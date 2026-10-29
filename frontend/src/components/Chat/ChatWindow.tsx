import React from 'react';
import { MessageList } from './MessageList';
import { ChatInput } from './ChatInput';
import type { ChatMessage } from '../../types/chat';

interface Props {
  messages: ChatMessage[];
  isLoading: boolean;
  loadingMessage?: string;
  onSendMessage: (msg: string) => void;
}

export const ChatWindow: React.FC<Props> = ({ 
  messages, 
  isLoading, 
  loadingMessage, 
  onSendMessage 
}) => {
  return (
    <main className="chat-body">
      <MessageList 
        messages={messages} 
        isLoading={isLoading} 
        loadingMessage={loadingMessage} 
        onQuickAction={onSendMessage}
      />
      <ChatInput 
        onSend={onSendMessage} 
        disabled={isLoading} 
      />
    </main>
  );
};
