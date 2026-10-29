import React, { useMemo, useState } from 'react';
import Prism from 'prismjs';
import 'prismjs/components/prism-python';
import 'prismjs/components/prism-sql';
import 'prismjs/themes/prism-tomorrow.css';
import { Check, ChevronDown, ChevronRight, Code, Copy, Terminal } from 'lucide-react';
import { formatSql } from '../utils/sqlFormatter';

interface CodeViewerProps {
  code: string;
  language: 'python' | 'sql';
  title: string;
  collapsible?: boolean;
  defaultExpanded?: boolean;
  isExpanded?: boolean;
  onToggleExpand?: () => void;
}

export const CodeViewer: React.FC<CodeViewerProps> = ({
  code,
  language,
  title,
  collapsible = true,
  defaultExpanded = true,
  isExpanded,
  onToggleExpand,
}) => {
  const [copied, setCopied] = useState(false);
  const [internalExpanded, setInternalExpanded] = useState(defaultExpanded);

  const effectiveExpanded = collapsible
    ? isExpanded !== undefined
      ? isExpanded
      : internalExpanded
    : true;

  const handleToggle = () => {
    if (!collapsible) return;
    if (onToggleExpand) {
      onToggleExpand();
    } else {
      setInternalExpanded((prev) => !prev);
    }
  };

  const displayCode = useMemo(() => {
    if (language === 'sql') {
      return formatSql(code);
    }
    return code;
  }, [code, language]);

  const highlightedHtml = useMemo(() => {
    const grammar = Prism.languages[language];
    if (!grammar) return displayCode.trim();
    try {
      return Prism.highlight(displayCode.trim(), grammar, language);
    } catch {
      return displayCode.trim();
    }
  }, [displayCode, language]);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(displayCode);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy code:', err);
    }
  };

  return (
    <div
      style={{
        width: '100%',
        maxWidth: '100%',
        backgroundColor: '#212529',
        border: '1px solid rgba(73, 80, 87, 0.7)',
        borderRadius: 'var(--app-radius, 6px)',
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <div
        onClick={collapsible ? handleToggle : undefined}
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '8px 12px',
          backgroundColor: '#212529',
          cursor: collapsible ? 'pointer' : 'default',
          userSelect: 'none',
          borderBottom: effectiveExpanded ? '1px solid rgba(73, 80, 87, 0.6)' : 'none',
          transition: 'background-color 0.15s ease',
        }}
        onMouseEnter={(e) => {
          if (collapsible) e.currentTarget.style.backgroundColor = '#2b3035';
        }}
        onMouseLeave={(e) => {
          if (collapsible) e.currentTarget.style.backgroundColor = '#212529';
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0, flex: 1, marginRight: '10px' }}>
          {language === 'python' ? (
            <Terminal size={14} color="#adb5bd" style={{ flexShrink: 0 }} />
          ) : (
            <Code size={14} color="#adb5bd" style={{ flexShrink: 0 }} />
          )}
          <span
            style={{
              fontSize: '12px',
              fontWeight: 600,
              color: '#ced4da',
              fontFamily: 'var(--font-mono)',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
            title={title}
          >
            {title}
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0 }}>
          <span
            className="badge badge-light"
            style={{
              fontSize: '10px',
              fontWeight: 600,
              padding: '2px 6px',
              letterSpacing: '0.04em',
            }}
          >
            {language.toUpperCase()}
          </span>

          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              handleCopy();
            }}
            title={copied ? 'Copied!' : 'Copy to clipboard'}
            style={{
              padding: '3px 8px',
              color: copied ? '#f8f9fa' : '#adb5bd',
              background: '#343a40',
              border: '1px solid rgba(108, 117, 125, 0.4)',
              borderRadius: '4px',
              fontSize: '11px',
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
              cursor: 'pointer',
              transition: 'all 0.15s ease',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.borderColor = '#ced4da';
              e.currentTarget.style.color = '#f8f9fa';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = 'rgba(108, 117, 125, 0.4)';
              e.currentTarget.style.color = copied ? '#f8f9fa' : '#adb5bd';
            }}
          >
            {copied ? <Check size={12} /> : <Copy size={12} />}
            <span>{copied ? 'Copied' : 'Copy'}</span>
          </button>

          {collapsible && (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#adb5bd',
                marginLeft: '2px',
              }}
            >
              {effectiveExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            </div>
          )}
        </div>
      </div>

      {effectiveExpanded && (
        <div className="scroll-auto-hide" style={{ width: '100%', overflowX: 'auto', maxHeight: '450px' }}>
          <pre
            className={`language-${language} scroll-auto-hide`}
            style={{
              margin: 0,
              padding: '12px 14px',
              background: '#181a1d',
              borderRadius: 0,
              fontFamily: 'var(--font-mono)',
              fontSize: '12.5px',
              lineHeight: 1.5,
            }}
          >
            <code
              className={`language-${language}`}
              dangerouslySetInnerHTML={{ __html: highlightedHtml }}
            />
          </pre>
        </div>
      )}
    </div>
  );
};
