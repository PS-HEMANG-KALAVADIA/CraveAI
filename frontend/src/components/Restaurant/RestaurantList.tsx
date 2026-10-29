import React from 'react';
import type { RankedRestaurant } from '../../types/restaurant';
import { RestaurantCard } from './RestaurantCard';

interface Props {
  restaurants: RankedRestaurant[];
}

export const RestaurantList: React.FC<Props> = ({ restaurants }) => {
  if (!restaurants || restaurants.length === 0) return null;
  
  return (
    <div className="restaurant-list">
      {restaurants.map((r, i) => (
        <RestaurantCard key={r.restaurant.id || i} data={r} />
      ))}
    </div>
  );
};
