import React from 'react';

interface Props {
  loadingMessage?: string;
}

export const TypingIndicator: React.FC<Props> = ({ loadingMessage }) => {
  return (
    <div className="message bot-message typing-indicator-container">
      <div className="message-avatar" aria-hidden="true">🍲</div>
      <div className="message-content typing-content">
        <span className="dot"></span>
        <span className="dot"></span>
        <span className="dot"></span>
        {loadingMessage && <span className="loading-text">{loadingMessage}</span>}
      </div>
    </div>
  );
};
