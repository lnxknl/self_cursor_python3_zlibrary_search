from flask import Flask, request, jsonify
from book_search import BookSearcher
import logging

app = Flask(__name__)
# Initialize the BookSearcher as a global instance
searcher = BookSearcher()

@app.route('/load', methods=['POST'])
def load_data():
    """Load or reload the book data"""
    try:
        data = request.get_json()
        directory = data.get('directory', '.')
        force_reload = data.get('force_reload', False)
        
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

@app.route('/search', methods=['POST'])
def search():
    """Search for books based on provided criteria"""
    try:
        data = request.get_json()
        search_params = {
            '文件编号': data.get('file_id'),
            '书名': data.get('title'),
            '作者': data.get('author'),
            '出版社': data.get('publisher'),
            '语种': data.get('language'),
            '出版年份': data.get('year'),
            '文件格式': data.get('format')
        }
        
        # Remove None values
        search_params = {k: v for k, v in search_params.items() if v is not None}
        
        if not search_params:
            return jsonify({
                'status': 'error',
                'message': 'No search parameters provided'
            }), 400
        
        results = searcher.search_books(**search_params)
        
        return jsonify({
            'status': 'success',
            'count': len(results),
            'results': results
        })
    except Exception as e:
        logging.error(f"Error during search: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

if __name__ == '__main__':
    # Initialize logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Start the Flask server
    app.run(host='0.0.0.0', port=6301) 
