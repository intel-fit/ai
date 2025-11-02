import requests
import os

USDA_API_KEY = os.getenv("USDA_API_KEY", "NWV0qcDRTdPxcxLmebG1nsi2sPDYITi56HIoiZy3")
BASE_URL = "https://api.nal.usda.gov/fdc/v1/foods/search"

def search_usda_food(query: str, page_size: int = 5):
    params = {
        "query": query,
        "pageSize": page_size,
        "api_key": USDA_API_KEY
    }
    response = requests.get(BASE_URL, params=params)
    if response.status_code != 200:
        return None
    return response.json()
