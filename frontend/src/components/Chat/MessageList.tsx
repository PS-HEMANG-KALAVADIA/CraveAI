import React, { useEffect, useRef } from 'react';
import type { ChatMessage } from '../../types/chat';
import { MessageBubble } from './MessageBubble';
import { TypingIndicator } from './TypingIndicator';
import { QuickActions } from '../QuickActions/QuickActions';

interface Props {
  messages: ChatMessage[];
  isLoading: boolean;
  loadingMessage?: string;
  onQuickAction?: (msg: string) => void;
}

export const MessageList: React.FC<Props> = ({ 
  messages, 
  isLoading, 
  loadingMessage,
  onQuickAction 
}) => {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading, loadingMessage]);

  return (
    <div className="message-list">
      {messages.length === 0 && (
        <div className="empty-state">
          <div className="empty-state-icon" aria-hidden="true">🍲</div>
          <h2>Good food starts with a good recommendation.</h2>
          <p>Tell me what you're craving, and I'll help you find something nearby.</p>
          {onQuickAction && <QuickActions onSelectAction={onQuickAction} />}
        </div>
      )}
      
      {messages.map((msg) => (
        <MessageBubble key={msg.id} message={msg} />
      ))}
      
      {isLoading && <TypingIndicator loadingMessage={loadingMessage} />}
      
      <div ref={bottomRef} />
    </div>
  );
};
