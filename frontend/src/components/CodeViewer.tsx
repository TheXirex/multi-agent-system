import React, { useEffect, useState } from 'react';
import Prism from 'prismjs';
import 'prismjs/components/prism-python';
import 'prismjs/components/prism-sql';
import { Check, Copy } from 'lucide-react';

interface CodeViewerProps {
  code: string;
  language: 'python' | 'sql';
  title: string;
}

export const CodeViewer: React.FC<CodeViewerProps> = ({ code, language, title }) => {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    Prism.highlightAll();
  }, [code, language]);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
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
          }}
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
        <pre style={{ margin: 0, padding: '10px', background: '#1c1f23', borderRadius: '4px' }}>
          <code className={`language-${language}`}>{code.trim()}</code>
        </pre>
      </div>
    </div>
  );
};
