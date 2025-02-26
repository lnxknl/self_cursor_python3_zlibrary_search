#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pandas as pd
import numpy as np
import argparse
import logging
import sys
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime
import re
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
import os
import warnings
import traceback
from threading import Lock
from apscheduler.schedulers.background import BackgroundScheduler
import mysql.connector
from mysql.connector import Error
import hashlib

# 设置警告过滤
warnings.filterwarnings('ignore')

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('book_search.log', encoding='utf-8')
    ]
)

class BookSearcher:
    """图书搜索器"""
    
    def __init__(self):
        self.search_results = []
        self.chunk_size = 200000
        self.n_workers = min(42, mp.cpu_count())
        self.data_lock = Lock()
        self.db_config = {
            'host': 'localhost',
            'user': 'root',
            'password': '123',
            'database': 'book_search'
        }
        self.init_database()

    def init_database(self):
        """初始化数据库连接和表"""
        try:
            conn = mysql.connector.connect(**self.db_config)
            cursor = conn.cursor()

            # 创建已处理文件记录表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS processed_files (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    file_path VARCHAR(512) NOT NULL,
                    file_hash VARCHAR(64) NOT NULL,
                    last_modified TIMESTAMP,
                    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE KEY unique_file (file_path)
                )
            """)

            # 删除旧表（如果存在）并创建新的书籍信息表
            cursor.execute("DROP TABLE IF EXISTS books")
            
            # 创建书籍信息表，使用TEXT类型存储可能较长的内容
            cursor.execute("""
                CREATE TABLE books (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    file_id VARCHAR(100),
                    title TEXT,
                    author TEXT,
                    publisher TEXT,
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
    def process_file_static(file_path: str, db_config: dict) -> tuple:
        """静态方法处理单个文件并将数据存入数据库"""
        try:
            # 在子进程中创建新的数据库连接
            conn = mysql.connector.connect(**db_config)
            cursor = conn.cursor()

            # 计算文件哈希值
            hash_md5 = hashlib.md5()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            file_hash = hash_md5.hexdigest()

            # 检查文件是否已处理
            cursor.execute("""
                SELECT * FROM processed_files 
                WHERE file_path = %s AND file_hash = %s
            """, (file_path, file_hash))
            
            if cursor.fetchone():
                logging.info(f"文件已处理过，跳过: {file_path}")
                return None

            # 读取Excel文件
            df = pd.read_excel(file_path)
            df['源文件'] = Path(file_path).name
            
            # 替换所有的NaN值为None
            df = df.replace({np.nan: None})

            # 批量插入数据以提高性能
            values = []
            for _, row in df.iterrows():
                # 处理每个字段，确保None值和长字符串被正确处理
                file_id = str(row.get('文件编号'))[:100] if pd.notna(row.get('文件编号')) else None
                title = str(row.get('书名')) if pd.notna(row.get('书名')) else None
                author = str(row.get('作者')) if pd.notna(row.get('作者')) else None
                publisher = str(row.get('出版社')) if pd.notna(row.get('出版社')) else None
                language = str(row.get('语种'))[:50] if pd.notna(row.get('语种')) else None
                publish_year = int(row.get('出版年份')) if pd.notna(row.get('出版年份')) else None
                file_format = str(row.get('文件格式'))[:50] if pd.notna(row.get('文件格式')) else None
                source_file = str(row.get('源文件'))[:512] if pd.notna(row.get('源文件')) else None
                
                values.append((
                    file_id, title, author, publisher,
                    language, publish_year, file_format, source_file
                ))

            # 使用批量插入提高性能
            cursor.executemany("""
                INSERT INTO books (
                    file_id, title, author, publisher, 
                    language, publish_year, format, source_file
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, values)

            # 记录已处理文件
            cursor.execute("""
                INSERT INTO processed_files (file_path, file_hash, last_modified)
                VALUES (%s, %s, %s)
            """, (file_path, file_hash, datetime.fromtimestamp(os.path.getmtime(file_path))))

            conn.commit()
            return str(file_path), True
        except Exception as e:
            logging.error(f"处理文件时发生错误 {file_path}: {str(e)}")
            if 'conn' in locals() and conn.is_connected():
                conn.rollback()
            return None
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()

    def load_data(self, directory: str = '../xlsx', force_reload: bool = False) -> None:
        """加载所有Excel文件到数据库中"""
        try:
            excel_files = []
            for pattern in ['*.xlsx', '*.xls']:
                excel_files.extend(Path(directory).glob(pattern))
            
            if not excel_files:
                raise FileNotFoundError(f"在目录 '{directory}' 中未找到Excel文件")
            
            print(f"找到 {len(excel_files)} 个Excel文件，开始加载...")
            
            if force_reload:
                # 如果强制重新加载，清除已处理文件记录
                with mysql.connector.connect(**self.db_config) as conn:
                    with conn.cursor() as cursor:
                        cursor.execute("TRUNCATE TABLE processed_files")
                        cursor.execute("TRUNCATE TABLE books")
                    conn.commit()

            # 使用进程池处理文件
            with ProcessPoolExecutor(max_workers=self.n_workers) as executor:
                futures = []
                for file_path in excel_files:
                    futures.append(
                        executor.submit(
                            self.process_file_static,
                            str(file_path),
                            self.db_config
                        )
                    )
                
                # 显示进度
                total_files = len(futures)
                completed = 0
                
                for future in futures:
                    try:
                        result = future.result()
                        if result:
                            completed += 1
                        print(f"加载进度: {completed}/{total_files} 文件 ({(completed/total_files*100):.1f}%)", 
                              end='\r')
                    except Exception as e:
                        logging.error(f"处理加载结果时发生错误: {str(e)}")
                        logging.error(traceback.format_exc())
        
            print("\n数据加载完成！")
        except Exception as e:
            logging.error(f"加载数据时发生错误: {str(e)}")
            raise

    @staticmethod
    def process_chunk(args):
        """Static method to process a single chunk"""
        df_chunk, search_params = args
        try:
            # Build query
            query = True
            for field, value in search_params.items():
                if value and field in df_chunk.columns:
                    if isinstance(value, str) and field not in ['上传日期', '日期1']:
                        try:
                            query &= df_chunk[field].astype(str).str.contains(value, case=False, na=False)
                        except Exception as e:
                            logging.warning(f"字段 {field} 的类型转换失败: {str(e)}")
                            continue
                    else:
                        try:
                            query &= (df_chunk[field] == value)
                        except Exception as e:
                            logging.warning(f"字段 {field} 的比较失败: {str(e)}")
                            continue
            
            # Get matching results
            matches = df_chunk[query].to_dict('records')
            return matches
        except Exception as e:
            logging.error(f"处理数据块时发生错误: {str(e)}")
            return []

    def search_books(self, **kwargs) -> List[Dict[str, Any]]:
        """从数据库中搜索符合条件的书籍"""
        try:
            conn = mysql.connector.connect(**self.db_config)
            cursor = conn.cursor(dictionary=True)

            # 构建查询条件
            conditions = []
            params = []
            for field, value in kwargs.items():
                if value:
                    if field == 'title':
                        conditions.append("MATCH(title) AGAINST(%s)")
                        params.append(f"%{value}%")
                    elif field == 'author':
                        conditions.append("MATCH(author) AGAINST(%s)")
                        params.append(f"%{value}%")
                    elif field == 'publisher':
                        conditions.append("MATCH(publisher) AGAINST(%s)")
                        params.append(f"%{value}%")
                    elif field == 'year':
                        conditions.append("publish_year = %s")
                        params.append(value)
                    # 添加其他搜索条件...

            query = "SELECT * FROM books"
            if conditions:
                query += " WHERE " + " AND ".join(conditions)

            cursor.execute(query, params)
            results = cursor.fetchall()
            return results

        except Error as e:
            logging.error(f"数据库搜索错误: {e}")
            return []
        finally:
            if conn.is_connected():
                cursor.close()
                conn.close()

    def print_results(self, verbose: bool = False) -> None:
        """打印搜索结果"""
        if not self.search_results:
            print("未找到匹配的书籍")
            return
        
        print(f"\n找到 {len(self.search_results)} 本匹配的书籍：")
        
        # 按文件分组显示结果
        results_by_file = {}
        for book in self.search_results:
            source_file = book.get('源文件', 'unknown')
            if source_file not in results_by_file:
                results_by_file[source_file] = []
            results_by_file[source_file].append(book)
        
        for source_file, books in results_by_file.items():
            print(f"\n在文件 {source_file} 中找到 {len(books)} 本书：")
            for idx, book in enumerate(books, 1):
                print(f"\n  --- 第 {idx} 本书 ---")
                if verbose:
                    # 详细模式显示所有字段
                    for field, value in book.items():
                        if field != '源文件':  # 不重复显示源文件
                            print(f"  {field}: {value}")
                else:
                    # 简略模式只显示主要字段
                    main_fields = ['书名', '作者', '出版社', '出版年份']
                    for field in main_fields:
                        if field in book:
                            print(f"  {field}: {book[field]}")

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='快速搜索和检查书籍信息')
    parser.add_argument('--dir', '-d', default='.', help='Excel文件所在目录路径（默认为当前目录）')
    parser.add_argument('--verbose', '-v', action='store_true', help='显示详细信息')
    parser.add_argument('--chunk-size', type=int, default=200000, help='每次处理的数据块大小')
    parser.add_argument('--reload', action='store_true', help='强制重新加载数据')
    
    # 添加所有可能的搜索字段
    parser.add_argument('--file-id', help='文件编号')
    parser.add_argument('--title', help='书名')
    parser.add_argument('--author', help='作者')
    parser.add_argument('--publisher', help='出版社')
    parser.add_argument('--language', help='语种')
    parser.add_argument('--year', type=int, help='出版年份')
    parser.add_argument('--format', help='文件格式')
    parser.add_argument('--export', help='导出搜索结果到Excel文件')
    
    args = parser.parse_args()
    
    try:
        searcher = BookSearcher()
        searcher.chunk_size = args.chunk_size
        
        # 构建搜索条件
        search_params = {
            '文件编号': args.file_id,
            '书名': args.title,
            '作者': args.author,
            '出版社': args.publisher,
            '语种': args.language,
            '出版年份': args.year,
            '文件格式': args.format
        }
        
        # 移除None值的参数
        search_params = {k: v for k, v in search_params.items() if v is not None}
        
        if not search_params:
            print("请提供至少一个搜索条件")
            parser.print_help()
            return 1
        
        # 执行搜索
        start_time = datetime.now()
        results = searcher.search_books(**search_params)
        end_time = datetime.now()
        
        # 打印结果
        print(f"\n搜索用时: {(end_time - start_time).total_seconds():.2f} 秒")
        searcher.print_results(args.verbose)
        
        # 导出结果
        if args.export and results:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            export_file = f"search_results_{timestamp}.xlsx"
            pd.DataFrame(results).to_excel(export_file, index=False)
            print(f"\n搜索结果已导出到: {export_file}")
        
        return 0
        
    except Exception as e:
        print(f"错误: {str(e)}")
        if args.verbose:
            traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main()) 
