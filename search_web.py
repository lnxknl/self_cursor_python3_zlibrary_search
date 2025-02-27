from flask import Flask, render_template, jsonify, request, session, json
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
    
    # 将翻译字典转换为JSON安全的格式
    translations_json = json.dumps(TRANSLATIONS[lang], ensure_ascii=False)
    
    return render_template('index.html', 
                         translations=TRANSLATIONS[lang],
                         translations_json=translations_json,
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
        force_reload = data.get('force_reload', False)
        
        if not force_reload:
            # 检查数据库中是否已有数据
            searcher = get_user_searcher()
            stats = searcher.get_statistics()
            if stats.get('total', 0) > 0:
                return jsonify({
                    'status': 'success',
                    'message': f'数据库中已有 {stats["total"]} 条记录，无需重新加载'
                })

        # 只有在强制重新加载或数据库为空时才处理Excel文件
        directory = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'xlsx')
        searcher = get_user_searcher()
        searcher.load_data(directory=directory, force_reload=force_reload)
        
        return jsonify({
            'status': 'success',
            'message': '数据加载完成'
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
        
        # 获取分页参数
        page = int(data.get('page', 1))
        per_page = int(data.get('per_page', 1000))
        
        # 构建搜索参数
        search_params = {
            'title': data.get('title'),
            'author': data.get('author'),
            'publisher': data.get('publisher'),
            'year': data.get('year'),
            'language': data.get('language'),
            'format': data.get('format'),
            'page': page,
            'per_page': per_page
        }
        
        # 移除None值
        search_params = {k: v for k, v in search_params.items() if v is not None}
        
        # 执行搜索
        results = searcher.search_books(**search_params)
        
        return jsonify({
            'status': 'success',
            'data': results['results'],
            'pagination': {
                'total': results['total'],
                'page': results['page'],
                'per_page': results['per_page'],
                'total_pages': results['total_pages']
            }
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
