import React, { useRef, useEffect, useState } from 'react';
import type { Message } from '../types';
import { marked } from 'marked';
import Prism from 'prismjs';
import 'prismjs/components/prism-python';
import 'prismjs/components/prism-sql';
import 'prismjs/themes/prism-tomorrow.css';
import { Paperclip, Send, User, X, Undo2, FileSpreadsheet, ChevronDown, ChevronRight, Terminal, Code } from 'lucide-react';
import { PlotlyChart } from './PlotlyChart';
import { CodeViewer } from './CodeViewer';

function cleanMarkdown(content: string): string {
  if (!content) return '';
  return content
    .replace(/<br\s*\/?>/gi, '\n\n')
    .replace(/^\s*[-*_]{3,}\s*$/gm, '')
    .replace(/\n{3,}/g, '\n\n');
}

interface ChatProps {
  messages: Message[];
  isBusy: boolean;
  onSendQuery: (text: string, attachedFile?: File | null) => Promise<void>;
  onSelectTurn: (turnIndex: number) => void;
  currentTurnIndex?: number;
}

const DEFAULT_SUGGESTIONS = [
  'Show summary statistics and distribution of customer age and spending score',
  'Train a K-Means clustering model to find customer segments and visualize with PCA',
  'List all database tables and dataset records currently available',
  'Train a regression model to predict spending score based on customer features',
];

export const Chat: React.FC<ChatProps> = ({
  messages,
  isBusy,
  onSendQuery,
  onSelectTurn,
  currentTurnIndex,
}) => {
  const [inputText, setInputText] = useState('');
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [expandedCodeCards, setExpandedCodeCards] = useState<Record<string, boolean>>({});

  const messagesScrollRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Auto-scroll to bottom on new messages and highlight code blocks
  useEffect(() => {
    if (messagesScrollRef.current) {
      messagesScrollRef.current.scrollTop = messagesScrollRef.current.scrollHeight;
    }
    const timer = setTimeout(() => {
      Prism.highlightAll();
    }, 40);
    return () => clearTimeout(timer);
  }, [messages, isBusy]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleSubmit = async () => {
    const text = inputText.trim();
    if ((!text && !pendingFile) || isBusy) return;

    const fileToSend = pendingFile;
    setInputText('');
    setPendingFile(null);

    await onSendQuery(text, fileToSend);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setPendingFile(e.target.files[0]);
    }
    // reset input
    e.target.value = '';
  };

  const toggleExpand = (cardKey: string) => {
    setExpandedCodeCards((prev) => ({ ...prev, [cardKey]: !prev[cardKey] }));
  };

  return (
    <div className="panel-card">
      {/* 1. Chat Message Stream */}
      <div
        ref={messagesScrollRef}
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: '16px',
          display: 'flex',
          flexDirection: 'column',
          gap: '16px',
        }}
      >
        {/* Welcome message if no conversation yet */}
        {messages.length === 0 && (
          <div
            style={{
              backgroundColor: 'rgba(52, 58, 64, 0.8)',
              border: '1px solid rgba(73, 80, 87, 0.7)',
              borderRadius: 'var(--app-radius)',
              padding: '16px',
              display: 'flex',
              flexDirection: 'column',
              gap: '12px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center' }}>
              <span style={{ fontSize: '13px', fontWeight: 600, color: '#f8f9fa' }}>
                Orchestrator Agent
              </span>
            </div>

            <div style={{ color: '#dee2e6', fontSize: '13px', lineHeight: 1.6 }}>
              <p style={{ fontWeight: 600, color: '#f8f9fa', marginBottom: '8px' }}>
                Welcome to the Multi-Agent Studio!
              </p>
              <p style={{ color: '#ced4da', marginBottom: '8px' }}>
                I am the <strong>AI Orchestrator</strong>, coordinating domain agents to analyze data, execute SQL queries, and build machine learning workflows:
              </p>
              <ul style={{ paddingLeft: '20px', color: '#ced4da', marginBottom: '8px' }}>
                <li>📊 <strong>Database Agent</strong>: Inspects schemas, executes queries, and manages tables.</li>
                <li>🤖 <strong>Machine Learning Agent</strong>: Trains models and generates interactive Plotly visualizations.</li>
                <li>📁 <strong>Custom Datasets</strong>: Attach your own <code>.csv</code> or <code>.xlsx</code> files below to bind them to this session.</li>
              </ul>
              <p style={{ color: '#adb5bd', fontSize: '12px' }}>
                Select a suggested prompt below to start immediately:
              </p>
            </div>

            {/* Suggested prompts list */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {DEFAULT_SUGGESTIONS.map((prompt, idx) => (
                <div
                  key={idx}
                  onClick={() => onSendQuery(prompt)}
                  style={{
                    padding: '8px 12px',
                    borderRadius: 'var(--app-radius)',
                    backgroundColor: 'rgba(33, 37, 41, 0.9)',
                    border: '1px solid rgba(73, 80, 87, 0.6)',
                    color: '#ced4da',
                    fontSize: '12px',
                    cursor: 'pointer',
                    transition: 'all 0.15s ease',
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.borderColor = '#adb5bd';
                    e.currentTarget.style.color = '#f8f9fa';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.borderColor = 'rgba(73, 80, 87, 0.6)';
                    e.currentTarget.style.color = '#ced4da';
                  }}
                >
                  {prompt}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Message bubbles */}
        {messages.map((msg, index) => {
          const isUser = msg.role === 'user';
          const cardId = msg.turnIndex ? `chat-turn-${msg.turnIndex}` : undefined;

          if (isUser) {
            return (
              <div
                key={index}
                style={{
                  display: 'flex',
                  justifyContent: 'flex-end',
                  width: '100%',
                }}
              >
                <div
                  style={{
                    maxWidth: '85%',
                    backgroundColor: '#495057',
                    color: '#f8f9fa',
                    padding: '12px 14px',
                    borderRadius: 'var(--app-radius)',
                    border: '1px solid rgba(108, 117, 125, 0.6)',
                    boxShadow: '0 2px 8px rgba(0, 0, 0, 0.2)',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '6px',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px', opacity: 0.85 }}>
                    <span style={{ fontSize: '11px', fontWeight: 600 }}>You</span>
                    <User size={13} />
                  </div>

                  {/* Attached files preview in user message */}
                  {msg.metadata?.attachments && msg.metadata.attachments.length > 0 && (
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', margin: '4px 0' }}>
                      {msg.metadata.attachments.map((att, aIdx) => (
                        <div
                          key={aIdx}
                          style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '5px',
                            backgroundColor: '#343a40',
                            border: '1px solid #6c757d',
                            padding: '3px 8px',
                            borderRadius: 'var(--app-radius)',
                            fontSize: '11px',
                            fontFamily: 'var(--font-mono)',
                          }}
                        >
                          <FileSpreadsheet size={13} color="#ced4da" />
                          <span>{att.filename}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  <div style={{ whiteSpace: 'pre-wrap', fontSize: '13.5px', lineHeight: 1.5 }}>
                    {msg.content}
                  </div>
                </div>
              </div>
            );
          }

          // Assistant message card
          return (
            <div
              key={index}
              id={cardId}
              style={{
                width: '100%',
                backgroundColor: 'rgba(52, 58, 64, 0.8)',
                border: '1px solid rgba(73, 80, 87, 0.7)',
                borderRadius: 'var(--app-radius)',
                padding: '14px',
                display: 'flex',
                flexDirection: 'column',
                gap: '12px',
                boxShadow: '0 2px 8px rgba(0, 0, 0, 0.2)',
                transition: 'all 0.3s ease-in-out',
                scrollMarginTop: '12px',
              }}
            >
              {/* Header row: Identity + Turn #N jump button */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', alignItems: 'center' }}>
                  <span style={{ fontSize: '12px', fontWeight: 600, color: '#f8f9fa' }}>
                    Orchestrator Agent
                  </span>
                </div>

                {msg.turnIndex && (
                  <button
                    onClick={() => onSelectTurn(msg.turnIndex!)}
                    title={`Restore workspace widgets to Turn #${msg.turnIndex}`}
                    aria-label={`Restore workspace widgets to Turn #${msg.turnIndex}`}
                    style={{
                      width: '24px',
                      height: '24px',
                      padding: 0,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      backgroundColor: currentTurnIndex === msg.turnIndex ? '#343a40' : '#212529',
                      border: currentTurnIndex === msg.turnIndex ? '1px solid #adb5bd' : '1px solid #495057',
                      color: currentTurnIndex === msg.turnIndex ? '#f8f9fa' : '#ced4da',
                      borderRadius: 'var(--app-radius)',
                      cursor: 'pointer',
                      transition: 'all 0.15s ease',
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.color = '#f8f9fa';
                      e.currentTarget.style.backgroundColor = '#343a40';
                      e.currentTarget.style.borderColor = '#adb5bd';
                    }}
                    onMouseLeave={(e) => {
                      const isActive = currentTurnIndex === msg.turnIndex;
                      e.currentTarget.style.color = isActive ? '#f8f9fa' : '#ced4da';
                      e.currentTarget.style.backgroundColor = isActive ? '#343a40' : '#212529';
                      e.currentTarget.style.borderColor = isActive ? '1px solid #adb5bd' : '1px solid #495057';
                    }}
                  >
                    <Undo2 size={13} />
                  </button>
                )}
              </div>

              {/* Markdown content */}
              <div
                className="markdown-body"
                dangerouslySetInnerHTML={{ __html: marked.parse(cleanMarkdown(msg.content)) as string }}
              />

              {/* Inline interactive plots preview */}
              {msg.chartsData && msg.chartsData.length > 0 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', paddingTop: '6px' }}>
                  <span style={{ fontSize: '11px', fontWeight: 600, color: '#ced4da', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                    Interactive Visualizations:
                  </span>
                  {msg.chartsData.map((ch, cIdx) => (
                    <PlotlyChart
                      key={cIdx}
                      spec={ch.spec}
                      title={ch.title}
                      chartType={ch.chart_type}
                    />
                  ))}
                </div>
              )}

              {/* Expandable Python script */}
              {msg.pythonScript && (
                <div style={{ borderRadius: 'var(--app-radius)', border: '1px solid rgba(73, 80, 87, 0.7)', overflow: 'hidden' }}>
                  <div
                    onClick={() => toggleExpand(`py-${index}`)}
                    style={{
                      padding: '8px 12px',
                      backgroundColor: '#212529',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      cursor: 'pointer',
                      fontSize: '12px',
                      color: '#ced4da',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <Terminal size={14} color="#adb5bd" />
                      <span>{msg.metadata?.code_title || msg.metadata?.task_description || 'Generated ML Python Script'}</span>
                    </div>
                    {expandedCodeCards[`py-${index}`] ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                  </div>
                  {expandedCodeCards[`py-${index}`] && (
                    <div style={{ padding: '8px', backgroundColor: '#1c1f23' }}>
                      <CodeViewer
                        code={msg.pythonScript}
                        language="python"
                        title={msg.metadata?.code_title || msg.metadata?.task_description || 'Machine Learning Python Script'}
                      />
                    </div>
                  )}
                </div>
              )}

              {/* Expandable SQL query */}
              {msg.sqlQuery && (
                <div style={{ borderRadius: 'var(--app-radius)', border: '1px solid rgba(73, 80, 87, 0.7)', overflow: 'hidden' }}>
                  <div
                    onClick={() => toggleExpand(`sql-${index}`)}
                    style={{
                      padding: '8px 12px',
                      backgroundColor: '#212529',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      cursor: 'pointer',
                      fontSize: '12px',
                      color: '#ced4da',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <Code size={14} color="#adb5bd" />
                      <span>
                        {msg.metadata?.sql_description ||
                          msg.datasetData?.name ||
                          'Executed PostgreSQL Query'}
                      </span>
                    </div>
                    {expandedCodeCards[`sql-${index}`] ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                  </div>
                  {expandedCodeCards[`sql-${index}`] && (
                    <div style={{ padding: '8px', backgroundColor: '#1c1f23' }}>
                      <CodeViewer
                        code={msg.sqlQuery}
                        language="sql"
                        title={
                          msg.metadata?.sql_description ||
                          msg.datasetData?.name ||
                          'PostgreSQL Query Statement'
                        }
                      />
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}

        {/* Thinking Indicator */}
        {isBusy && (
          <div
            style={{
              padding: '12px 14px',
              backgroundColor: 'rgba(52, 58, 64, 0.9)',
              border: '1px solid rgba(73, 80, 87, 0.7)',
              borderRadius: 'var(--app-radius)',
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              fontSize: '12px',
              color: '#ced4da',
              fontStyle: 'italic',
            }}
          >
            <div
              style={{
                width: '12px',
                height: '12px',
                borderRadius: '50%',
                border: '2px solid #ced4da',
                borderTopColor: 'transparent',
                animation: 'spin 0.8s linear infinite',
              }}
            />
            <span>Thinking & executing multi-agent workflow...</span>
          </div>
        )}
      </div>

      {/* 2. Chat Input Box Form */}
      <div
        style={{
          borderTop: '1px solid rgba(73, 80, 87, 0.6)',
          backgroundColor: '#212529',
          padding: '12px',
          display: 'flex',
          flexDirection: 'column',
          gap: '8px',
        }}
      >
        {/* Pending attachment chip */}
        {pendingFile && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <div
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                backgroundColor: '#343a40',
                border: '1px solid #6c757d',
                color: '#f8f9fa',
                fontSize: '11px',
                padding: '4px 10px',
                borderRadius: 'var(--app-radius)',
                fontFamily: 'var(--font-mono)',
              }}
            >
              <FileSpreadsheet size={13} color="#ced4da" />
              <span>{pendingFile.name} ({(pendingFile.size / 1024).toFixed(1)} KB)</span>
              <button
                onClick={() => setPendingFile(null)}
                style={{ padding: '2px', color: '#adb5bd', marginLeft: '4px' }}
                title="Remove attachment"
              >
                <X size={12} />
              </button>
            </div>
          </div>
        )}

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {/* File attach button */}
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileChange}
            accept=".csv,.xlsx,.xls"
            style={{ display: 'none' }}
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            title="Attach CSV or Excel file (.csv, .xlsx)"
            disabled={isBusy}
            style={{
              width: '38px',
              height: '38px',
              backgroundColor: '#343a40',
              border: '1px solid #495057',
              color: '#ced4da',
              flexShrink: 0,
            }}
            onMouseEnter={(e) => (e.currentTarget.style.color = '#f8f9fa')}
            onMouseLeave={(e) => (e.currentTarget.style.color = '#ced4da')}
          >
            <Paperclip size={16} />
          </button>

          {/* Text input area */}
          <textarea
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask the question..."
            disabled={isBusy}
            rows={1}
            style={{
              flex: 1,
              padding: '9px 12px',
              backgroundColor: '#343a40',
              border: '1px solid #495057',
              borderRadius: 'var(--app-radius)',
              color: '#f8f9fa',
              fontSize: '13px',
              resize: 'none',
              minHeight: '38px',
              maxHeight: '120px',
            }}
          />

          {/* Send button */}
          <button
            onClick={handleSubmit}
            disabled={isBusy || (!inputText.trim() && !pendingFile)}
            style={{
              width: '38px',
              height: '38px',
              backgroundColor: '#f8f9fa',
              color: '#212529',
              flexShrink: 0,
            }}
          >
            <Send size={15} />
          </button>
        </div>
      </div>

      <style>{`
        @keyframes spin {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
};
