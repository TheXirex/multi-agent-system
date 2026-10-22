/**
 * Formats SQL queries into clean, multi-line, indented statements without using regular expressions.
 */
export function formatSql(sql: string): string {
  if (!sql || typeof sql !== 'string') return '';
  const trimmed = sql.trim();
  if (!trimmed) return '';

  const tokens: string[] = [];
  let i = 0;
  const n = trimmed.length;
  const delimiters = new Set([' ', '\t', '\r', '\n', '(', ')', ',', ';']);

  // Tokenize without regex
  while (i < n) {
    const c = trimmed[i];

    // Whitespace
    if (c === ' ' || c === '\t' || c === '\r' || c === '\n') {
      i++;
      continue;
    }

    // String literals '...' (with '' escape)
    if (c === "'") {
      const start = i;
      i++;
      while (i < n) {
        if (trimmed[i] === "'") {
          if (i + 1 < n && trimmed[i + 1] === "'") {
            i += 2;
          } else {
            i++;
            break;
          }
        } else {
          i++;
        }
      }
      tokens.push(trimmed.slice(start, i));
      continue;
    }

    // Double quoted identifiers "..."
    if (c === '"') {
      const start = i;
      i++;
      while (i < n && trimmed[i] !== '"') {
        i++;
      }
      if (i < n) i++;
      tokens.push(trimmed.slice(start, i));
      continue;
    }

    // Single-character punctuation
    if (c === '(' || c === ')' || c === ',' || c === ';') {
      tokens.push(c);
      i++;
      continue;
    }

    // Word tokens and operators
    const start = i;
    while (i < n && !delimiters.has(trimmed[i])) {
      i++;
    }
    tokens.push(trimmed.slice(start, i));
  }

  if (tokens.length === 0) return trimmed;

  const majorClauses = new Set([
    'SELECT',
    'FROM',
    'WHERE',
    'HAVING',
    'LIMIT',
    'OFFSET',
    'UNION',
    'EXCEPT',
    'INTERSECT',
    'INSERT',
    'VALUES',
    'UPDATE',
    'SET',
    'WITH',
  ]);

  const compoundClauses: Record<string, string[]> = {
    GROUP: ['BY'],
    ORDER: ['BY'],
    LEFT: ['JOIN'],
    RIGHT: ['JOIN'],
    INNER: ['JOIN'],
    FULL: ['JOIN'],
    CROSS: ['JOIN'],
  };

  const lines: string[] = [];
  let currentLine: string[] = [];
  let parenDepth = 0;
  let indentLevel = 0;
  let inSelectColumns = false;

  const finishLine = () => {
    if (currentLine.length > 0) {
      const prefix = '  '.repeat(indentLevel);
      lines.push(prefix + currentLine.join('').trim());
      currentLine = [];
    }
  };

  const appendToken = (tok: string, spaceBefore = true) => {
    if (currentLine.length === 0) {
      currentLine.push(tok);
    } else if (!spaceBefore) {
      currentLine.push(tok);
    } else {
      currentLine.push(' ' + tok);
    }
  };

  let k = 0;
  const totalTokens = tokens.length;

  while (k < totalTokens) {
    const tok = tokens[k];
    const upper = tok.toUpperCase();

    if (tok === '(') {
      parenDepth++;
      const prevLineStr = currentLine.length > 0 ? currentLine[currentLine.length - 1] : '';
      const lastChar = prevLineStr.length > 0 ? prevLineStr[prevLineStr.length - 1] : '';
      const isWordChar =
        (lastChar >= 'a' && lastChar <= 'z') ||
        (lastChar >= 'A' && lastChar <= 'Z') ||
        (lastChar >= '0' && lastChar <= '9') ||
        lastChar === '_';
      appendToken(tok, !isWordChar);
      k++;
      continue;
    }

    if (tok === ')') {
      parenDepth = Math.max(0, parenDepth - 1);
      appendToken(tok, false);
      k++;
      continue;
    }

    if (tok === ';') {
      if (currentLine.length > 0) {
        currentLine.push(';');
        finishLine();
      } else if (lines.length > 0) {
        lines[lines.length - 1] = lines[lines.length - 1].trimEnd() + ';';
      }
      k++;
      continue;
    }

    if (tok === ',') {
      currentLine.push(',');
      if (parenDepth === 0 && (inSelectColumns || indentLevel > 0)) {
        finishLine();
      }
      k++;
      continue;
    }

    let spaceBefore = true;
    if (currentLine.length > 0) {
      const lastToken = currentLine[currentLine.length - 1];
      if (lastToken.endsWith('(')) {
        spaceBefore = false;
      }
    }

    if (parenDepth > 0) {
      appendToken(tok, spaceBefore);
      k++;
      continue;
    }

    // Compound clauses: GROUP BY, ORDER BY, LEFT JOIN, etc.
    if (compoundClauses[upper] && k + 1 < totalTokens) {
      const nextUpper = tokens[k + 1].toUpperCase();
      if (compoundClauses[upper].includes(nextUpper)) {
        const compoundName = `${upper} ${nextUpper}`;
        finishLine();
        inSelectColumns = false;
        if (compoundName === 'GROUP BY' || compoundName === 'ORDER BY') {
          indentLevel = 0;
          appendToken(compoundName, false);
          finishLine();
          indentLevel = 1;
        } else {
          indentLevel = 0;
          appendToken(compoundName, false);
        }
        k += 2;
        continue;
      }
    }

    // Compound clauses with OUTER: LEFT OUTER JOIN, etc.
    if ((upper === 'LEFT' || upper === 'RIGHT' || upper === 'FULL') && k + 2 < totalTokens) {
      if (tokens[k + 1].toUpperCase() === 'OUTER' && tokens[k + 2].toUpperCase() === 'JOIN') {
        const compoundName = `${upper} OUTER JOIN`;
        finishLine();
        inSelectColumns = false;
        indentLevel = 0;
        appendToken(compoundName, false);
        k += 3;
        continue;
      }
    }

    if (upper === 'JOIN') {
      finishLine();
      inSelectColumns = false;
      indentLevel = 0;
      appendToken('JOIN', false);
      k++;
      continue;
    }

    if (upper === 'ON') {
      appendToken('ON', true);
      k++;
      continue;
    }

    if (majorClauses.has(upper)) {
      finishLine();
      indentLevel = 0;
      if (upper === 'SELECT') {
        if (k + 1 < totalTokens && tokens[k + 1].toUpperCase() === 'DISTINCT') {
          appendToken('SELECT DISTINCT', false);
          k += 2;
        } else {
          appendToken('SELECT', false);
          k++;
        }
        finishLine();
        indentLevel = 1;
        inSelectColumns = true;
        continue;
      } else if (upper === 'WHERE' || upper === 'HAVING') {
        appendToken(upper, false);
        finishLine();
        indentLevel = 1;
        inSelectColumns = false;
        k++;
        continue;
      } else {
        inSelectColumns = false;
        indentLevel = 0;
        appendToken(upper, false);
        k++;
        continue;
      }
    }

    if (upper === 'AND' || upper === 'OR') {
      finishLine();
      indentLevel = 1;
      appendToken(upper, false);
      k++;
      continue;
    }

    appendToken(tok, spaceBefore);
    k++;
  }

  finishLine();
  return lines.join('\n');
}
