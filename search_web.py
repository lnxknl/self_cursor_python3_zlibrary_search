from flask import Flask, render_template, jsonify, request, session
from book_search import BookSearcher
from translations import TRANSLATIONS
import os
import time
import secrets
import logging
from threading import Lock
from pathlib import Path

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# Global dictionary to store user-specific searchers
user_searchers = {}
searcher_lock = Lock()

def get_user_searcher():
    """Get or create a BookSearcher instance for the current user"""
    user_id = session.get('user_id')
    if not user_id:
        user_id = secrets.token_hex(8)
        session['user_id'] = user_id
    
    with searcher_lock:
        if user_id not in user_searchers:
            user_searchers[user_id] = BookSearcher()
        return user_searchers[user_id]

@app.route('/')
def index():
    """Render the main search page"""
    # Get language from query parameter or session or default to Chinese
    lang = request.args.get('lang') or session.get('lang', 'zh')
    session['lang'] = lang  # Store language preference in session
    return render_template('index.html', 
                         translations=TRANSLATIONS[lang],
                         current_lang=lang)

@app.route('/change-language/<lang>')
def change_language(lang):
    """Change the interface language"""
    if lang in TRANSLATIONS:
        session['lang'] = lang
        return jsonify({
            'status': 'success',
            'translations': TRANSLATIONS[lang]
        })
    return jsonify({'status': 'error', 'message': 'Invalid language'}), 400

@app.route('/api/load', methods=['POST'])
def load_data():
    """Load or reload the book data"""
    try:
        data = request.get_json()
        # 使用相对于应用程序的路径
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        directory = data.get('directory', '../xlsx')
        directory = os.path.join(base_dir, directory)
        force_reload = data.get('force_reload', False)
        
        # 确保目录存在
        directory = os.path.abspath(directory)
        logging.info(f"Searching for Excel files in directory: {directory}")
        
        if not os.path.exists(directory):
            return jsonify({
                'status': 'error',
                'message': f'目录不存在: {directory}'
            }), 404

        # 检查是否有Excel文件
        excel_files = []
        for pattern in ['*.xlsx', '*.xls']:
            excel_files.extend(Path(directory).glob(pattern))
        
        if not excel_files:
            return jsonify({
                'status': 'error',
                'message': f'在目录 {directory} 中未找到Excel文件'
            }), 404

        logging.info(f"Found {len(excel_files)} Excel files")
        searcher = get_user_searcher()
        searcher.load_data(directory=directory, force_reload=force_reload)
        
        return jsonify({
            'status': 'success',
            'message': f'成功处理 {len(excel_files)} 个Excel文件'
        })
    except Exception as e:
        logging.error(f"Error loading data: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/search', methods=['POST'])
def search():
    """Search for books based on provided criteria"""
    try:
        data = request.get_json()
        logging.info(f"Received search request with data: {data}")
        
        searcher = get_user_searcher()
        
        # 构建搜索参数
        search_params = {
            'title': data.get('title'),
            'author': data.get('author'),
            'publisher': data.get('publisher'),
            'year': data.get('year'),
            'language': data.get('language'),
            'format': data.get('format')
        }
        
        # 移除None值
        search_params = {k: v for k, v in search_params.items() if v is not None}
        
        # 执行搜索
        results = searcher.search_books(**search_params)
        
        return jsonify({
            'status': 'success',
            'data': results,
            'count': len(results)
        })
    except Exception as e:
        logging.error(f"Search error: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    app.run(host='0.0.0.0', port=6122, debug=True)
