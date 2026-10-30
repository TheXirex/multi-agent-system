import type { ChartData, DatasetData, ScriptData, Session } from '../types';

const API_BASE = '';

export async function fetchSessions(): Promise<Session[]> {
  try {
    const res = await fetch(`${API_BASE}/api/sessions`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error('Failed to fetch sessions:', err);
    return [];
  }
}

export async function createSession(title: string = 'New Chat'): Promise<Session | null> {
  try {
    const res = await fetch(`${API_BASE}/api/sessions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error('Failed to create session:', err);
    return null;
  }
}

export async function getSessionDetail(sessionId: string): Promise<any | null> {
  try {
    const res = await fetch(`${API_BASE}/api/sessions/${sessionId}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error(`Failed to get session ${sessionId}:`, err);
    return null;
  }
}

export async function renameSession(sessionId: string, title: string): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/api/sessions/${sessionId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title }),
    });
    return res.ok;
  } catch (err) {
    console.error(`Failed to rename session ${sessionId}:`, err);
    return false;
  }
}

export async function deleteSession(sessionId: string): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/api/sessions/${sessionId}`, {
      method: 'DELETE',
    });
    return res.ok;
  } catch (err) {
    console.error(`Failed to delete session ${sessionId}:`, err);
    return false;
  }
}

export async function extractErrorMessage(res: Response, fallback: string): Promise<string> {
  try {
    const data = await res.json();
    if (data && typeof data === 'object') {
      if (typeof data.detail === 'string') return data.detail;
      if (typeof data.detail === 'object' && data.detail !== null) {
        if (typeof data.detail.message === 'string') return data.detail.message;
        if (typeof data.detail.error === 'string') return data.detail.error;
        return JSON.stringify(data.detail);
      }
      if (typeof data.message === 'string') return data.message;
      if (typeof data.error === 'string') return data.error;
    }
    return JSON.stringify(data);
  } catch {
    try {
      const text = await res.text();
      return text || fallback;
    } catch {
      return fallback;
    }
  }
}

export function formatHumanReadableError(err: any): string {
  let raw = err?.message || (typeof err === 'string' ? err : '');
  if (!raw && err) {
    try {
      raw = String(err);
    } catch {
      raw = 'An unexpected error occurred.';
    }
  }

  if (raw && (raw.startsWith('{') || raw.startsWith('['))) {
    try {
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === 'object') {
        if (typeof parsed.detail === 'string') {
          raw = parsed.detail;
        } else if (typeof parsed.detail === 'object' && parsed.detail !== null) {
          raw = parsed.detail.message || parsed.detail.error || JSON.stringify(parsed.detail);
        } else if (typeof parsed.message === 'string') {
          raw = parsed.message;
        } else if (typeof parsed.error === 'string') {
          raw = parsed.error;
        }
      }
    } catch {
      // Keep raw string if JSON parsing fails
    }
  }

  raw = raw.trim();
  if (raw.toLowerCase().startsWith('error:')) {
    raw = raw.slice(6).trim();
  }
  return raw || 'An unexpected error occurred while processing your request. Please try again.';
}

export async function sendQuery(query: string, sessionId?: string): Promise<any> {
  const res = await fetch(`${API_BASE}/api/query`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, session_id: sessionId }),
  });

  if (!res.ok) {
    const errorMsg = await extractErrorMessage(res, `Query failed with status ${res.status}`);
    throw new Error(errorMsg);
  }

  return await res.json();
}

export async function sendQueryStream(
  query: string,
  sessionId?: string,
  onStatusUpdate?: (action: string) => void
): Promise<any> {
  try {
    const res = await fetch(`${API_BASE}/api/query/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, session_id: sessionId }),
    });

    if (!res.ok) {
      const errorMsg = await extractErrorMessage(res, `Query failed with status ${res.status}`);
      throw new Error(errorMsg);
    }

    if (!res.body) {
      throw new Error('ReadableStream not supported by browser');
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let finalResult: any = null;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      buffer = buffer.split('\r\n').join('\n').split('\r').join('\n');

      while (buffer.indexOf('\n\n') !== -1) {
        const idx = buffer.indexOf('\n\n');
        const block = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);

        const lines = block.split('\n');
        for (const rawLine of lines) {
          const line = rawLine.trim();
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6).trim());
              if (data.type === 'status' && data.action && onStatusUpdate) {
                onStatusUpdate(data.action);
              } else if (data.type === 'result') {
                finalResult = data;
              } else if (data.type === 'error') {
                throw new Error(data.error || 'Server error during execution');
              }
            } catch (jsonErr: any) {
              if (jsonErr.message && !jsonErr.message.includes('JSON')) {
                throw jsonErr;
              }
            }
          }
        }
      }
    }

    if (finalResult) {
      return finalResult;
    }
  } catch (err: any) {
    if (err.message && !err.message.includes('Failed to fetch') && !err.message.includes('ReadableStream')) {
      throw err;
    }
    console.warn('Streaming failed, falling back to standard query:', err);
  }

  return await sendQuery(query, sessionId);
}

export async function uploadFile(file: File, sessionId?: string): Promise<any> {
  const formData = new FormData();
  formData.append('file', file);
  if (sessionId) {
    formData.append('session_id', sessionId);
  }

  const res = await fetch(`${API_BASE}/api/upload`, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    const errorMsg = await extractErrorMessage(res, `File upload failed with status ${res.status}`);
    throw new Error(errorMsg);
  }

  return await res.json();
}

export async function fetchTable(tableName: string, sessionId?: string): Promise<DatasetData | null> {
  try {
    const url = sessionId
      ? `${API_BASE}/api/tables/${encodeURIComponent(tableName)}?session_id=${encodeURIComponent(sessionId)}`
      : `${API_BASE}/api/tables/${encodeURIComponent(tableName)}`;
    const res = await fetch(url);
    if (!res.ok) return null;
    return await res.json();
  } catch (err) {
    console.error(`Failed to fetch table ${tableName}:`, err);
    return null;
  }
}

export async function fetchChart(chartId: number): Promise<ChartData | null> {
  try {
    const res = await fetch(`${API_BASE}/api/charts/${chartId}`);
    if (!res.ok) return null;
    return await res.json();
  } catch (err) {
    console.error(`Failed to fetch chart ${chartId}:`, err);
    return null;
  }
}

export async function fetchScript(scriptId: number): Promise<ScriptData | null> {
  try {
    const res = await fetch(`${API_BASE}/api/scripts/${scriptId}`);
    if (!res.ok) return null;
    return await res.json();
  } catch (err) {
    console.error(`Failed to fetch script ${scriptId}:`, err);
    return null;
  }
}
