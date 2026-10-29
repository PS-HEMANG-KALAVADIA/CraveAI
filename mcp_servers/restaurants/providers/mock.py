from typing import List, Dict, Any, Optional
from .base import RestaurantProvider

MOCK_RESTAURANTS = [
    {
        "id": "mock_1",
        "name": "Rajwada Thali",
        "rating": 4.5,
        "distance_meters": 1200,
        "price": "$$",
        "cuisine": ["Gujarati", "Rajasthani", "Thali"],
        "address": "123 Heritage Road, Ahmedabad",
        "is_closed": False,
        "url": "https://example.com/rajwada"
    },
    {
        "id": "mock_2",
        "name": "Spicy Bite Cafe",
        "rating": 4.2,
        "distance_meters": 800,
        "price": "$",
        "cuisine": ["Street Food", "Snacks"],
        "address": "45 Market St, Ahmedabad",
        "is_closed": False,
        "url": "https://example.com/spicy-bite"
    },
    {
        "id": "mock_3",
        "name": "Jaipur Sweets & Namkeen",
        "rating": 4.8,
        "distance_meters": 2500,
        "price": "$",
        "cuisine": ["Sweets", "Snacks", "Rajasthani"],
        "address": "88 City Center, Jaipur",
        "is_closed": False,
        "url": "https://example.com/jaipur-sweets"
    },
    {
        "id": "mock_4",
        "name": "The Grand Kachori House",
        "rating": 4.7,
        "distance_meters": 400,
        "price": "$",
        "cuisine": ["Snacks", "Street Food"],
        "address": "12 Old City, Jaipur",
        "is_closed": False,
        "url": "https://example.com/kachori-house"
    }
]

class MockRestaurantProvider(RestaurantProvider):
    """A deterministic mock provider that simulates an API response."""
    
    async def search_nearby_restaurants(
        self, 
        latitude: float, 
        longitude: float, 
        query: Optional[str] = None, 
        radius_meters: int = 5000,
        price_tier: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        results = []
        for r in MOCK_RESTAURANTS:
            # Simple distance filter
            if r["distance_meters"] > radius_meters:
                continue
                
            # Simple query filter (matches name or cuisine)
            if query:
                q = query.lower()
                matches_name = q in r["name"].lower()
                matches_cuisine = any(q in c.lower() for c in r["cuisine"])
                if not (matches_name or matches_cuisine):
                    continue
                    
            # Price tier filter
            if price_tier and r["price"] != price_tier:
                continue
                
            results.append(r)
            
        # Sort by distance
        results.sort(key=lambda x: x["distance_meters"])
        return results
