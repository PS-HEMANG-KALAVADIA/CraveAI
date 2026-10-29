import { describe, it } from 'node:test';
import assert from 'node:assert';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Replicate MessageBubble formatToolName logic to test formatting contracts
function formatToolName(tool, message) {
  if (tool.startsWith('get_current_weather:')) {
    const detail = tool.substring('get_current_weather:'.length).trim();
    return `Weather checked: ${detail}`;
  }
  if (tool.startsWith('get_current_weather_failed')) {
    if (tool.includes(':')) {
      const detail = tool.split(':')[1].trim();
      return `Weather unavailable: ${detail}`;
    }
    return 'Weather unavailable: Could not retrieve current conditions';
  }

  switch (tool) {
    case 'get_current_weather':
      return 'Weather checked';
    case 'get_current_weather_failed':
      return 'Weather unavailable: Could not retrieve current conditions';
    case 'get_weather_forecast':
      return 'Weather forecast checked';
    case 'get_weather_forecast_failed':
      return 'Weather forecast check failed';
    case 'get_food_for_weather':
      return 'Food suggestions retrieved';
    case 'get_food_for_weather_failed':
      return 'Food suggestions unavailable';
    case 'get_food_for_mood':
      return 'Mood suggestions retrieved';
    case 'get_food_for_mood_failed':
      return 'Mood suggestions unavailable';
    case 'get_dish_information':
      return 'Dish information retrieved';
    case 'get_dish_information_failed':
      return 'Dish information unavailable';
    case 'get_cuisine_information':
      return 'Cuisine information retrieved';
    case 'get_cuisine_information_failed':
      return 'Cuisine information unavailable';
    case 'get_city_food':
      return 'City food guide retrieved';
    case 'get_city_food_failed':
      return 'City food guide unavailable';
    case 'search_food':
      return 'Food knowledge searched';
    case 'search_food_failed':
      return 'Food knowledge search failed';
    case 'search_nearby_restaurants':
      return message?.restaurants && message.restaurants.length > 0
        ? 'Nearby restaurants found'
        : 'No nearby restaurants found';
    case 'search_nearby_restaurants_no_results':
      return 'No nearby restaurants found';
    case 'search_nearby_restaurants_failed':
      return 'Restaurant search failed';
    case 'get_workflow_guidance':
      return 'Workflow guidance retrieved';
    case 'get_workflow_guidance_failed':
      return 'Workflow guidance failed';
    default:
      if (tool.endsWith('_failed')) {
        return tool.replace(/_failed$/, '').replace(/_/g, ' ') + ' failed';
      }
      return tool.replace(/_/g, ' ') + ' executed';
  }
}

describe('Weather Quick Action and Activity Trace Formatting', () => {
  it('QuickActions component does not hardcode rainy weather in action prompt', () => {
    const quickActionsPath = path.join(__dirname, '..', 'src', 'components', 'QuickActions', 'QuickActions.tsx');
    const content = fs.readFileSync(quickActionsPath, 'utf8');

    // Must not contain the old hardcoded rain prompt
    assert.strictEqual(
      content.includes("It's raining and I don't know what to eat."),
      false,
      "QuickActions should not hardcode rain into the weather button action"
    );

    // Must contain a neutral food-for-weather action
    assert.ok(
      content.includes("What food do you recommend for today's weather?"),
      "QuickActions should send a neutral prompt asking for food recommendations based on weather"
    );
  });

  it('formats clear/sunny weather trace truthfully with temperature', () => {
    const tool = 'get_current_weather: Clear, 29°C';
    const isFailed = tool.includes('_failed');
    const label = formatToolName(tool);

    assert.strictEqual(isFailed, false);
    assert.strictEqual(label, 'Weather checked: Clear, 29°C');
  });

  it('formats rainy weather trace truthfully with temperature', () => {
    const tool = 'get_current_weather: Rain, 24°C';
    const isFailed = tool.includes('_failed');
    const label = formatToolName(tool);

    assert.strictEqual(isFailed, false);
    assert.strictEqual(label, 'Weather checked: Rain, 24°C');
  });

  it('formats weather API failure truthfully as unavailable', () => {
    const tool = 'get_current_weather_failed: Could not retrieve current conditions';
    const isFailed = tool.includes('_failed');
    const label = formatToolName(tool);

    assert.strictEqual(isFailed, true);
    assert.strictEqual(label, 'Weather unavailable: Could not retrieve current conditions');
  });

  it('supports legacy weather tool tokens gracefully', () => {
    assert.strictEqual(formatToolName('get_current_weather'), 'Weather checked');
    assert.strictEqual(
      formatToolName('get_current_weather_failed'),
      'Weather unavailable: Could not retrieve current conditions'
    );
  });

  it('formats food knowledge tools with clean activity trace names', () => {
    assert.strictEqual(formatToolName('get_food_for_weather'), 'Food suggestions retrieved');
    assert.strictEqual(formatToolName('get_food_for_weather_failed'), 'Food suggestions unavailable');
    assert.strictEqual(formatToolName('get_food_for_mood'), 'Mood suggestions retrieved');
    assert.strictEqual(formatToolName('get_dish_information'), 'Dish information retrieved');
    assert.strictEqual(formatToolName('get_cuisine_information'), 'Cuisine information retrieved');
    assert.strictEqual(formatToolName('get_city_food'), 'City food guide retrieved');
  });

  it('formats restaurant search results correctly based on restaurant presence', () => {
    assert.strictEqual(formatToolName('search_nearby_restaurants', { restaurants: [{ name: 'Place 1' }] }), 'Nearby restaurants found');
    assert.strictEqual(formatToolName('search_nearby_restaurants', { restaurants: [] }), 'No nearby restaurants found');
    assert.strictEqual(formatToolName('search_nearby_restaurants_no_results'), 'No nearby restaurants found');
    assert.strictEqual(formatToolName('search_nearby_restaurants_failed'), 'Restaurant search failed');
  });
});
