import { FoldingRangeKind, type FoldingRange } from 'vscode-languageserver';
import type { TextDocument } from 'vscode-languageserver-textdocument';
import type { Script } from '../syntax/ast.js';
import { visit } from '../syntax/walk.js';

/**
 * Folds brackets, commands continued with a backslash, multi-line strings and runs of comment lines.
 * The closing line stays visible when the bracket sits alone on its line.
 */
export function foldingRanges(document: TextDocument, script: Script): FoldingRange[] {
  const text = document.getText();
  const ranges = new Map<number, FoldingRange>();

  const add = (start: number, end: number, kind?: FoldingRangeKind, keepLastLine = false): void => {
    const startLine = document.positionAt(start).line;
    let endLine = document.positionAt(end).line;
    if (keepLastLine) endLine -= 1;
    if (endLine <= startLine) return;
    const existing = ranges.get(startLine);
    if (!existing || existing.endLine < endLine) ranges.set(startLine, { startLine, endLine, ...(kind ? { kind } : {}) });
  };

  const closesOnOwnLine = (end: number): boolean => {
    let p = end - 2;
    while (p >= 0 && (text[p] === ' ' || text[p] === '\t')) p--;
    return p < 0 || text[p] === '\n' || text[p] === '\r';
  };

  visit(script, (node) => {
    switch (node.kind) {
      case 'brace':
      case 'subst':
      case 'group':
        add(node.start, node.end, undefined, node.closed && closesOnOwnLine(node.end));
        break;
      case 'statement': {
        // A statement that ends in a bracket on its own line folds like that bracket does.
        const last = node.elements[node.elements.length - 1];
        const value = last?.kind === 'named' ? last.value : last;
        const bracket = value?.kind === 'brace' || value?.kind === 'subst' || value?.kind === 'group' ? value : null;
        add(node.start, node.end, undefined, bracket !== null && bracket.closed && closesOnOwnLine(node.end));
        break;
      }
      case 'string':
        add(node.start, node.end);
        break;
    }
  });

  // Consecutive comment lines fold together.
  let run: { start: number; end: number } | null = null;
  const flush = (): void => {
    if (run) add(run.start, run.end, FoldingRangeKind.Comment);
    run = null;
  };
  for (const comment of script.comments) {
    const line = document.positionAt(comment.start).line;
    if (run && document.positionAt(run.end).line + 1 === line) run.end = comment.end;
    else {
      flush();
      run = { start: comment.start, end: comment.end };
    }
  }
  flush();

  return [...ranges.values()].sort((a, b) => a.startLine - b.startLine);
}
