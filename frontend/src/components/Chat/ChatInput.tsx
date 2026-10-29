import React, { useState, useRef, useEffect } from 'react';

interface Props {
  onSend: (message: string) => void;
  disabled: boolean;
}

export const ChatInput: React.FC<Props> = ({ onSend, disabled }) => {
  const [input, setInput] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize textarea height to content, up to max limit
  useEffect(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      const newHeight = Math.min(textarea.scrollHeight, 120);
      textarea.style.height = `${Math.max(newHeight, 42)}px`;
    }
  }, [input]);

  const handleSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!input.trim() || disabled) return;
    onSend(input.trim());
    setInput('');
    if (textareaRef.current) {
      textareaRef.current.style.height = '42px';
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <form className="chat-form" onSubmit={handleSubmit}>
      <div className="chat-input-wrapper">
        <textarea
          ref={textareaRef}
          rows={1}
          className="chat-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask for food, dishes, or restaurants nearby..."
          disabled={disabled}
          aria-label="Food search prompt"
        />
      </div>
      <button 
        type="submit" 
        className="chat-submit" 
        disabled={disabled || !input.trim()}
        aria-label="Send message"
      >
        Send
      </button>
    </form>
  );
};
