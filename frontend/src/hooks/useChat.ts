import { useState, useCallback } from 'react';
import type { ChatMessage, LocationState } from '../types/chat';
import { sendChatMessage } from '../services/api';

export interface SwiggyAuthHandler {
  updateFromAuthError?: (type: 'reauth_required' | 'not_connected') => void;
  checkStatus?: () => void;
}

export function useChat(locationState: LocationState, swiggyAuth?: SwiggyAuthHandler) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [loadingMessage, setLoadingMessage] = useState<string | undefined>();
  const [error, setError] = useState<string | null>(null);

  const sendMessage = useCallback(async (text: string) => {
    // 1. Add user message instantly
    const userMsg: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: text
    };
    
    setMessages(prev => [...prev, userMsg]);
    setIsLoading(true);
    setLoadingMessage("Sending request...");
    setError(null);

    // 2. Call API with conversation history
    await sendChatMessage(
      text,
      messages, // Pass history
      locationState,
      (progressMsg) => {
        setLoadingMessage(progressMsg);
      },
      (resultData) => {
        // Specifically detect authentication errors and update connection status immediately
        if (resultData.auth_status === 'reauth_required') {
          swiggyAuth?.updateFromAuthError?.('reauth_required');
        } else if (resultData.auth_status === 'not_connected') {
          swiggyAuth?.updateFromAuthError?.('not_connected');
        } else if (resultData.response) {
          const respLower = resultData.response.toLowerCase();
          if (respLower.includes('session expired') || respLower.includes('re-authenticate')) {
            swiggyAuth?.updateFromAuthError?.('reauth_required');
          } else if (respLower.includes('swiggy authentication missing') || (respLower.includes('connect to swiggy') && respLower.includes('swiggy/login'))) {
            swiggyAuth?.updateFromAuthError?.('not_connected');
          }
        }

        const botMsg: ChatMessage = {
          id: (Date.now() + 1).toString(),
          role: 'assistant',
          content: resultData.response,
          tools_used: resultData.tools_used,
          restaurants: resultData.restaurants
        };
        setMessages(prev => [...prev, botMsg]);
        setIsLoading(false);
        setLoadingMessage(undefined);
      },
      (errMsg) => {
        setError(errMsg);
        setIsLoading(false);
        setLoadingMessage(undefined);

        const lower = errMsg.toLowerCase();
        if (lower.includes('session expired') || lower.includes('re-authenticate')) {
          swiggyAuth?.updateFromAuthError?.('reauth_required');
        } else if (lower.includes('swiggy authentication missing')) {
          swiggyAuth?.updateFromAuthError?.('not_connected');
        }
      }
    );
  }, [messages, locationState, swiggyAuth]);

  return {
    messages,
    isLoading,
    loadingMessage,
    error,
    sendMessage
  };
}
