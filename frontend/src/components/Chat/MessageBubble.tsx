import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { ChatMessage } from '../../types/chat';
import { RestaurantList } from '../Restaurant/RestaurantList';

interface Props {
  message: ChatMessage;
}

export const MessageBubble: React.FC<Props> = ({ message }) => {
  const isUser = message.role === 'user';
  
  return (
    <div className={`message ${isUser ? 'user-message' : 'bot-message'}`}>
      {!isUser && (
        <div className="message-avatar" aria-hidden="true">
          🍲
        </div>
      )}
      <div className="message-content">
        {!isUser && message.tools_used && message.tools_used.length > 0 && (
          <div className="tools-used">
            <span className="tools-used-title">Activity</span>
            <ul>
              {message.tools_used.map((tool, i) => {
                const isFailed = tool.includes('_failed');
                return (
                  <li key={i} className={isFailed ? 'tool-failed' : 'tool-success'}>
                    <span className="tool-indicator">{isFailed ? '—' : '✓'}</span>
                    <span className="tool-text">{formatToolName(tool, message)}</span>
                  </li>
                );
              })}
            </ul>
          </div>
        )}

        <div className="message-text">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
        </div>
        
        {!isUser && message.restaurants && message.restaurants.length > 0 && (
          <RestaurantList restaurants={message.restaurants} />
        )}
      </div>
    </div>
  );
};

function formatToolName(tool: string, message?: ChatMessage): string {
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

