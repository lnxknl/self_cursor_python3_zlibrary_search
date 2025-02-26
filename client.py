import requests
import json
from typing import Dict, Any, List

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
    # Example usage
    client = BookSearchClient()
    
    # First, load the data
    print("Loading data...")
    result = client.load_data(directory=".", force_reload=True)
    print(f"Load result: {json.dumps(result, indent=2, ensure_ascii=False)}")
    
    # Example search
    print("\nSearching for books...")
    search_result = client.search_books(
        title="Python",  # Replace with your search criteria
        publisher="O'Reilly"
    )
    
    print(f"\nSearch results: {json.dumps(search_result, indent=2, ensure_ascii=False)}")

if __name__ == "__main__":
    main() 
