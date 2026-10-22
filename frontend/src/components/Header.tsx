import React from 'react';
import { PanelLeft } from 'lucide-react';

interface HeaderProps {
  isBusy: boolean;
  onToggleSidebar: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  isBusy,
  onToggleSidebar,
}) => {
  return (
    <header className="app-header">
      {/* Left section: Sidebar toggle & Studio Title */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <button
          onClick={onToggleSidebar}
          aria-label="Toggle session history sidebar"
          style={{
            padding: '6px',
            color: '#ced4da',
            background: '#343a40',
            border: '1px solid #495057',
            cursor: 'pointer',
          }}
        >
          <PanelLeft size={16} />
        </button>

        <div>
          <span style={{ fontSize: '13px', fontWeight: 700, color: '#f8f9fa' }}>
            Multi-Agent Studio
          </span>
        </div>
      </div>

      {/* Right section: Activity status indicator */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
        {isBusy && (
          <div
            style={{
              width: '12px',
              height: '12px',
              borderRadius: '50%',
              border: '2px solid #adb5bd',
              borderTopColor: 'transparent',
              animation: 'spin 0.8s linear infinite',
              marginLeft: '6px',
            }}
            title="Processing..."
          />
        )}
      </div>
    </header>
  );
};
