export interface LocationState {
  status: 'unknown' | 'available' | 'denied' | 'unavailable' | 'requesting';
  latitude?: number;
  longitude?: number;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  tools_used?: string[];
  restaurants?: any[]; // To be updated with Restaurant type
}
