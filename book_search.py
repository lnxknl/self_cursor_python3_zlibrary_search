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
        self.loaded_data = {}
        self.last_load_time = {}
    
    def read_excel_safe(self, file_path: str) -> pd.DataFrame:
        """安全地读取Excel文件"""
        try:
            # 尝试使用openpyxl引擎
            return pd.read_excel(file_path, engine='openpyxl')
        except Exception as e1:
            logging.warning(f"使用openpyxl读取失败 {file_path}, 尝试其他引擎: {str(e1)}")
            try:
                # 尝试使用xlrd引擎
                return pd.read_excel(file_path, engine='xlrd')
            except Exception as e2:
                logging.warning(f"使用xlrd读取失败 {file_path}, 尝试最后方案: {str(e2)}")
                try:
                    # 最后尝试不指定引擎
                    return pd.read_excel(file_path)
                except Exception as e3:
                    logging.error(f"所有读取方法都失败 {file_path}: {str(e3)}")
                    raise
    
    @staticmethod
    def process_file(args):
        """Static method to process a single file"""
        file_path, reader_method = args
        try:
            df = reader_method(file_path)
            df['源文件'] = Path(file_path).name
            return str(file_path), df
        except Exception as e:
            logging.error(f"加载文件 {file_path} 时发生错误: {str(e)}")
            return None

    def load_data(self, directory: str = '../xlsx', force_reload: bool = False) -> None:
        """Load all Excel files from the directory into memory"""
        excel_files = []
        for pattern in ['*.xlsx', '*.xls']:
            excel_files.extend(Path(directory).glob(pattern))
        
        if not excel_files:
            raise FileNotFoundError(f"在目录 '{directory}' 中未找到Excel文件")
            
        print(f"找到 {len(excel_files)} 个Excel文件，开始加载...")
        
        # Load files in parallel
        with ProcessPoolExecutor(max_workers=self.n_workers) as executor:
            futures = []
            for f in excel_files:
                file_path = str(f)
                if not force_reload and file_path in self.loaded_data:
                    file_mtime = os.path.getmtime(file_path)
                    if file_mtime <= self.last_load_time.get(file_path, 0):
                        continue
                futures.append(
                    executor.submit(
                        self.process_file, 
                        (file_path, self.read_excel_safe)
                    )
                )
            
            # Show progress
            total_files = len(futures)
            completed = 0
            
            for future in futures:
                try:
                    result = future.result()
                    if result:
                        file_path, df = result
                        self.loaded_data[file_path] = df
                        self.last_load_time[file_path] = os.path.getmtime(file_path)
                    completed += 1
                    print(f"加载进度: {completed}/{total_files} 文件 ({(completed/total_files*100):.1f}%)", 
                          end='\r')
                except Exception as e:
                    logging.error(f"处理加载结果时发生错误: {str(e)}")
                    logging.error(traceback.format_exc())
        
        print("\n数据加载完成！")

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

    def search_books(self, directory: str = '.', reload: bool = False, **kwargs) -> List[Dict[str, Any]]:
        """搜索符合条件的书籍"""
        if not self.loaded_data or reload:
            self.load_data(directory, force_reload=reload)
            
        all_results = []
        
        # Create a pool of workers
        with ProcessPoolExecutor(max_workers=self.n_workers) as executor:
            futures = []
            
            # Process each loaded DataFrame
            for file_path, df in self.loaded_data.items():
                try:
                    # Split DataFrame into chunks
                    chunks = [df[i:i + self.chunk_size] for i in range(0, len(df), self.chunk_size)]
                    
                    # Submit each chunk for processing
                    for chunk in chunks:
                        futures.append(
                            executor.submit(self.process_chunk, (chunk, kwargs))
                        )
                    
                except Exception as e:
                    logging.error(f"处理文件 {file_path} 时发生错误: {str(e)}")
                    logging.error(traceback.format_exc())
            
            # Show progress
            total_futures = len(futures)
            completed = 0
            
            # Collect results as they complete
            for future in futures:
                try:
                    chunk_results = future.result()
                    all_results.extend(chunk_results)
                    completed += 1
                    print(f"搜索进度: {completed}/{total_futures} 块 ({(completed/total_futures*100):.1f}%)", 
                          end='\r')
                except Exception as e:
                    logging.error(f"处理搜索结果时发生错误: {str(e)}")
            
            print("\n搜索完成！")
        
        self.search_results = all_results
        return all_results

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
        results = searcher.search_books(args.dir, reload=args.reload, **search_params)
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
