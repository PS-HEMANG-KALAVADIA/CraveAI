import httpx
import logging
import re
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"

COMMON_NON_CITIES = {
    "weather", "today", "tomorrow", "now", "here", "current", "food", 
    "restaurant", "restaurants", "hello", "hi", "hey", "please", 
    "help", "me", "my", "location", "coordinates", "the", "a", "an",
    "is", "it", "what", "whats", "how", "show", "tell", "check", "get",
    "forecast", "rain", "temperature", "cold", "hot", "cloudy", "sunny",
    "good", "great", "places", "place", "eat", "eating", "dinner", "lunch",
    "breakfast", "spicy", "sweet", "nearby", "near", "around"
}

def extract_city(text: str) -> Optional[str]:
    """
    Extract a potential city name from user text.
    Handles queries like:
    - 'What's the weather in Ahmedabad?'
    - 'Will it rain tomorrow in Ahmedabad?'
    - 'Weather for Jaipur'
    - 'Ahmedabad weather'
    - 'Ahmedabad'
    Returns None if no clear city is mentioned.
    """
    if not text:
        return None

    cleaned = text.strip().rstrip("?.!;,")
    
    # Pattern 1: ... in/at/around <City> ... or (weather/forecast) for <City>
    # e.g., "weather in Ahmedabad", "rain tomorrow in Ahmedabad", "places in Ahmedabad", "forecast for Jaipur"
    m = re.search(
        r'\b(?:in|at|around)\s+([A-Za-z\s]+?)(?:\s+(?:today|tomorrow|now|right now|this week|next week)|\?|$|\.)',
        cleaned,
        re.IGNORECASE
    )
    if not m:
        m = re.search(
            r'\b(?:weather|forecast|temperature|rain)\s+for\s+([A-Za-z\s]+?)(?:\s+(?:today|tomorrow|now|right now|this week|next week)|\?|$|\.)',
            cleaned,
            re.IGNORECASE
        )
    if m:
        candidate = m.group(1).strip()
        words = candidate.lower().split()
        if candidate.lower() not in COMMON_NON_CITIES and not all(w in COMMON_NON_CITIES for w in words) and len(candidate) > 1:
            return candidate

    # Pattern 2: <City> weather / forecast
    # e.g. "Ahmedabad weather", "Please check Jaipur forecast"
    m = re.search(
        r'^(?:(?:please|can you|could you)\s+)?(?:check\s+|tell me\s+|show\s+)?([A-Za-z\s]+?)\s+(?:weather|forecast)',
        cleaned,
        re.IGNORECASE
    )
    if m:
        candidate = m.group(1).strip()
        words = candidate.lower().split()
        if candidate.lower() not in COMMON_NON_CITIES and not all(w in COMMON_NON_CITIES for w in words) and len(candidate) > 1:
            return candidate

    # Pattern 3: Direct short input (e.g. user replied 'Ahmedabad', 'Ahmedabad, Gujarat')
    clean_words = [w.strip(".,;:!?") for w in cleaned.split()]
    clean_words = [w for w in clean_words if w]
    if 1 <= len(clean_words) <= 3 and all(w.isalpha() for w in clean_words):
        if not any(w.lower() in COMMON_NON_CITIES for w in clean_words):
            return " ".join(clean_words)

    return None


PROMINENT_INDIAN_CITIES = [
    "Ahmedabad", "Mumbai", "Delhi", "Bengaluru", "Bangalore", "Hyderabad", 
    "Chennai", "Kolkata", "Jaipur", "Surat", "Pune", "Lucknow", "Kanpur", 
    "Nagpur", "Indore", "Thane", "Bhopal", "Visakhapatnam", "Vadodara", 
    "Patna", "Ghaziabad", "Ludhiana", "Agra", "Nashik", "Faridabad", 
    "Meerut", "Rajkot", "Varanasi", "Srinagar", "Aurangabad", "Dhanbad", 
    "Amritsar", "Prayagraj", "Ranchi", "Howrah", "Coimbatore", "Jabalpur", 
    "Gwalior", "Vijayawada", "Jodhpur", "Madurai", "Raipur", "Kota", 
    "Chandigarh", "Guwahati", "Solapur", "Hubli", "Mysore", "Tiruchirappalli", 
    "Bareilly", "Aligarh", "Tiruppur", "Gurgaon", "Gurugram", "Moradabad", 
    "Jalandhar", "Bhubaneswar", "Salem", "Warangal", "Jalgaon", "Guntur", "Dehradun"
]

def find_city_spelling_suggestion(candidate: str, cutoff: float = 0.70) -> Optional[str]:
    """Find a likely city spelling match among prominent cities using difflib."""
    import difflib
    if not candidate or len(candidate.strip()) < 3:
        return None
    c_lower = candidate.strip().lower()
    city_map = {c.lower(): c for c in PROMINENT_INDIAN_CITIES}
    matches = difflib.get_close_matches(c_lower, list(city_map.keys()), n=1, cutoff=cutoff)
    if matches:
        return city_map[matches[0]]
    return None

async def geocode_city(city_name: str) -> Optional[Dict[str, Any]]:
    """
    Resolve a city name to latitude and longitude coordinates using Open-Meteo Geocoding API.
    Detects and corrects likely spelling typos (e.g. 'ahmedabaf' -> 'Ahmedabad').
    Never invents coordinates. Returns None if city cannot be resolved or on error.
    """
    if not city_name or not city_name.strip():
        return None

    cleaned_name = city_name.strip()
    corrected_from = None

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                GEOCODING_URL,
                params={"name": cleaned_name, "count": 1, "language": "en", "format": "json"}
            )
            response.raise_for_status()
            data = response.json()
            results = data.get("results")

            # If no direct match, check for likely city spelling typo
            if not results and len(cleaned_name) >= 4:
                suggested = find_city_spelling_suggestion(cleaned_name)
                if suggested:
                    logger.info(f"City typo detected: '{cleaned_name}' -> suggested '{suggested}'")
                    resp2 = await client.get(
                        GEOCODING_URL,
                        params={"name": suggested, "count": 1, "language": "en", "format": "json"}
                    )
                    if resp2.status_code == 200:
                        data2 = resp2.json()
                        results = data2.get("results")
                        if results:
                            corrected_from = cleaned_name

            if results and len(results) > 0:
                first = results[0]
                res = {
                    "name": first.get("name", cleaned_name),
                    "latitude": float(first["latitude"]),
                    "longitude": float(first["longitude"]),
                    "country": first.get("country"),
                    "admin1": first.get("admin1"),
                    "timezone": first.get("timezone")
                }
                if corrected_from:
                    res["corrected_from"] = corrected_from
                return res
    except Exception as e:
        logger.error(f"Geocoding error for '{city_name}': {e}")

    return None
