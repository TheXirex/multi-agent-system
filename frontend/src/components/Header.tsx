import React from 'react';
import { PanelLeft } from 'lucide-react';

interface HeaderProps {
  isBusy: boolean;
  onToggleSidebar: () => void;
}

export const Header: React.FC<HeaderProps> = ({ isBusy, onToggleSidebar }) => (
  <header className="app-header">
    <div className="header-left">
      <button
        onClick={onToggleSidebar}
        aria-label="Toggle session history sidebar"
        className="header-toggle-btn"
      >
        <PanelLeft size={16} />
      </button>
      <span className="header-title">Multi-Agent Studio</span>
    </div>

    <div className="header-right">
      {isBusy && <div className="spinner" title="Processing..." />}
    </div>
  </header>
);
