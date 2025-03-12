import requests
from src.utils.logger import logger
from src.config.config import API_BASE_URL

async def api_request(method: str, endpoint: str, token: str = None, data: dict = None):
    """Make API requests to the Copperx API"""
    url = f"{API_BASE_URL}{endpoint}"
    headers = {'Authorization': f'Bearer {token}'} if token else {}
    
    try:
        if method.lower() == 'get':
            response = requests.get(url, headers=headers)
        elif method.lower() == 'post':
            response = requests.post(url, headers=headers, json=data)
        
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed: {str(e)}")
        return {"error": str(e)}