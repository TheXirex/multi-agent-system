import { useEffect, useState, useCallback } from 'react';
import type { Message, Session, TurnArtifacts, ChartData } from './types';
import * as api from './services/api';
import { Header } from './components/Header';
import { Sidebar } from './components/Sidebar';
import { Chat } from './components/Chat';
import { Workspace } from './components/Workspace';

function extractCodeBlock(text: string, lang: string): string | null {
  if (!text) return null;
  const lower = text.toLowerCase();
  const marker = '```' + lang.toLowerCase();
  const startIdx = lower.indexOf(marker);
  if (startIdx === -1) return null;

  const afterMarker = startIdx + marker.length;
  const lineEndIdx = text.indexOf('\n', afterMarker);
  if (lineEndIdx === -1) return null;

  const endIdx = text.indexOf('```', lineEndIdx);
  if (endIdx === -1) return null;

  return text.substring(lineEndIdx + 1, endIdx).trim();
}

export function App() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);

  const [messages, setMessages] = useState<Message[]>([]);
  const [turns, setTurns] = useState<TurnArtifacts[]>([]);
  const [currentTurnIndex, setCurrentTurnIndex] = useState(0);
  const [isBusy, setIsBusy] = useState(false);
  const [currentAction, setCurrentAction] = useState<string | null>(null);

  // Scroll to assistant message card in chat
  const handleScrollToMessage = useCallback((turnIndex: number) => {
    if (!turnIndex) return;
    const el = document.getElementById(`chat-turn-${turnIndex}`);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      el.classList.add('turn-highlight-active');
      setTimeout(() => {
        el.classList.remove('turn-highlight-active');
      }, 1800);
    }
  }, []);

  // Load a session's messages and hydrate artifacts
  const loadSession = useCallback(async (sessionId: string) => {
    setIsBusy(true);
    setCurrentAction('Loading session history...');
    setCurrentSessionId(sessionId);

    const detail = await api.getSessionDetail(sessionId);
    if (!detail) {
      setIsBusy(false);
      setCurrentAction(null);
      return;
    }

    const rawMessages: any[] = detail.messages || [];
    const hydratedMessages: Message[] = [];
    const loadedTurns: TurnArtifacts[] = [];
    let assistantTurnCounter = 0;
    let lastUserQuery = '';

    for (const msg of rawMessages) {
      const role = msg.role || 'user';
      const content = msg.content || '';
      const meta = msg.metadata || {};

      if (role === 'user') {
        lastUserQuery = content;
        hydratedMessages.push({
          id: msg.id,
          session_id: sessionId,
          role: 'user',
          content,
          metadata: meta,
          created_at: msg.created_at,
        });
      } else {
        assistantTurnCounter += 1;
        const currentTurn = assistantTurnCounter;

        // Fetch table data
        let datasetData = null;
        if (meta.table_names && meta.table_names.length > 0) {
          datasetData = await api.fetchTable(meta.table_names[0], sessionId);
        } else if (meta.dataset_id) {
          datasetData = await api.fetchDataset(meta.dataset_id);
        }

        // Fetch charts
        const chartIds: number[] = meta.chart_ids || (meta.chart_id ? [meta.chart_id] : []);
        const chartsData: ChartData[] = [];
        for (const cid of chartIds) {
          const ch = await api.fetchChart(cid);
          if (ch) chartsData.push(ch);
        }

        // Resolve Python script and SQL query
        let pythonScript: string | null = meta.code || null;
        let sqlQuery: string | null = meta.sql_query || datasetData?.query || null;

        const pythonScriptId = meta.python_script_id || (meta.script_id && !meta.sql_script_id ? meta.script_id : null);
        if (!pythonScript && pythonScriptId) {
          const sc = await api.fetchScript(pythonScriptId);
          if (sc && sc.script) {
            if (sc.language === 'python') pythonScript = sc.script;
            else if (sc.language === 'sql' && !sqlQuery) sqlQuery = sc.script;
          }
        }

        const sqlScriptId = meta.sql_script_id || (meta.script_id && meta.script_id !== pythonScriptId ? meta.script_id : null);
        if (!sqlQuery && sqlScriptId) {
          const sc = await api.fetchScript(sqlScriptId);
          if (sc && sc.script) {
            if (sc.language === 'sql') sqlQuery = sc.script;
            else if (sc.language === 'python' && !pythonScript) pythonScript = sc.script;
          }
        }

        // Fallbacks via markdown parsing
        if (!sqlQuery) sqlQuery = extractCodeBlock(content, 'sql');
        if (!pythonScript) pythonScript = extractCodeBlock(content, 'python');

        const messageObj: Message = {
          id: msg.id,
          session_id: sessionId,
          role: 'assistant',
          content,
          metadata: meta,
          created_at: msg.created_at,
          turnIndex: currentTurn,
          datasetData,
          chartsData,
          pythonScript,
          sqlQuery,
        };
        hydratedMessages.push(messageObj);

        const turnObj: TurnArtifacts = {
          turnIndex: currentTurn,
          totalTurns: 0,
          userQuery: lastUserQuery,
          messageContent: content,
          metadata: meta,
          datasetData,
          chartsData,
          pythonScript,
          sqlQuery,
        };
        loadedTurns.push(turnObj);
      }
    }

    // Update totalTurns count
    for (const t of loadedTurns) {
      t.totalTurns = loadedTurns.length;
    }

    setMessages(hydratedMessages);
    setTurns(loadedTurns);
    setCurrentTurnIndex(loadedTurns.length);
    setIsBusy(false);
    setCurrentAction(null);
  }, []);

  // Initial load: fetch sessions
  useEffect(() => {
    async function init() {
      const sessList = await api.fetchSessions();
      setSessions(sessList);
      if (sessList.length > 0) {
        await loadSession(sessList[0].id);
      } else {
        const newSess = await api.createSession('New Chat');
        if (newSess) {
          setSessions([newSess]);
          await loadSession(newSess.id);
        }
      }
    }
    init();
  }, [loadSession]);

  const handleNewSession = async () => {
    if (isBusy) return;
    const newSess = await api.createSession('New Chat');
    if (newSess) {
      setSessions((prev) => [newSess, ...prev]);
      await loadSession(newSess.id);
    }
  };

  const handleSidebarRename = async (sessionId: string, newTitle: string) => {
    const ok = await api.renameSession(sessionId, newTitle);
    if (ok) {
      setSessions((prev) =>
        prev.map((s) => (s.id === sessionId ? { ...s, title: newTitle } : s))
      );
    }
  };

  const handleDeleteSession = async (sessionId: string) => {
    const ok = await api.deleteSession(sessionId);
    if (ok) {
      const remaining = sessions.filter((s) => s.id !== sessionId);
      setSessions(remaining);
      if (sessionId === currentSessionId) {
        if (remaining.length > 0) {
          await loadSession(remaining[0].id);
        } else {
          await handleNewSession();
        }
      }
    }
  };

  const handleSendQuery = async (text: string, attachedFile?: File | null) => {
    if (isBusy || (!text && !attachedFile)) return;

    setIsBusy(true);

    try {
      // 1. File Upload Flow
      if (attachedFile) {
        setCurrentAction('Ingesting dataset...');
        const userMsg: Message = {
          role: 'user',
          content: text || `Uploaded file: ${attachedFile.name}`,
          metadata: {
            attachments: [
              {
                filename: attachedFile.name,
                content: '',
                size_str: `${(attachedFile.size / 1024).toFixed(1)} KB`,
              },
            ],
          },
        };
        setMessages((prev) => [...prev, userMsg]);

        const uploadRes = await api.uploadFile(attachedFile, currentSessionId || undefined);
        const tableNames: string[] = uploadRes.table_names || (uploadRes.table_name ? [uploadRes.table_name] : []);
        const msgText = uploadRes.message || `File \`${attachedFile.name}\` uploaded and ingested.`;

        let dsData = null;
        if (tableNames.length > 0) {
          dsData = await api.fetchTable(tableNames[0], uploadRes.session_id || currentSessionId || undefined);
        } else if (uploadRes.primary_dataset_id) {
          dsData = await api.fetchDataset(uploadRes.primary_dataset_id);
        }

        const newTurnIdx = turns.length + 1;
        const assistantMsg: Message = {
          role: 'assistant',
          content: msgText,
          metadata: { table_names: tableNames },
          turnIndex: newTurnIdx,
          datasetData: dsData,
        };
        setMessages((prev) => [...prev, assistantMsg]);

        const newTurn: TurnArtifacts = {
          turnIndex: newTurnIdx,
          totalTurns: newTurnIdx,
          userQuery: text || `Uploaded ${attachedFile.name}`,
          messageContent: msgText,
          metadata: { table_names: tableNames },
          datasetData: dsData,
          chartsData: [],
        };

        setTurns((prev) => {
          const updated = [...prev, newTurn];
          for (const t of updated) t.totalTurns = updated.length;
          return updated;
        });
        setCurrentTurnIndex(newTurnIdx);
      }
      // 2. Normal Query Flow
      else {
        setCurrentAction('Planning execution steps...');
        const userMsg: Message = {
          role: 'user',
          content: text,
        };
        setMessages((prev) => [...prev, userMsg]);

        const queryRes = await api.sendQueryStream(
          text,
          currentSessionId || undefined,
          undefined,
          (action) => setCurrentAction(action)
        );
        const responseText = queryRes.response || 'No response generated.';
        const meta = queryRes.metadata || {};

        let dsData = null;
        if (meta.table_names && meta.table_names.length > 0) {
          dsData = await api.fetchTable(meta.table_names[0], queryRes.session_id || currentSessionId || undefined);
        } else if (meta.dataset_id) {
          dsData = await api.fetchDataset(meta.dataset_id);
        }

        const chartIds: number[] = meta.chart_ids || (meta.chart_id ? [meta.chart_id] : []);
        const chartsData: ChartData[] = [];
        for (const cid of chartIds) {
          const ch = await api.fetchChart(cid);
          if (ch) chartsData.push(ch);
        }

        // Resolve Python script and SQL query
        let pythonScript: string | null = meta.code || null;
        let sqlQuery: string | null = meta.sql_query || dsData?.query || null;

        const pythonScriptId = meta.python_script_id || (meta.script_id && !meta.sql_script_id ? meta.script_id : null);
        if (!pythonScript && pythonScriptId) {
          const sc = await api.fetchScript(pythonScriptId);
          if (sc && sc.script) {
            if (sc.language === 'python') pythonScript = sc.script;
            else if (sc.language === 'sql' && !sqlQuery) sqlQuery = sc.script;
          }
        }

        const sqlScriptId = meta.sql_script_id || (meta.script_id && meta.script_id !== pythonScriptId ? meta.script_id : null);
        if (!sqlQuery && sqlScriptId) {
          const sc = await api.fetchScript(sqlScriptId);
          if (sc && sc.script) {
            if (sc.language === 'sql') sqlQuery = sc.script;
            else if (sc.language === 'python' && !pythonScript) pythonScript = sc.script;
          }
        }

        if (!sqlQuery) sqlQuery = extractCodeBlock(responseText, 'sql');
        if (!pythonScript) pythonScript = extractCodeBlock(responseText, 'python');

        const newTurnIdx = turns.length + 1;
        const assistantMsg: Message = {
          role: 'assistant',
          content: responseText,
          metadata: meta,
          turnIndex: newTurnIdx,
          datasetData: dsData,
          chartsData,
          pythonScript,
          sqlQuery,
        };
        setMessages((prev) => [...prev, assistantMsg]);

        const newTurn: TurnArtifacts = {
          turnIndex: newTurnIdx,
          totalTurns: newTurnIdx,
          userQuery: text,
          messageContent: responseText,
          metadata: meta,
          datasetData: dsData,
          chartsData,
          pythonScript,
          sqlQuery,
        };

        setTurns((prev) => {
          const updated = [...prev, newTurn];
          for (const t of updated) t.totalTurns = updated.length;
          return updated;
        });
        setCurrentTurnIndex(newTurnIdx);
      }

      // Refresh session list to get updated title
      const updatedSessions = await api.fetchSessions();
      setSessions(updatedSessions);
    } catch (err: any) {
      console.error('Query execution error:', err);
      const cleanError = api.formatHumanReadableError(err);
      const errorMsg: Message = {
        role: 'assistant',
        content: cleanError,
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsBusy(false);
      setCurrentAction(null);
    }
  };

  return (
    <>
      <Header
        isBusy={isBusy}
        onToggleSidebar={() => setIsSidebarOpen((v) => !v)}
      />

      <div className="app-main">
        <Sidebar
          isOpen={isSidebarOpen}
          sessions={sessions}
          activeSessionId={currentSessionId}
          onSelectSession={(id) => {
            if (isBusy) return;
            loadSession(id);
          }}
          onNewSession={handleNewSession}
          onRenameSession={handleSidebarRename}
          onDeleteSession={handleDeleteSession}
          isBusy={isBusy}
        />

        <div className="studio-grid">
          <Chat
            messages={messages}
            isBusy={isBusy}
            currentAction={currentAction}
            onSendQuery={handleSendQuery}
            currentTurnIndex={currentTurnIndex}
            turnsCount={turns.length}
            onSelectTurn={(turnIdx) => {
              setCurrentTurnIndex(turnIdx);
              handleScrollToMessage(turnIdx);
            }}
          />

          <Workspace
            turns={turns}
            currentTurnIndex={currentTurnIndex}
            onSelectTurn={setCurrentTurnIndex}
            onScrollToMessage={handleScrollToMessage}
          />
        </div>
      </div>
    </>
  );
}

export default App;
