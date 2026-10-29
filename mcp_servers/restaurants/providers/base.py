from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

class RestaurantProvider(ABC):
    """Abstract base class for all restaurant providers."""
    
    @abstractmethod
    async def search_nearby_restaurants(
        self, 
        latitude: float, 
        longitude: float, 
        query: Optional[str] = None, 
        radius_meters: int = 5000,
        price_tier: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for nearby restaurants.
        
        Returns a list of restaurant dicts with standardized keys:
        - id: str
        - name: str
        - rating: float
        - distance_meters: float
        - price: str (e.g. $, $$, $$$)
        - cuisine: list[str]
        - address: str
        - is_closed: bool
        - url: str
        """
        pass
