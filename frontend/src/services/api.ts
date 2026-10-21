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

export async function sendQuery(
  query: string,
  sessionId?: string,
  attachments?: any[]
): Promise<any> {
  const payload: Record<string, any> = { query, session_id: sessionId };
  if (attachments && attachments.length > 0) {
    payload.attachments = attachments;
  }

  const res = await fetch(`${API_BASE}/api/query`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const errText = await res.text();
    throw new Error(errText || `Query failed with status ${res.status}`);
  }

  return await res.json();
}

export async function uploadFile(
  file: File,
  sessionId?: string
): Promise<any> {
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
    const errText = await res.text();
    throw new Error(errText || `File upload failed with status ${res.status}`);
  }

  return await res.json();
}

export async function fetchDataset(datasetId: number): Promise<DatasetData | null> {
  try {
    const res = await fetch(`${API_BASE}/api/datasets/${datasetId}`);
    if (!res.ok) return null;
    return await res.json();
  } catch (err) {
    console.error(`Failed to fetch dataset ${datasetId}:`, err);
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
