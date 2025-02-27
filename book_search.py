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
import time

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
        self.db_config = {
            'host': 'localhost',
            'user': 'root',
            'password': '123',
            'database': 'book_search'
        }
        self.ensure_db_initialized()

    def ensure_db_initialized(self):
        """确保数据库已初始化"""
        try:
            conn = mysql.connector.connect(**self.db_config)
            cursor = conn.cursor()
            
            # 检查表是否存在
            cursor.execute("""
                SELECT COUNT(*) 
                FROM information_schema.tables 
                WHERE table_schema = %s 
                AND table_name IN ('books', 'processed_files')
            """, (self.db_config['database'],))
            
            if cursor.fetchone()[0] < 2:
                self.init_database()
            
        except Error as e:
            logging.error(f"检查数据库状态时发生错误: {e}")
            raise
        finally:
            if conn.is_connected():
                cursor.close()
                conn.close()

    def init_database(self):
        """初始化数据库连接和表"""
        try:
            conn = mysql.connector.connect(**self.db_config)
            cursor = conn.cursor()

            # 删除旧表（如果存在）
            cursor.execute("DROP TABLE IF EXISTS books")
            cursor.execute("DROP TABLE IF EXISTS processed_files")
            
            # 创建已处理文件记录表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS processed_files (
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
                SELECT file_path, file_hash, last_modified 
                FROM processed_files 
                WHERE file_path = %s OR file_hash = %s
            """, (file_path, file_hash))
            
            result = cursor.fetchone()
            if result:
                db_path, db_hash, db_modified = result
                current_modified = datetime.fromtimestamp(os.path.getmtime(file_path))
                
                # 如果文件路径和哈希值都匹配，且修改时间未变，则跳过
                if db_path == file_path and db_hash == file_hash:
                    logging.info(f"文件已处理过且未修改，跳过: {file_path}")
                    return None
                
                # 如果只有哈希值匹配，说明是相同内容的文件
                if db_hash == file_hash:
                    logging.info(f"发现相同内容的文件: {db_path} 和 {file_path}")
                    return None

            # 优化Excel读取
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

            # 分批处理数据，增加批量大小
            batch_size = 5000  # 增加到5000条记录
            total_rows = len(df)
            processed_rows = 0
            last_log_time = time.time()
            log_interval = 5  # 每5秒记录一次日志

            # 准备SQL语句
            sql = """
                INSERT INTO books (
                    file_id, title, author, publisher, 
                    language, publish_year, format, source_file
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """

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

                try:
                    # 使用executemany进行批量插入
                    cursor.executemany(sql, values)
                    conn.commit()
                    
                    processed_rows += len(batch_df)
                    
                    # 控制日志输出频率
                    current_time = time.time()
                    if current_time - last_log_time >= log_interval:
                        logging.info(f"文件 {Path(file_path).name}: 已处理 {processed_rows}/{total_rows} 行 ({processed_rows/total_rows*100:.1f}%)")
                        last_log_time = current_time
                        
                except Error as e:
                    logging.error(f"插入批次数据时发生错误: {str(e)}")
                    conn.rollback()
                    raise

            # 记录已处理文件
            cursor.execute("""
                INSERT INTO processed_files (file_path, file_hash, last_modified)
                VALUES (%s, %s, %s)
            """, (file_path, file_hash, datetime.fromtimestamp(os.path.getmtime(file_path))))

            conn.commit()
            logging.info(f"完成处理文件 {Path(file_path).name}: 共处理 {total_rows} 行")
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
        """仅在必要时加载Excel文件数据"""
        try:
            # 首先检查数据库中是否已有数据
            conn = mysql.connector.connect(**self.db_config)
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM books")
            book_count = cursor.fetchone()[0]
            
            if book_count > 0 and not force_reload:
                logging.info(f"数据库中已有 {book_count} 条记录，跳过加载")
                return
            
            # 如果没有数据或强制重新加载，则处理Excel文件
            logging.info("开始加载Excel文件数据...")
            
            excel_files = []
            for pattern in ['*.xlsx', '*.xls']:
                excel_files.extend(Path(directory).glob(pattern))
            
            if not excel_files:
                raise FileNotFoundError(f"在目录 '{directory}' 中未找到Excel文件")
            
            print(f"找到 {len(excel_files)} 个Excel文件，开始加载...")
            
            # 使用进程池处理文件
            with ProcessPoolExecutor(max_workers=min(42, mp.cpu_count())) as executor:
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
        except Error as e:
            logging.error(f"检查数据库状态时发生错误: {e}")
            raise
        finally:
            if conn.is_connected():
                cursor.close()
                conn.close()

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

    def search_books(self, page=1, per_page=1000, **kwargs) -> dict:
        """从数据库中搜索符合条件的书籍，支持分页"""
        try:
            conn = mysql.connector.connect(**self.db_config)
            cursor = conn.cursor(dictionary=True)

            # 构建查询条件
            conditions = []
            params = []
            
            if kwargs.get('file_id'):
                conditions.append("file_id = %s")
                params.append(kwargs['file_id'])
            if kwargs.get('title'):
                conditions.append("MATCH(title) AGAINST(%s IN BOOLEAN MODE)")
                params.append(f"*{kwargs['title']}*")
            if kwargs.get('author'):
                conditions.append("MATCH(author) AGAINST(%s IN BOOLEAN MODE)")
                params.append(f"*{kwargs['author']}*")
            if kwargs.get('publisher'):
                conditions.append("MATCH(publisher) AGAINST(%s IN BOOLEAN MODE)")
                params.append(f"*{kwargs['publisher']}*")
            if kwargs.get('language'):
                conditions.append("language = %s")
                params.append(kwargs['language'])
            if kwargs.get('year'):
                conditions.append("publish_year = %s")
                params.append(kwargs['year'])
            if kwargs.get('format'):
                conditions.append("format = %s")
                params.append(kwargs['format'])

            # 构建WHERE子句
            where_clause = " AND ".join(conditions) if conditions else "1"

            # 获取总记录数
            count_query = f"SELECT COUNT(*) as total FROM books WHERE {where_clause}"
            cursor.execute(count_query, params)
            total_count = cursor.fetchone()['total']

            # 计算分页
            offset = (page - 1) * per_page
            
            # 执行分页查询
            query = f"""
                SELECT * FROM books 
                WHERE {where_clause}
                ORDER BY id 
                LIMIT %s OFFSET %s
            """
            cursor.execute(query, params + [per_page, offset])
            results = cursor.fetchall()

            # 计算总页数
            total_pages = (total_count + per_page - 1) // per_page

            logging.info(f"数据库查询完成，共找到 {total_count} 条结果，当前显示第 {page} 页")
            
            return {
                'results': results,
                'total': total_count,
                'page': page,
                'per_page': per_page,
                'total_pages': total_pages
            }

        except Error as e:
            logging.error(f"数据库查询错误: {e}")
            return {'results': [], 'total': 0, 'page': page, 'per_page': per_page, 'total_pages': 0}
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

    def get_statistics(self) -> Dict[str, Any]:
        """获取数据库统计信息"""
        try:
            conn = mysql.connector.connect(**self.db_config)
            cursor = conn.cursor(dictionary=True)
            
            stats = {}
            
            # 获取总记录数
            cursor.execute("SELECT COUNT(*) as total FROM books")
            stats.update(cursor.fetchone())
            
            # 获取语言统计
            cursor.execute("""
                SELECT language, COUNT(*) as count 
                FROM books 
                WHERE language IS NOT NULL 
                GROUP BY language
            """)
            stats['languages'] = cursor.fetchall()
            
            # 获取年份范围
            cursor.execute("""
                SELECT 
                    MIN(publish_year) as earliest_year,
                    MAX(publish_year) as latest_year
                FROM books 
                WHERE publish_year IS NOT NULL
            """)
            stats.update(cursor.fetchone())
            
            return stats
            
        except Error as e:
            logging.error(f"获取统计信息时发生错误: {e}")
            return {}
        finally:
            if conn.is_connected():
                cursor.close()
                conn.close()

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
        if args.export and results['results']:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            export_file = f"search_results_{timestamp}.xlsx"
            pd.DataFrame(results['results']).to_excel(export_file, index=False)
            print(f"\n搜索结果已导出到: {export_file}")
        
        return 0
        
    except Exception as e:
        print(f"错误: {str(e)}")
        if args.verbose:
            traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main()) 
