import httpx
from typing import List, Dict, Any, Optional
from .base import RestaurantProvider

class YelpRestaurantProvider(RestaurantProvider):
    """Provider integrating with Yelp Fusion API."""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.yelp.com/v3"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json"
        }
        
    async def search_nearby_restaurants(
        self, 
        latitude: float, 
        longitude: float, 
        query: Optional[str] = None, 
        radius_meters: int = 5000,
        price_tier: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        
        # Yelp limits max radius to 40000 meters
        radius_meters = min(radius_meters, 40000)
        
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "radius": radius_meters,
            "categories": "restaurants,food",
            "limit": 15,
            "sort_by": "distance"
        }
        
        if query:
            params["term"] = query
            
        if price_tier:
            # Convert "$$" to "2" for Yelp
            price_len = len(price_tier)
            if 1 <= price_len <= 4:
                params["price"] = str(price_len)
                
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/businesses/search", 
                headers=self.headers,
                params=params
            )
            response.raise_for_status()
            data = response.json()
            
            businesses = data.get("businesses", [])
            results = []
            
            for b in businesses:
                results.append({
                    "id": b.get("id"),
                    "name": b.get("name"),
                    "rating": b.get("rating", 0.0),
                    "distance_meters": round(b.get("distance", 0.0)),
                    "price": b.get("price", "N/A"),
                    "cuisine": [c.get("title") for c in b.get("categories", [])],
                    "address": ", ".join(b.get("location", {}).get("display_address", [])),
                    "is_closed": b.get("is_closed", False),
                    "url": b.get("url", "")
                })
                
            return results
