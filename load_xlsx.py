import os
import sys
import hashlib
import logging
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from mysql.connector import connect, Error
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class ExcelLoader:
    def __init__(self):
        self.db_config = {
            'host': 'localhost',
            'user': 'root',  # 替换为你的数据库用户名
            'password': '123',  # 替换为你的数据库密码
            'database': 'book_search'
        }
        self.chunk_size = 5000
        self.n_workers = min(42, mp.cpu_count())

    def init_database(self):
        """初始化数据库，删除旧表并创建新表"""
        try:
            conn = connect(**self.db_config)
            cursor = conn.cursor()

            # 删除旧表
            cursor.execute("DROP TABLE IF EXISTS books")
            cursor.execute("DROP TABLE IF EXISTS processed_files")
            
            # 创建已处理文件记录表
            cursor.execute("""
                CREATE TABLE processed_files (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    file_path VARCHAR(512) NOT NULL,
                    file_hash VARCHAR(64) NOT NULL,
                    last_modified TIMESTAMP,
                    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE KEY unique_file_hash (file_hash),
                    UNIQUE KEY unique_file_path (file_path)
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
            """)
            
            # 创建书籍信息表
            cursor.execute("""
                CREATE TABLE books (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    file_id VARCHAR(100),
                    title MEDIUMTEXT,
                    author MEDIUMTEXT,
                    publisher MEDIUMTEXT,
                    language VARCHAR(50),
                    publish_year INT,
                    format VARCHAR(50),
                    source_file VARCHAR(512),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FULLTEXT INDEX idx_title (title),
                    FULLTEXT INDEX idx_author (author),
                    FULLTEXT INDEX idx_publisher (publisher)
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
            """)

            conn.commit()
            logging.info("数据库表初始化完成")
        except Error as e:
            logging.error(f"数据库初始化错误: {e}")
            raise
        finally:
            if conn.is_connected():
                cursor.close()
                conn.close()

    @staticmethod
    def process_file(args):
        """处理单个Excel文件"""
        file_path, db_config = args
        try:
            # 创建数据库连接
            conn = connect(**db_config)
            cursor = conn.cursor()

            # 计算文件哈希值
            hash_md5 = hashlib.md5()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            file_hash = hash_md5.hexdigest()

            # 读取Excel文件
            df = pd.read_excel(
                file_path,
                dtype={
                    '文件编号': str,
                    '书名': str,
                    '作者': str,
                    '出版社': str,
                    '语种': str,
                    '出版年份': 'Int64',
                    '文件格式': str
                }
            )
            df['源文件'] = Path(file_path).name
            
            # 替换所有的NaN值为None
            df = df.replace({np.nan: None})

            # 分批处理数据
            batch_size = 5000
            total_rows = len(df)
            processed_rows = 0

            while processed_rows < total_rows:
                batch_df = df.iloc[processed_rows:processed_rows + batch_size]
                values = []
                
                for _, row in batch_df.iterrows():
                    values.append((
                        str(row.get('文件编号'))[:100] if pd.notna(row.get('文件编号')) else None,
                        str(row.get('书名')) if pd.notna(row.get('书名')) else None,
                        str(row.get('作者')) if pd.notna(row.get('作者')) else None,
                        str(row.get('出版社')) if pd.notna(row.get('出版社')) else None,
                        str(row.get('语种'))[:50] if pd.notna(row.get('语种')) else None,
                        int(row.get('出版年份')) if pd.notna(row.get('出版年份')) else None,
                        str(row.get('文件格式'))[:50] if pd.notna(row.get('文件格式')) else None,
                        str(row.get('源文件'))[:512] if pd.notna(row.get('源文件')) else None
                    ))

                cursor.executemany("""
                    INSERT INTO books (
                        file_id, title, author, publisher, 
                        language, publish_year, format, source_file
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, values)
                conn.commit()

                processed_rows += len(batch_df)
                logging.info(f"文件 {Path(file_path).name}: 已处理 {processed_rows}/{total_rows} 行 ({processed_rows/total_rows*100:.1f}%)")

            # 记录已处理文件
            cursor.execute("""
                INSERT INTO processed_files (file_path, file_hash, last_modified)
                VALUES (%s, %s, %s)
            """, (str(file_path), file_hash, datetime.fromtimestamp(os.path.getmtime(file_path))))
            conn.commit()

            logging.info(f"完成处理文件 {Path(file_path).name}: 共处理 {total_rows} 行")
            return True
        except Exception as e:
            logging.error(f"处理文件时发生错误 {file_path}: {str(e)}")
            if 'conn' in locals() and conn.is_connected():
                conn.rollback()
            return False
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()

    def load_data(self, directory: str):
        """加载所有Excel文件到数据库"""
        try:
            # 初始化数据库（删除旧数据）
            self.init_database()

            # 查找所有Excel文件
            excel_files = []
            for pattern in ['*.xlsx', '*.xls']:
                excel_files.extend(Path(directory).glob(pattern))

            if not excel_files:
                raise FileNotFoundError(f"在目录 '{directory}' 中未找到Excel文件")

            logging.info(f"找到 {len(excel_files)} 个Excel文件，开始加载...")

            # 使用进程池处理文件
            with ProcessPoolExecutor(max_workers=self.n_workers) as executor:
                args = [(str(f), self.db_config) for f in excel_files]
                results = list(executor.map(self.process_file, args))

            # 统计处理结果
            success_count = sum(1 for r in results if r)
            logging.info(f"数据加载完成！成功处理 {success_count}/{len(excel_files)} 个文件")

        except Exception as e:
            logging.error(f"加载数据时发生错误: {str(e)}")
            raise

def main():
    if len(sys.argv) != 2:
        print("使用方法: python load_xlsx.py <xlsx目录路径>")
        sys.exit(1)

    directory = sys.argv[1]
    if not os.path.isdir(directory):
        print(f"错误: '{directory}' 不是有效的目录")
        sys.exit(1)

    loader = ExcelLoader()
    loader.load_data(directory)

if __name__ == "__main__":
    main() 