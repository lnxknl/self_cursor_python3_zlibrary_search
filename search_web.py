from flask import Flask, render_template, jsonify, request, session
from book_search import BookSearcher
from translations import TRANSLATIONS
import os
import time
import secrets
import logging
from threading import Lock

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
        directory = data.get('directory', '.')
        force_reload = data.get('force_reload', False)
        
        searcher = get_user_searcher()
        searcher.load_data(directory=directory, force_reload=force_reload)
        return jsonify({
            'status': 'success',
            'message': 'Data loaded successfully'
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
        
        # Map English field names to Chinese field names
        search_params = {
            '文件编号': data.get('file_id'),
            '书名': data.get('title'),
            '作者': data.get('author'),
            '出版社': data.get('publisher'),
            '语种': data.get('language'),
            '出版年份': data.get('year'),
            '文件格式': data.get('format')
        }
        
        # Remove None and empty string values
        search_params = {k: v for k, v in search_params.items() if v is not None and v != ''}
        
        if not search_params:
            return jsonify({
                'status': 'error',
                'message': 'No search parameters provided'
            }), 400
        
        results = searcher.search_books(**search_params)
        
        # Transform results to use English field names and handle non-JSON-serializable values
        transformed_results = []
        for result in results:
            # Convert any numeric values to strings if they're NaN
            transformed = {
                'file_id': str(result.get('文件编号', '')) if result.get('文件编号') is not None else '',
                'title': str(result.get('书名', '')) if result.get('书名') is not None else '',
                'author': str(result.get('作者', '')) if result.get('作者') is not None else '',
                'publisher': str(result.get('出版社', '')) if result.get('出版社') is not None else '',
                'language': str(result.get('语种', '')) if result.get('语种') is not None else '',
                'year': str(result.get('出版年份', '')) if result.get('出版年份') is not None else '',
                'format': str(result.get('文件格式', '')) if result.get('文件格式') is not None else ''
            }
            
            # Clean up 'nan' strings
            transformed = {k: '' if v.lower() == 'nan' else v for k, v in transformed.items()}
            transformed_results.append(transformed)
        
        return jsonify({
            'status': 'success',
            'count': len(results),
            'results': transformed_results
        })
    except Exception as e:
        logging.exception("Error during search")
        return jsonify({
            'status': 'error',
            'message': f"Search error: {str(e)}"
        }), 500

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    app.run(host='0.0.0.0', port=6122, debug=True)
