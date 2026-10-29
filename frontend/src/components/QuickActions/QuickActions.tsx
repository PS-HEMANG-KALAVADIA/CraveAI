import React from 'react';

interface Props {
  onSelectAction: (message: string) => void;
}

export const QuickActions: React.FC<Props> = ({ onSelectAction }) => {
  return (
    <div className="quick-actions" aria-label="Quick conversational suggestions">
      <button 
        type="button" 
        className="chip" 
        onClick={() => onSelectAction("Find good food nearby")}
      >
        Find food nearby
      </button>
      <button 
        type="button" 
        className="chip" 
        onClick={() => onSelectAction("I only have ₹250.")}
      >
        Something budget-friendly
      </button>
      <button 
        type="button" 
        className="chip" 
        onClick={() => onSelectAction("What food do you recommend for today's weather?")}
      >
        Food for today's weather
      </button>
      <button 
        type="button" 
        className="chip" 
        onClick={() => onSelectAction("I want to experience Jaipur food.")}
      >
        Explore local dishes
      </button>
    </div>
  );
};
