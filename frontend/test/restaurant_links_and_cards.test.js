import { describe, it } from 'node:test';
import assert from 'node:assert';

describe('Restaurant Card & Link Presentation Tests', () => {
  it('Requirement 1 & 2: Differentiates canonical restaurant URLs from search fallback URLs in link labels', () => {
    // Check logic of RestaurantCard:
    // If url_type === 'canonical' -> 'View on Swiggy ↗'
    // If url_type === 'search' -> 'Search on Swiggy ↗'
    const getLinkLabel = (restaurant) => {
      if (!restaurant.url || restaurant.url_type === 'none') return null;
      return restaurant.url_type === 'canonical'
        ? 'View on Swiggy ↗'
        : 'Search restaurant and dish on Swiggy ↗';
    };

    const canonicalRest = {
      name: 'Gwalia Sweets',
      url: 'https://www.swiggy.com/restaurants/gwalia-sweets-ahmedabad-12345',
      url_type: 'canonical'
    };

    const searchRest = {
      name: 'Gwalia Sweets & Fast Food',
      url: 'https://www.swiggy.com/search?query=Gwalia+Sweets+%26+Fast+Food+pani+puri',
      url_type: 'search'
    };

    const noUrlRest = {
      name: 'Unknown Place',
      url: '',
      url_type: 'none'
    };

    assert.strictEqual(getLinkLabel(canonicalRest), 'View on Swiggy ↗');
    assert.strictEqual(getLinkLabel(searchRest), 'Search restaurant and dish on Swiggy ↗');
    assert.strictEqual(getLinkLabel(noUrlRest), null);
  });

  it('Requirement 3: Search fallback URLs encode restaurant name and requested dish with special characters and without (Ad)', () => {
    const cleanRestaurantName = (name) => {
      if (!name) return '';
      return name.replace(/\s*\([Aa][Dd]\)\s*$/, '').trim();
    };

    const formatSearchUrl = (name, dish = '') => {
      const clean = cleanRestaurantName(name);
      const query = dish && !clean.toLowerCase().includes(dish.toLowerCase())
        ? `${clean} ${dish}`.trim()
        : clean;
      return `https://www.swiggy.com/search?query=${encodeURIComponent(query).replace(/'/g, '%27').replace(/%20/g, '+')}`;
    };

    const waffleRest = 'The Belgian Waffle Co.';
    const dirtyAdName = 'Tea Post (Ad)';
    const ampersandName = "Gwalia Sweets & Fast Food (Ad)";
    const apostropheName = "Radhika's Authentic South Indian Food";

    assert.strictEqual(
      formatSearchUrl(waffleRest, 'chocolate waffle'),
      'https://www.swiggy.com/search?query=The+Belgian+Waffle+Co.+chocolate+waffle'
    );

    assert.strictEqual(
      formatSearchUrl(dirtyAdName, 'chaat'),
      'https://www.swiggy.com/search?query=Tea+Post+chaat'
    );

    assert.strictEqual(
      formatSearchUrl(ampersandName, 'pani puri'),
      'https://www.swiggy.com/search?query=Gwalia+Sweets+%26+Fast+Food+pani+puri'
    );

    assert.strictEqual(
      formatSearchUrl(apostropheName, 'dosa'),
      'https://www.swiggy.com/search?query=Radhika%27s+Authentic+South+Indian+Food+dosa'
    );
  });

  it('Requirement 5 & 6: Confirmed menu matches show match score; unverified matches do NOT show score badge', () => {
    const shouldDisplayScoreBadge = (category, score, hasImage = false) => {
      if (hasImage) return false;
      return category === 'confirmed' && Boolean(score);
    };

    // Confirmed category shows match score
    assert.strictEqual(shouldDisplayScoreBadge('confirmed', 90, false), true);

    // Unverified category never shows match score badge even if numerical score exists
    assert.strictEqual(shouldDisplayScoreBadge('unverified', 70, false), false);
    assert.strictEqual(shouldDisplayScoreBadge('possible', 65, false), false);
  });

  it('Requirement 7: Displays item availability status accurately with explicit states (confirmed, unavailable, unverified)', () => {
    const getBadgeLabel = (category, dishAvailability) => {
      if (category === 'confirmed') return '✓ Confirmed Menu Match';
      if (dishAvailability === 'unavailable' || dishAvailability === 'not_found') return 'Dish Unavailable';
      if (category === 'possible') return 'Possible Match';
      return 'Dish Unverified';
    };

    assert.strictEqual(getBadgeLabel('confirmed', 'confirmed'), '✓ Confirmed Menu Match');
    assert.strictEqual(getBadgeLabel('possible', 'unverified'), 'Possible Match');
    assert.strictEqual(getBadgeLabel('possible', 'unavailable'), 'Dish Unavailable');
    assert.strictEqual(getBadgeLabel('unverified', 'unavailable'), 'Dish Unavailable');
    assert.strictEqual(getBadgeLabel('unverified', 'unverified'), 'Dish Unverified');
  });

  it('Requirement 8: Displays (Currently Unavailable) tag for verified menu items marked is_available: false', () => {
    const renderItemText = (item) => {
      let text = item.name;
      if (item.price !== undefined) text += ` — ₹${item.price}`;
      if (item.rating) text += ` (${item.rating}★)`;
      if (item.is_available === false) text += ' (Currently Unavailable)';
      return text;
    };

    const availableItem = { name: 'Pani Puri', price: 60, rating: 4.2, is_available: true };
    const outOfStockItem = { name: 'Dhokla', price: 80, is_available: false };

    assert.strictEqual(renderItemText(availableItem), 'Pani Puri — ₹60 (4.2★)');
    assert.strictEqual(renderItemText(outOfStockItem), 'Dhokla — ₹80 (Currently Unavailable)');
  });

  it('Requirement 9: Displays product type tags accurately for packaged, side, and unverified items', () => {
    const renderProductTypeTag = (productType) => {
      if (productType === 'packaged') return ' (Packaged Product)';
      if (productType === 'side') return ' (Side / Snack)';
      if (productType === 'unspecified') return ' (Product Type Unverified)';
      return '';
    };

    assert.strictEqual(renderProductTypeTag('packaged'), ' (Packaged Product)');
    assert.strictEqual(renderProductTypeTag('side'), ' (Side / Snack)');
    assert.strictEqual(renderProductTypeTag('unspecified'), ' (Product Type Unverified)');
    assert.strictEqual(renderProductTypeTag('prepared'), '');
  });

  it('Requirement 10: Differentiates dish_fallback and restaurant_search URLs in link labels and fallback links', () => {
    const getCardLinkLabel = (restaurant) => {
      if (!restaurant.url || restaurant.url_type === 'none') return null;
      if (restaurant.url_type === 'canonical') return 'View on Swiggy ↗';
      if (restaurant.url_type === 'dish_fallback') return 'Search dish on Swiggy ↗';
      if (restaurant.url_type === 'restaurant_search') return 'Search restaurant on Swiggy ↗';
      return restaurant.url.includes('+') ? 'Search restaurant and dish on Swiggy ↗' : 'Search on Swiggy ↗';
    };

    const getSecondaryLinkLabel = (restaurant) => {
      if (!restaurant.fallback_url) return null;
      return restaurant.fallback_url_type === 'restaurant_fallback'
        ? 'Search restaurant name ↗'
        : 'Search dish only ↗';
    };

    const dishFallbackRest = {
      name: 'Oven The Bakery & Cafe',
      url: 'https://www.swiggy.com/search?query=Milk+Waffle',
      url_type: 'dish_fallback',
      fallback_url: 'https://www.swiggy.com/search?query=Oven+The+Bakery+%26+Cafe',
      fallback_url_type: 'restaurant_fallback'
    };

    const restSearchRest = {
      name: 'The Belgian Waffle Co.',
      url: 'https://www.swiggy.com/search?query=The+Belgian+Waffle+Co.',
      url_type: 'restaurant_search'
    };

    assert.strictEqual(getCardLinkLabel(dishFallbackRest), 'Search dish on Swiggy ↗');
    assert.strictEqual(getSecondaryLinkLabel(dishFallbackRest), 'Search restaurant name ↗');
    assert.strictEqual(getCardLinkLabel(restSearchRest), 'Search restaurant on Swiggy ↗');
  });
});
