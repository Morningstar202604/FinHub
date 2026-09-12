import React, { useState } from 'react';
import { Copy, Check } from 'lucide-react';
import { useTheme } from '@/contexts/ThemeContext';
import SyntaxHighlighter, { oneDark, oneLight } from './SyntaxHighlighter';
interface CodeBlockProps {
  language: string | null;
  code: string;
  compact?: boolean;
  codeTheme?: 'light' | 'dark';
}

// --- CodeBlock component ---
export default function CodeBlock({ language, code, compact = false, codeTheme }: CodeBlockProps): React.ReactElement {
  const { theme } = useTheme();
  const effectiveTheme = codeTheme ?? theme;
  const [copied, setCopied] = useState(false);

  const handleCopy = (): void => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // When codeTheme is set, use explicit colors instead of CSS vars.
  // CSS vars resolve to the current theme at render time and get baked into
  // innerHTML clones (Paged.js) and react-to-print iframes.
  const isForceLight = codeTheme === 'light';
  const bgColor = isForceLight ? '#f8f9fa' : 'var(--color-bg-code)';
  const borderColor = isForceLight ? '#e0e0e0' : 'var(--color-border-muted)';
  const labelColor = isForceLight ? '#6b7280' : 'var(--color-text-tertiary)';

  // Export/print mode: Notion-style clean code block — no header chrome,
  // just code on a light gray background. Page-break-inside:avoid keeps
  // the block together across pages.
  if (isForceLight) {
    return (
      <div style={{ margin: compact ? '4px 0' : '6px 0' }}>
        <div className="rounded overflow-hidden"
          style={{ backgroundColor: '#f7f6f3', pageBreakInside: 'avoid', breakInside: 'avoid' }}>
          <SyntaxHighlighter
            language={language || 'text'}
            style={oneLight}
            customStyle={{
              margin: 0,
              padding: '0.8rem 1rem',
              backgroundColor: 'transparent',
              fontSize: compact ? '0.75rem' : '0.8rem',
              lineHeight: '1.6',
            }}
            codeTagProps={{ style: { backgroundColor: 'transparent' } }}
            wrapLongLines
          >
            {code}
          </SyntaxHighlighter>
        </div>
      </div>
    );
  }

  return (
    <div style={{ margin: compact ? '4px 0' : '6px 0' }}>
      <div className="rounded-lg overflow-hidden"
        style={{ backgroundColor: bgColor, border: `1px solid ${borderColor}` }}>
        {!compact && (
          <div className="flex items-center justify-between px-3 py-1.5"
            style={{ borderBottom: `1px solid ${borderColor}` }}>
            <span className="text-xs font-mono" style={{ color: labelColor }}>
              {language || 'text'}
            </span>
            <button onClick={handleCopy}
              className="flex items-center gap-1 text-xs hover:opacity-100 transition-opacity"
              style={{ color: labelColor, background: 'none', border: 'none', cursor: 'pointer' }}>
              {copied ? <><Check className="h-3 w-3" /> Copied</> : <><Copy className="h-3 w-3" /> Copy</>}
            </button>
          </div>
        )}
        <SyntaxHighlighter
          language={language || 'text'}
          style={effectiveTheme === 'light' ? oneLight : oneDark}
          customStyle={{
            margin: 0,
            padding: compact ? '0.6rem' : '1rem',
            backgroundColor: 'transparent',
            fontSize: compact ? '0.75rem' : '0.875rem',
            lineHeight: '1.5',
          }}
          codeTagProps={{ style: { backgroundColor: 'transparent' } }}
          wrapLongLines
        >
          {code}
        </SyntaxHighlighter>
      </div>
    </div>
  );
}


