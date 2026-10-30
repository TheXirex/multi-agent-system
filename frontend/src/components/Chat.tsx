import React, { useRef, useEffect, useState } from 'react';
import type { Message } from '../types';
import { marked } from 'marked';
import Prism from 'prismjs';
import 'prismjs/components/prism-python';
import 'prismjs/components/prism-sql';
import 'prismjs/themes/prism-tomorrow.css';
import { Paperclip, Send, User, X, ArrowRightToLine, FileSpreadsheet } from 'lucide-react';
import { formatFileSize } from '../utils/formatters';
import { useScrollGutter } from '../utils/scrollAutoHide';
import { PlotlyChart } from './PlotlyChart';
import { CodeViewer } from './CodeViewer';
import { FileAttachModal } from './FileAttachModal';

interface ChatProps {
  messages: Message[];
  isBusy: boolean;
  onSendQuery: (text: string, attachedFile?: File | null) => Promise<void>;
  onSelectTurn: (turnIndex: number) => void;
  currentTurnIndex?: number;
  turnsCount?: number;
  currentAction?: string | null;
}

const DEFAULT_SUGGESTIONS = [
  'What can you do and how can you help me analyze data?',
  'What tables and datasets are available in the database?',
  'Which top 10 product categories have the highest catalog volume?',
  'Does offering higher discounts impact customer ratings? Visualize the relationship',
  'Segment products based on prices, discounts, and ratings to uncover market tiers',
];

export const Chat: React.FC<ChatProps> = ({
  messages,
  isBusy,
  onSendQuery,
  onSelectTurn,
  currentTurnIndex,
  turnsCount,
  currentAction,
}) => {
  const [inputText, setInputText] = useState('');
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [isAttachModalOpen, setIsAttachModalOpen] = useState(false);

  const messagesScrollRef = useRef<HTMLDivElement>(null);
  const scrollGutter = useScrollGutter(messagesScrollRef, `${messages.length}-${isBusy}`, 10);

  const orchestratorStatesCount =
    typeof turnsCount === 'number'
      ? turnsCount
      : messages.filter((m) => m.role === 'assistant' && typeof m.turnIndex === 'number').length;
  const showTurnArrow = orchestratorStatesCount >= 2;

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

  return (
    <div className="panel-card">
      <div
        ref={messagesScrollRef}
        className="scroll-auto-hide chat-stream"
        style={{ paddingRight: `${Math.max(0, 16 - scrollGutter)}px` }}
      >
        <div className="welcome-card">
          <span className="agent-label" style={{ fontSize: '13px' }}>
            Orchestrator Agent
          </span>

          <div className="markdown-body" style={{ fontSize: '13px' }}>
            <p style={{ fontWeight: 600, color: '#f8f9fa' }}>
              Welcome to the Multi-Agent Studio!
            </p>
            <p>
              I am the <strong>AI Orchestrator</strong>, coordinating domain agents to analyze data, execute SQL queries, and build machine learning workflows:
            </p>
            <ul>
              <li>📊 <strong>Database Agent</strong>: Inspects schemas, executes queries, and manages tables.</li>
              <li>🤖 <strong>Machine Learning Agent</strong>: Trains models and generates interactive Plotly visualizations.</li>
              <li>📁 <strong>Custom Datasets</strong>: Attach your own <code>.csv</code> or <code>.xlsx</code> files below to bind them to this session.</li>
            </ul>
            <p style={{ color: '#adb5bd', fontSize: '12px' }}>
              Select a suggested prompt below to start immediately:
            </p>
          </div>

          <div className="suggestions-list">
            {DEFAULT_SUGGESTIONS.map((prompt, idx) => (
              <div
                key={idx}
                onClick={() => {
                  if (!isBusy) onSendQuery(prompt);
                }}
                className={`suggestion-item ${isBusy ? 'disabled' : ''}`}
              >
                {prompt}
              </div>
            ))}
          </div>
        </div>

        {messages.map((msg, index) => {
          if (msg.role === 'user') {
            return (
              <div key={index} className="user-bubble-row">
                <div className="user-bubble">
                  <div className="user-bubble-header">
                    <span>You</span>
                    <User size={13} />
                  </div>

                  {msg.metadata?.attachments && msg.metadata.attachments.length > 0 && (
                    <div className="attachment-list">
                      {msg.metadata.attachments.map((att, aIdx) => (
                        <div key={aIdx} className="attachment-chip">
                          <FileSpreadsheet size={13} color="#ced4da" />
                          <span>{att.filename}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  <div className="user-bubble-text">{msg.content}</div>
                </div>
              </div>
            );
          }

          const cardId = msg.turnIndex ? `chat-turn-${msg.turnIndex}` : undefined;

          return (
            <div key={index} id={cardId} className="assistant-card">
              <div className="card-header-row">
                <span className="agent-label">Orchestrator Agent</span>

                {msg.turnIndex && showTurnArrow && (
                  <button
                    onClick={() => onSelectTurn(msg.turnIndex!)}
                    aria-label={`Open Turn #${msg.turnIndex} in workspace`}
                    className={`turn-jump-btn ${currentTurnIndex === msg.turnIndex ? 'active' : ''}`}
                  >
                    <ArrowRightToLine size={13} />
                  </button>
                )}
              </div>

              <div
                className="markdown-body"
                dangerouslySetInnerHTML={{ __html: marked.parse(msg.content || '') as string }}
              />

              {msg.chartsData && msg.chartsData.length > 0 && (
                <div className="charts-section">
                  <span className="charts-section-label">Interactive Visualizations:</span>
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

              {msg.pythonScript && (
                <CodeViewer
                  code={msg.pythonScript}
                  language="python"
                  title={msg.metadata?.code_title || msg.metadata?.task_description || 'Machine Learning Python Script'}
                  collapsible={true}
                  defaultExpanded={false}
                />
              )}

              {msg.sqlQuery && (
                <CodeViewer
                  code={msg.sqlQuery}
                  language="sql"
                  title={
                    msg.metadata?.sql_description ||
                    msg.datasetData?.name ||
                    'Executed PostgreSQL Query'
                  }
                  collapsible={true}
                  defaultExpanded={false}
                />
              )}
            </div>
          );
        })}

        {isBusy && (
          <div className="thinking-banner">
            <div className="spinner" />
            <span>{currentAction || 'Executing multi-agent workflow...'}</span>
          </div>
        )}
      </div>

      <div className="chat-input-bar">
        {pendingFile && (
          <div className="attachment-list" style={{ margin: 0 }}>
            <div className="attachment-chip">
              <FileSpreadsheet size={13} color="#ced4da" />
              <span>{pendingFile.name} ({formatFileSize(pendingFile.size)})</span>
              <button
                onClick={() => setPendingFile(null)}
                className="icon-action-btn"
                title="Remove attachment"
              >
                <X size={12} />
              </button>
            </div>
          </div>
        )}

        <div className="chat-input-row">
          <button
            onClick={() => setIsAttachModalOpen(true)}
            aria-label="Attach dataset file"
            disabled={isBusy}
            className="btn-attach"
          >
            <Paperclip size={16} />
          </button>

          <textarea
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask the question..."
            disabled={isBusy}
            rows={1}
            className="chat-textarea"
          />

          <button
            onClick={handleSubmit}
            disabled={isBusy || (!inputText.trim() && !pendingFile)}
            className="btn-send"
          >
            <Send size={15} />
          </button>
        </div>
      </div>

      <FileAttachModal
        isOpen={isAttachModalOpen}
        onClose={() => setIsAttachModalOpen(false)}
        onSelectFile={(file) => setPendingFile(file)}
        currentFile={pendingFile}
      />
    </div>
  );
};
