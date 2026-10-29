import type { ChatMessage, LocationState } from '../types/chat';
export async function sendChatMessage(
  message: string, 
  conversation: ChatMessage[], 
  locationState: LocationState,
  onProgress: (msg: string) => void,
  onResult: (data: any) => void,
  onError: (error: string) => void
) {
  try {
    const payload: any = {
      message,
      conversation: conversation.map(m => ({
        role: m.role,
        content: m.content
      }))
    };

    payload.location_status = locationState.status;
    if (locationState.status === 'available' && locationState.latitude && locationState.longitude) {
      payload.location = {
        latitude: locationState.latitude,
        longitude: locationState.longitude
      };
    }

    const response = await fetch('http://localhost:8000/api/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      throw new Error(`API Error: ${response.statusText}`);
    }

    if (!response.body) {
      throw new Error("ReadableStream not yet supported in this browser.");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");

    let done = false;
    while (!done) {
      const { value, done: readerDone } = await reader.read();
      done = readerDone;
      if (value) {
        const chunk = decoder.decode(value, { stream: true });
        
        // SSE lines come as "data: {...}\n\n"
        const lines = chunk.split('\n');
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const dataStr = line.substring(6);
              const data = JSON.parse(dataStr);
              
              if (data.type === 'progress') {
                onProgress(data.message);
              } else if (data.type === 'result') {
                onResult(data);
              } else if (data.type === 'error') {
                onError(data.message);
              }
            } catch (e) {
              console.warn("Failed to parse SSE chunk:", line, e);
            }
          }
        }
      }
    }
  } catch (err: any) {
    onError(err.message || 'Unknown network error');
  }
}
