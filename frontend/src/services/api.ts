const API_BASE_URL = 'http://127.0.0.1:8000';

export interface ChatResponse {
  reply: string;
  conversation_id: string;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
}

export interface Conversation {
  id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
}

export interface StreamMeta {
  conversation_id: string;
  metrics: Record<string, number>;
}

export async function sendMessage(
  message: string, 
  conversationId?: string
): Promise<ChatResponse> {
  const response = await fetch(`${API_BASE_URL}/api/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      message,
      conversation_id: conversationId || null,
    }),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to send message to Jarvis.');
  }

  return response.json();
}

export async function fetchConversations(): Promise<Conversation[]> {
  const response = await fetch(`${API_BASE_URL}/api/conversations`);
  if (!response.ok) {
    throw new Error('Failed to fetch conversations.');
  }
  return response.json();
}

export async function fetchMessages(conversationId: string): Promise<Message[]> {
  const response = await fetch(`${API_BASE_URL}/api/conversations/${conversationId}/messages`);
  if (!response.ok) {
    throw new Error('Failed to fetch conversation messages.');
  }
  return response.json();
}

// src/api.ts
export async function streamChatMessage(
  message: string,
  conversationId: string | null,
  onChunk: (textChunk: string) => void,
  onMeta: (meta: StreamMeta) => void,
  onError: (err: string) => void
) {
  try {
    const response = await fetch(`${API_BASE_URL}/api/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, conversation_id: conversationId }),
    });

    if (!response.ok) {
      throw new Error(`Stream request failed (${response.status}).`);
    }

    if (!response.body) throw new Error('ReadableStream not supported.');

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let receivedDoneEvent = false;

    const processEvent = (block: string) => {
      let eventType = 'message';
      const dataLines: string[] = [];

      for (const line of block.split(/\r?\n/)) {
        if (line.startsWith('event:')) {
          eventType = line.slice('event:'.length).trim();
        } else if (line.startsWith('data:')) {
          dataLines.push(line.slice('data:'.length).trimStart());
        }
      }

      const data = dataLines.join('\n');
      if (eventType === 'chunk' && data) {
        const parsed: unknown = JSON.parse(data);
        if (
          typeof parsed !== 'object' ||
          parsed === null ||
          !('text' in parsed) ||
          typeof parsed.text !== 'string'
        ) {
          throw new Error('Received an invalid text chunk from the chat stream.');
        }
        onChunk(parsed.text);
      } else if (eventType === 'meta' && data) {
        onMeta(JSON.parse(data) as StreamMeta);
      } else if (eventType === 'error' && data) {
        let errorMessage = data;
        try {
          const parsed: unknown = JSON.parse(data);
          if (
            typeof parsed === 'object' &&
            parsed !== null &&
            'error' in parsed &&
            typeof parsed.error === 'string'
          ) {
            errorMessage = parsed.error;
          }
        } catch {
          // The SSE data can also be a plain-text error message.
        }
        throw new Error(errorMessage);
      } else if (eventType === 'done') {
        receivedDoneEvent = true;
      }
    };

    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });

      const blocks = buffer.split(/\r?\n\r?\n/);
      buffer = blocks.pop() || '';
      for (const block of blocks) {
        processEvent(block);
      }

      if (done || receivedDoneEvent) break;
    }

    if (buffer.trim()) {
      processEvent(buffer);
    }
    if (!receivedDoneEvent) {
      throw new Error('The chat stream ended before completing the response.');
    }
  } catch (err: unknown) {
    onError(err instanceof Error ? err.message : 'Stream error');
  }
}