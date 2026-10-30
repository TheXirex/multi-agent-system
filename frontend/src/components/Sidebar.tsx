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
  const [sessionToDelete, setSessionToDelete] = useState<Session | null>(null);

  const startRename = (s: Session, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingId(s.id);
    setEditTitle(s.title);
  };

  const saveRename = (id: string, e: React.MouseEvent | React.KeyboardEvent) => {
    e.stopPropagation();
    if (editTitle.trim()) {
      onRenameSession(id, editTitle.trim());
    }
    setEditingId(null);
  };

  const cancelRename = (e: React.MouseEvent | React.KeyboardEvent) => {
    e.stopPropagation();
    setEditingId(null);
  };

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
      <div className="sidebar-top">
        <button
          onClick={() => {
            if (!isBusy) onNewSession();
          }}
          disabled={isBusy}
          aria-label="Start a new chat"
          className="btn-new-chat"
        >
          <Plus size={15} />
          <span>New Chat</span>
        </button>
      </div>

      <div className="sidebar-list">
        <span className="sidebar-section-label">Recent Sessions</span>

        {sessions.length === 0 ? (
          <div className="sidebar-empty">No chat history yet.</div>
        ) : (
          sessions.map((s) => {
            const isActive = s.id === activeSessionId;
            const isCurrentEditing = editingId === s.id;
            const itemClasses = [
              'session-item',
              isActive ? 'active' : '',
              isBusy && !isActive ? 'locked' : '',
            ]
              .filter(Boolean)
              .join(' ');

            return (
              <div
                key={s.id}
                onClick={() => {
                  if (!isBusy) onSelectSession(s.id);
                }}
                title={isBusy && !isActive ? 'Session switching is locked while agent is working' : undefined}
                className={itemClasses}
              >
                <div className="session-item-main">
                  <MessageSquare size={14} color={isActive ? '#f8f9fa' : '#adb5bd'} style={{ flexShrink: 0 }} />

                  {isCurrentEditing ? (
                    <input
                      type="text"
                      value={editTitle}
                      onChange={(e) => setEditTitle(e.target.value)}
                      onClick={(e) => e.stopPropagation()}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') saveRename(s.id, e);
                        if (e.key === 'Escape') cancelRename(e);
                      }}
                      autoFocus
                      className="session-edit-input"
                    />
                  ) : (
                    <span className="session-title" title={s.title || 'Untitled Session'}>
                      {truncateToNearestSpace(s.title || 'Untitled Session', 34)}
                    </span>
                  )}
                </div>

                <div className="session-actions">
                  {isCurrentEditing ? (
                    <>
                      <button
                        onClick={(e) => saveRename(s.id, e)}
                        className="icon-action-btn light"
                        title="Save title"
                      >
                        <Check size={12} />
                      </button>
                      <button
                        onClick={cancelRename}
                        className="icon-action-btn"
                        title="Cancel"
                      >
                        <X size={12} />
                      </button>
                    </>
                  ) : (
                    <>
                      <button
                        onClick={(e) => startRename(s, e)}
                        className="icon-action-btn"
                        title="Rename session"
                      >
                        <Edit2 size={12} />
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setSessionToDelete(s);
                        }}
                        className="icon-action-btn"
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

      {sessionToDelete && (
        <div onClick={() => setSessionToDelete(null)} className="modal-backdrop">
          <div onClick={(e) => e.stopPropagation()} className="modal-dialog" style={{ maxWidth: '340px' }}>
            <div className="modal-header">
              <div className="modal-title">
                <Trash2 size={16} color="#ced4da" />
                <span>Delete Session</span>
              </div>
              <button
                onClick={() => setSessionToDelete(null)}
                className="icon-action-btn"
                title="Close"
              >
                <X size={15} />
              </button>
            </div>

            <div className="modal-body">
              <p style={{ fontSize: '13px', color: '#ced4da', lineHeight: 1.5 }}>
                Are you sure you want to delete this chat session? This action cannot be undone.
              </p>
            </div>

            <div className="modal-footer">
              <button onClick={() => setSessionToDelete(null)} className="btn-secondary">
                Cancel
              </button>
              <button onClick={confirmDelete} className="btn-primary">
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </aside>
  );
};
