export interface ScoreBreakdown {
  food_match: number;
  rating: number;
  distance: number;
  budget_fit: number;
  total_score: number;
}

export interface Restaurant {
  id?: string;
  name?: string;
  rating?: number;
  price?: string;
  distance_meters?: number;
  cuisine?: string[];
  url?: string;
  url_type?: 'canonical' | 'search' | 'dish_fallback' | 'restaurant_search' | 'none';
  fallback_url?: string;
  fallback_url_type?: string;
  dish_availability?: 'confirmed' | 'not_found' | 'unavailable' | 'unverified';
  [key: string]: any;
}

export interface MatchedItem {
  name: string;
  price?: number;
  rating?: number;
  is_available?: boolean;
  product_type?: 'prepared' | 'packaged' | 'side' | 'unspecified';
  product_type_label?: string;
}

export interface RankedRestaurant {
  restaurant: Restaurant;
  score: number;
  score_breakdown: ScoreBreakdown;
  match_category?: 'confirmed' | 'possible' | 'unverified';
  matched_items?: MatchedItem[];
  match_reason?: string;
  dish_availability?: 'confirmed' | 'not_found' | 'unavailable' | 'unverified';
}
