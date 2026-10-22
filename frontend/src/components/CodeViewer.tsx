import React, { useMemo, useState } from 'react';
import Prism from 'prismjs';
import 'prismjs/components/prism-python';
import 'prismjs/components/prism-sql';
import 'prismjs/themes/prism-tomorrow.css';
import { Check, Copy } from 'lucide-react';
import { formatSql } from '../utils/sqlFormatter';

interface CodeViewerProps {
  code: string;
  language: 'python' | 'sql';
  title: string;
}

export const CodeViewer: React.FC<CodeViewerProps> = ({ code, language, title }) => {
  const [copied, setCopied] = useState(false);

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
        borderRadius: '6px',
        padding: '12px 14px',
        display: 'flex',
        flexDirection: 'column',
        gap: '8px',
        overflow: 'hidden',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span
          style={{
            fontSize: '12px',
            fontWeight: 600,
            color: '#ced4da',
            fontFamily: 'var(--font-mono)',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            maxWidth: '75%',
          }}
          title={title}
        >
          {title}
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span className="badge badge-light">{language.toUpperCase()}</span>
          <button
            onClick={handleCopy}
            title={copied ? 'Copied!' : 'Copy to clipboard'}
            style={{
              padding: '3px 6px',
              color: copied ? '#f8f9fa' : '#adb5bd',
              background: '#343a40',
              border: '1px solid rgba(108, 117, 125, 0.4)',
              fontSize: '11px',
              gap: '4px',
            }}
          >
            {copied ? <Check size={12} /> : <Copy size={12} />}
            <span>{copied ? 'Copied' : 'Copy'}</span>
          </button>
        </div>
      </div>
      <div style={{ width: '100%', overflowX: 'auto', maxHeight: '450px' }}>
        <pre
          className={`language-${language}`}
          style={{
            margin: 0,
            padding: '12px',
            background: '#181a1d',
            borderRadius: '4px',
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
    </div>
  );
};
