import requests
import json
from typing import Dict, Any, List
import argparse

class BookSearchClient:
    def __init__(self, base_url: str = "http://localhost:6301"):
        self.base_url = base_url.rstrip('/')
        
    def load_data(self, directory: str = '.', force_reload: bool = False) -> Dict[str, Any]:
        """Load or reload the book data on the server"""
        response = requests.post(
            f"{self.base_url}/load",
            json={
                "directory": directory,
                "force_reload": force_reload
            }
        )
        return response.json()
    
    def search_books(self, **kwargs) -> Dict[str, Any]:
        """
        Search for books using various criteria
        
        Parameters:
        - file_id (str): File ID
        - title (str): Book title
        - author (str): Author name
        - publisher (str): Publisher name
        - language (str): Language
        - year (int): Publication year
        - format (str): File format
        """
        response = requests.post(
            f"{self.base_url}/search",
            json=kwargs
        )
        return response.json()

def main():
    parser = argparse.ArgumentParser(description='Search for books using the book search service')
    parser.add_argument('--url', default='http://localhost:6301', help='Service URL')
    parser.add_argument('--directory', '-d', default='.', help='Directory to load books from')
    parser.add_argument('--reload', action='store_true', help='Force reload of book data')
    
    # Search parameters
    parser.add_argument('--title', help='Book title')
    parser.add_argument('--author', help='Author name')
    parser.add_argument('--publisher', help='Publisher name')
    parser.add_argument('--language', help='Language')
    parser.add_argument('--year', type=int, help='Publication year')
    parser.add_argument('--format', help='File format')
    parser.add_argument('--file-id', help='File ID')
    
    args = parser.parse_args()
    
    # Initialize client
    client = BookSearchClient(base_url=args.url)
    
    # Load data if requested
    if args.reload:
        print("Loading data...")
        result = client.load_data(directory=args.directory, force_reload=True)
        print(f"Load result: {json.dumps(result, indent=2, ensure_ascii=False)}")
    
    # Build search parameters (only include non-None values)
    search_params = {
        'title': args.title,
        'author': args.author,
        'publisher': args.publisher,
        'language': args.language,
        'year': args.year,
        'format': args.format,
        'file_id': args.file_id
    }
    search_params = {k: v for k, v in search_params.items() if v is not None}
    
    if not search_params:
        print("Error: No search parameters provided")
        parser.print_help()
        return
    
    # Perform search
    print("\nSearching for books...")
    search_result = client.search_books(**search_params)
    
    print(f"\nSearch results: {json.dumps(search_result, indent=2, ensure_ascii=False)}")

if __name__ == "__main__":
    main() 
