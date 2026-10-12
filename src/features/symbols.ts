import { SymbolKind, type DocumentSymbol } from 'vscode-languageserver';
import type { TextDocument } from 'vscode-languageserver-textdocument';
import type { Brace, Element, Script, Statement } from '../syntax/ast.js';

/** A word or a quoted string used as a name. */
function nameOf(element: Element | undefined): { text: string; start: number; end: number } | null {
  if (element?.kind === 'word') return { text: element.text, start: element.start, end: element.end };
  if (element?.kind === 'string' && element.closed) return { text: element.value, start: element.start, end: element.end };
  return null;
}

/** Whether the statement is only a menu path such as "/ip firewall filter", the header of a section in an export. */
function isMenuHeader(statement: Statement): boolean {
  return statement.prefix === '/' && statement.elements.length > 0 && statement.elements.every((e) => e.kind === 'word');
}

/**
 * The outline of a script: function definitions (:global name do={ ... }), variables declared with :global or :local,
 * and the menu path headers that divide an export into sections.
 */
export function documentSymbols(document: TextDocument, script: Script): DocumentSymbol[] {
  const range = (start: number, end: number) => ({ start: document.positionAt(start), end: document.positionAt(end) });

  function fromStatements(statements: Statement[], depth: number): DocumentSymbol[] {
    const out: DocumentSymbol[] = [];
    let section: { symbol: DocumentSymbol; commands: number } | null = null;

    const closeSection = (until: number): void => {
      if (!section) return;
      section.symbol.range = range(document.offsetAt(section.symbol.range.start), until);
      section.symbol.detail = `${section.commands} ${section.commands === 1 ? 'command' : 'commands'}`;
      section = null;
    };

    for (const statement of statements) {
      if (depth === 0 && isMenuHeader(statement)) {
        closeSection(statement.start);
        const path = statement.elements.map((e) => (e.kind === 'word' ? e.text : '')).join(' ');
        const symbol: DocumentSymbol = {
          name: `/${path}`,
          kind: SymbolKind.Namespace,
          range: range(statement.start, statement.end),
          selectionRange: range(statement.start, statement.end),
        };
        out.push(symbol);
        section = { symbol, commands: 0 };
        continue;
      }
      if (section) section.commands++;

      const head = statement.elements[0];
      if (head?.kind !== 'word' || (head.text !== 'global' && head.text !== 'local')) continue;
      const name = nameOf(statement.elements[1]);
      if (!name) continue;

      const body = statement.elements
        .slice(2)
        .find((e): e is Extract<Element, { kind: 'named' }> => e.kind === 'named' && e.name.kind === 'word' && e.name.text === 'do');
      const block = body?.value?.kind === 'brace' ? (body.value as Brace) : null;
      const symbol: DocumentSymbol = {
        name: name.text,
        kind: block ? SymbolKind.Function : SymbolKind.Variable,
        detail: head.text,
        range: range(statement.start, statement.end),
        selectionRange: range(name.start, name.end),
      };
      if (block) {
        const children = fromStatements(block.body, depth + 1);
        if (children.length > 0) symbol.children = children;
      }
      out.push(symbol);
    }
    if (section) closeSection(statements[statements.length - 1]?.end ?? script.end);
    return out;
  }

  return fromStatements(script.statements, 0);
}
