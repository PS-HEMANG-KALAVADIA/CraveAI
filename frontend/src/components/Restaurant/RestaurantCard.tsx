import React from 'react';
import type { RankedRestaurant, MatchedItem } from '../../types/restaurant';

interface Props {
  data: RankedRestaurant;
}

export const RestaurantCard: React.FC<Props> = ({ data }) => {
  const { restaurant, score, match_category, matched_items, match_reason, dish_availability } = data;
  
  const category = match_category || restaurant.match_category || 'unverified';
  const dishAvail = dish_availability || restaurant.dish_availability;
  const verifiedItems: MatchedItem[] = (matched_items || restaurant.matched_items || []) as MatchedItem[];
  const reason = match_reason || restaurant.match_reason;
  const imageUrl = restaurant.image_url || (restaurant as any).image;

  return (
    <article className={`restaurant-card category-${category}`}>
      <div className="restaurant-card-header">
        <div className="restaurant-title-area">
          <h4>{restaurant.name || "Unknown Restaurant"}</h4>
          <div className="badge-row">
            {category === 'confirmed' && (
              <span className="match-category-badge match-confirmed">✓ Confirmed Menu Match</span>
            )}
            {category === 'possible' && dishAvail !== 'unavailable' && (
              <span className="match-category-badge match-possible">Possible Match</span>
            )}
            {(dishAvail === 'unavailable' || dishAvail === 'not_found') && category !== 'confirmed' && (
              <span className="match-category-badge match-unavailable">Dish Unavailable</span>
            )}
            {category === 'unverified' && dishAvail !== 'unavailable' && dishAvail !== 'not_found' && (
              <span className="match-category-badge match-unverified">Dish Unverified</span>
            )}
            {restaurant.is_closed !== undefined && (
              <span className={`status-tag ${restaurant.is_closed ? 'closed' : 'open'}`}>
                {restaurant.is_closed ? 'Closed' : 'Open'}
              </span>
            )}
          </div>
        </div>
        {imageUrl && (
          <img 
            src={imageUrl} 
            alt={restaurant.name || "Restaurant"} 
            className="restaurant-thumb"
            loading="lazy" 
          />
        )}
        {!imageUrl && category === 'confirmed' && score ? (
          <span className="score-badge">Match: {score}</span>
        ) : null}
      </div>
      
      {verifiedItems.length > 0 && (
        <div className="matched-dishes-box">
          <div className="matched-dishes-title">Verified on Menu</div>
          <ul className="matched-dishes-list">
            {verifiedItems.map((item: MatchedItem, idx: number) => (
              <li key={idx} className="matched-dish-item">
                <span className="dish-name">{item.name}</span>
                {item.price !== undefined && <span className="dish-price"> — ₹{item.price}</span>}
                {item.rating && <span className="dish-rating"> ({item.rating}★)</span>}
                {item.product_type === 'packaged' && (
                  <span className="product-type-tag packaged"> (Packaged Product)</span>
                )}
                {item.product_type === 'side' && (
                  <span className="product-type-tag side"> (Side / Snack)</span>
                )}
                {item.product_type === 'unspecified' && (
                  <span className="product-type-tag unspecified"> (Product Type Unverified)</span>
                )}
                {item.is_available === false && (
                  <span className="dish-unavailable-tag"> (Currently Unavailable)</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {category !== 'confirmed' && reason && (
        <div className="match-reason-note">{reason}</div>
      )}
      
      <div className="restaurant-meta">
        {restaurant.rating && <span className="restaurant-rating">★ {restaurant.rating}</span>}
        {restaurant.price && <span>{restaurant.price}</span>}
        {restaurant.distance_meters !== undefined && (
          <span>{(restaurant.distance_meters / 1000).toFixed(1)} km</span>
        )}
        {restaurant.address && <span className="restaurant-address">{restaurant.address}</span>}
      </div>
      
      {restaurant.cuisine && restaurant.cuisine.length > 0 && (
        <div className="restaurant-cuisine">
          {restaurant.cuisine.join(' · ')}
        </div>
      )}
      
      {restaurant.url && restaurant.url_type !== 'none' && (
        <div className="restaurant-links-row">
          <a
            href={restaurant.url}
            target="_blank"
            rel="noopener noreferrer"
            className="restaurant-link"
            title={
              restaurant.url_type === 'canonical'
                ? 'Verified official restaurant page on Swiggy'
                : restaurant.url_type === 'dish_fallback'
                ? 'Dish-focused search fallback — outlet availability on Swiggy may vary by location'
                : 'Search on Swiggy'
            }
          >
            {restaurant.url_type === 'canonical'
              ? 'View on Swiggy ↗'
              : restaurant.url_type === 'dish_fallback'
              ? 'Search dish on Swiggy ↗'
              : restaurant.url_type === 'restaurant_search'
              ? 'Search restaurant on Swiggy ↗'
              : (restaurant.url.includes('+') ? 'Search restaurant and dish on Swiggy ↗' : 'Search on Swiggy ↗')}
          </a>
          {restaurant.fallback_url && (
            <a
              href={restaurant.fallback_url}
              target="_blank"
              rel="noopener noreferrer"
              className="restaurant-secondary-link"
              title="Alternative search link"
            >
              {restaurant.fallback_url_type === 'restaurant_fallback'
                ? 'Search restaurant name ↗'
                : 'Search dish only ↗'}
            </a>
          )}
        </div>
      )}
      {restaurant.url_type === 'dish_fallback' && (
        <div className="search-disclaimer-note">
          Dish-focused search fallback — outlet availability on Swiggy may vary by delivery location.
        </div>
      )}
    </article>
  );
};
