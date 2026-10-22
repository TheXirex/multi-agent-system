import React, { useState, useEffect } from 'react';
import type { Session } from '../types';
import { MessageSquare, Plus, Trash2, Edit2, Check, X } from 'lucide-react';
import { truncateToNearestSpace } from '../utils/formatters';

interface SidebarProps {
  isOpen: boolean;
  sessions: Session[];
  activeSessionId: string | null;
  onSelectSession: (id: string) => void;
  onNewSession: () => void;
  onRenameSession: (id: string, newTitle: string) => void;
  onDeleteSession: (id: string) => void;
  isBusy?: boolean;
}

export const Sidebar: React.FC<SidebarProps> = ({
  isOpen,
  sessions,
  activeSessionId,
  onSelectSession,
  onNewSession,
  onRenameSession,
  onDeleteSession,
  isBusy,
}) => {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');

  const startRename = (s: Session, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingId(s.id);
    setEditTitle(s.title);
  };

  const saveRename = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (editTitle.trim()) {
      onRenameSession(id, editTitle.trim());
    }
    setEditingId(null);
  };

  const cancelRename = (e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingId(null);
  };

  const [sessionToDelete, setSessionToDelete] = useState<Session | null>(null);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && sessionToDelete) {
        setSessionToDelete(null);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [sessionToDelete]);

  const confirmDelete = () => {
    if (sessionToDelete) {
      onDeleteSession(sessionToDelete.id);
      setSessionToDelete(null);
    }
  };

  return (
    <aside className={`app-sidebar ${isOpen ? '' : 'closed'}`}>
      {/* Top action button */}
      <div style={{ padding: '12px', borderBottom: '1px solid rgba(73, 80, 87, 0.5)' }}>
        <button
          onClick={() => {
            if (isBusy) return;
            onNewSession();
          }}
          disabled={isBusy}
          title={isBusy ? 'Please wait until current agent task completes' : 'Start a new chat'}
          style={{
            width: '100%',
            padding: '8px 12px',
            backgroundColor: '#343a40',
            border: '1px solid #495057',
            color: '#f8f9fa',
            fontWeight: 600,
            fontSize: '12px',
            gap: '8px',
            opacity: isBusy ? 0.45 : 1,
            cursor: isBusy ? 'not-allowed' : 'pointer',
          }}
        >
          <Plus size={15} />
          <span>New Chat</span>
        </button>
      </div>

      {/* Sessions list */}
      <div
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: '8px',
          display: 'flex',
          flexDirection: 'column',
          gap: '4px',
        }}
      >
        <span
          style={{
            fontSize: '10px',
            fontWeight: 700,
            textTransform: 'uppercase',
            letterSpacing: '0.06em',
            color: '#6c757d',
            padding: '4px 8px',
          }}
        >
          Recent Sessions
        </span>

        {sessions.length === 0 ? (
          <div
            style={{
              padding: '20px 8px',
              textAlign: 'center',
              color: '#6c757d',
              fontSize: '12px',
            }}
          >
            No chat history yet.
          </div>
        ) : (
          sessions.map((s) => {
            const isActive = s.id === activeSessionId;
            const isCurrentEditing = editingId === s.id;

            return (
              <div
                key={s.id}
                onClick={() => {
                  if (isBusy) return;
                  onSelectSession(s.id);
                }}
                title={isBusy && !isActive ? 'Session switching is locked while agent is working' : undefined}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '7px 10px',
                  borderRadius: 'var(--app-radius)',
                  backgroundColor: isActive ? 'rgba(73, 80, 87, 0.6)' : 'transparent',
                  border: isActive ? '1px solid #6c757d' : '1px solid transparent',
                  cursor: isBusy ? 'not-allowed' : 'pointer',
                  opacity: isBusy && !isActive ? 0.5 : 1,
                  transition: 'all 0.15s ease',
                  gap: '6px',
                }}
                className="group"
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0, flex: 1 }}>
                  <MessageSquare size={14} color={isActive ? '#f8f9fa' : '#adb5bd'} style={{ flexShrink: 0 }} />

                  {isCurrentEditing ? (
                    <input
                      type="text"
                      value={editTitle}
                      onChange={(e) => setEditTitle(e.target.value)}
                      onClick={(e) => e.stopPropagation()}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') saveRename(s.id, e as any);
                        if (e.key === 'Escape') cancelRename(e as any);
                      }}
                      autoFocus
                      style={{
                        padding: '2px 4px',
                        fontSize: '12px',
                        width: '100%',
                        height: '22px',
                      }}
                    />
                  ) : (
                    <span
                      title={s.title || 'Untitled Session'}
                      style={{
                        fontSize: '12px',
                        color: isActive ? '#f8f9fa' : '#ced4da',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                        fontWeight: isActive ? 600 : 400,
                      }}
                    >
                      {truncateToNearestSpace(s.title || 'Untitled Session', 34)}
                    </span>
                  )}
                </div>

                {/* Actions */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '2px', flexShrink: 0 }}>
                  {isCurrentEditing ? (
                    <>
                      <button
                        onClick={(e) => saveRename(s.id, e)}
                        style={{ padding: '3px', color: '#f8f9fa' }}
                        title="Save title"
                      >
                        <Check size={12} />
                      </button>
                      <button
                        onClick={cancelRename}
                        style={{ padding: '3px', color: '#adb5bd' }}
                        title="Cancel"
                      >
                        <X size={12} />
                      </button>
                    </>
                  ) : (
                    <>
                      <button
                        onClick={(e) => startRename(s, e)}
                        style={{ padding: '3px', color: '#6c757d' }}
                        title="Rename session"
                      >
                        <Edit2 size={12} />
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setSessionToDelete(s);
                        }}
                        style={{ padding: '3px', color: '#6c757d' }}
                        title="Delete session"
                      >
                        <Trash2 size={12} />
                      </button>
                    </>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Custom Confirmation Modal */}
      {sessionToDelete && (
        <div
          onClick={() => setSessionToDelete(null)}
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.75)',
            backdropFilter: 'blur(3px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: '16px',
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              width: '100%',
              maxWidth: '380px',
              backgroundColor: '#212529',
              border: '1px solid #495057',
              borderRadius: 'var(--app-radius)',
              boxShadow: '0 12px 36px rgba(0, 0, 0, 0.6)',
              overflow: 'hidden',
              display: 'flex',
              flexDirection: 'column',
            }}
          >
            {/* Modal Header */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '14px 16px',
                borderBottom: '1px solid rgba(73, 80, 87, 0.6)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Trash2 size={16} color="#ced4da" />
                <span style={{ fontSize: '13px', fontWeight: 600, color: '#f8f9fa' }}>
                  Delete Session
                </span>
              </div>
              <button
                onClick={() => setSessionToDelete(null)}
                style={{ padding: '2px', color: '#adb5bd' }}
                title="Close"
              >
                <X size={15} />
              </button>
            </div>

            {/* Modal Body */}
            <div style={{ padding: '16px' }}>
              <p style={{ fontSize: '13px', color: '#ced4da', margin: 0, lineHeight: 1.5 }}>
                Are you sure you want to delete this chat session? This action cannot be undone.
              </p>
            </div>

            {/* Modal Footer */}
            <div
              style={{
                padding: '12px 16px',
                backgroundColor: 'rgba(33, 37, 41, 0.95)',
                borderTop: '1px solid rgba(73, 80, 87, 0.6)',
                display: 'flex',
                justifyContent: 'flex-end',
                gap: '8px',
              }}
            >
              <button
                onClick={() => setSessionToDelete(null)}
                style={{
                  padding: '6px 12px',
                  fontSize: '12px',
                  fontWeight: 500,
                  color: '#ced4da',
                  backgroundColor: '#343a40',
                  border: '1px solid #495057',
                }}
              >
                Cancel
              </button>
              <button
                onClick={confirmDelete}
                style={{
                  padding: '6px 12px',
                  fontSize: '12px',
                  fontWeight: 600,
                  color: '#212529',
                  backgroundColor: '#f8f9fa',
                  border: '1px solid #f8f9fa',
                }}
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </aside>
  );
};
