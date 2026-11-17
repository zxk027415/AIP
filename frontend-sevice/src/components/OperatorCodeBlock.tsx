// @AI_GENERATED
/**
 * OperatorCodeBlock — 算子 Python 源码展示（轻量语法高亮，无外部依赖）
 */
import React from 'react';

const KEYWORDS = new Set([
  'def', 'class', 'return', 'import', 'from', 'if', 'elif', 'else',
  'for', 'while', 'in', 'not', 'and', 'or', 'is', 'None', 'True', 'False',
  'try', 'except', 'finally', 'raise', 'with', 'as', 'pass', 'break',
  'continue', 'lambda', 'yield', 'async', 'await',
]);

function tokenizeLine(line: string): React.ReactNode[] {
  const commentIdx = line.indexOf('#');
  if (commentIdx === 0) {
    return [<span key="cmt" style={{ color: '#6a9955' }}>{line}</span>];
  }

  const tokens: React.ReactNode[] = [];
  const re = /("""[\s\S]*?"""|'''[\s\S]*?'''|"[^"]*"|'[^']*'|#.*$|\b\w+\b|[^\w\s])/g;
  let match: RegExpExecArray | null;
  let last = 0;
  let i = 0;

  while ((match = re.exec(line)) !== null) {
    if (match.index > last) {
      tokens.push(<span key={`gap-${i}`}>{line.slice(last, match.index)}</span>);
    }
    const tok = match[0];
    let color: string | undefined;

    if (tok.startsWith('#')) {
      color = '#6a9955';
    } else if (tok.startsWith('"') || tok.startsWith("'")) {
      color = '#ce9178';
    } else if (KEYWORDS.has(tok)) {
      color = '#569cd6';
    } else if (/^\d+(\.\d+)?$/.test(tok)) {
      color = '#b5cea8';
    } else if (/^[A-Z_][A-Z0-9_]{2,}$/.test(tok)) {
      color = '#4ec9b0';
    } else if (/^[a-z_]\w*$/.test(tok) && line[match.index + tok.length] === '(') {
      color = '#dcdcaa';
    }

    tokens.push(
      color
        ? <span key={`tok-${i}`} style={{ color }}>{tok}</span>
        : <span key={`tok-${i}`}>{tok}</span>,
    );
    last = match.index + tok.length;
    i++;
  }

  if (last < line.length) {
    tokens.push(<span key="tail">{line.slice(last)}</span>);
  }
  return tokens;
}

export interface OperatorCodeBlockProps {
  code: string;
  maxHeight?: number;
}

const OperatorCodeBlock: React.FC<OperatorCodeBlockProps> = ({ code, maxHeight = 420 }) => {
  const lines = code.split('\n');
  return (
    <div
      style={{
        background: '#1e1e1e',
        borderRadius: 6,
        padding: '12px 0',
        maxHeight,
        overflowY: 'auto',
        overflowX: 'auto',
        fontFamily: '"JetBrains Mono", "Fira Code", "Consolas", monospace',
        fontSize: 12.5,
        lineHeight: '20px',
      }}
    >
      <table style={{ borderCollapse: 'collapse', width: '100%' }}>
        <tbody>
          {lines.map((line, idx) => (
            <tr key={idx} style={{ verticalAlign: 'top' }}>
              <td
                style={{
                  userSelect: 'none',
                  color: '#6e7681',
                  textAlign: 'right',
                  paddingRight: 16,
                  paddingLeft: 12,
                  minWidth: 36,
                  fontSize: 11,
                  lineHeight: '20px',
                }}
              >
                {idx + 1}
              </td>
              <td style={{ paddingRight: 20, whiteSpace: 'pre', color: '#d4d4d4' }}>
                {tokenizeLine(line)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default OperatorCodeBlock;
// @AI_GENERATED: end
