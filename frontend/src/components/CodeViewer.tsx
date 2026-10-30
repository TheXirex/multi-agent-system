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

  const displayCode = useMemo(
    () => (language === 'sql' ? formatSql(code) : code),
    [code, language]
  );

  const highlightedHtml = useMemo(() => {
    const grammar = Prism.languages[language];
    if (!grammar) return displayCode.trim();
    try {
      return Prism.highlight(displayCode.trim(), grammar, language);
    } catch {
      return displayCode.trim();
    }
  }, [displayCode, language]);

  const handleCopy = async (e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(displayCode);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy code:', err);
    }
  };

  const headerClasses = [
    'widget-header',
    effectiveExpanded ? 'expanded' : '',
    collapsible ? 'collapsible' : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div className="widget-card">
      <div onClick={collapsible ? handleToggle : undefined} className={headerClasses}>
        <div className="widget-title-group">
          {language === 'python' ? (
            <Terminal size={14} color="#adb5bd" style={{ flexShrink: 0 }} />
          ) : (
            <Code size={14} color="#adb5bd" style={{ flexShrink: 0 }} />
          )}
          <span className="widget-title" title={title}>
            {title}
          </span>
        </div>

        <div className="widget-actions">
          <span className="badge badge-light">{language.toUpperCase()}</span>

          <button
            type="button"
            onClick={handleCopy}
            title={copied ? 'Copied!' : 'Copy to clipboard'}
            className={`widget-copy-btn ${copied ? 'copied' : ''}`}
          >
            {copied ? <Check size={12} /> : <Copy size={12} />}
            <span>{copied ? 'Copied' : 'Copy'}</span>
          </button>

          {collapsible && (
            <span className="widget-chevron">
              {effectiveExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            </span>
          )}
        </div>
      </div>

      {effectiveExpanded && (
        <div className="scroll-auto-hide" style={{ width: '100%', overflowX: 'auto', maxHeight: '450px' }}>
          <pre className={`language-${language} scroll-auto-hide code-pre`}>
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
