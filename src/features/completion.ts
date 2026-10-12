import { CompletionItemKind, MarkupKind, type CompletionItem, type Position, type Range } from 'vscode-languageserver';
import type { TextDocument } from 'vscode-languageserver-textdocument';
import type { Analysis } from '../analyze.js';
import { variablesAt } from '../binder/query.js';
import type { Path, WordResolution } from '../checker/commands.js';
import type { ArgInfo, NodeInfo, Schema } from '../schema/schema.js';
import type { Brace, Element, Node, Script, Statement, Subst } from '../syntax/ast.js';
import { ancestorsAt } from '../syntax/walk.js';

type Holder = Script | Brace | Subst;

function isHolder(node: Node): node is Holder {
  return node.kind === 'script' || node.kind === 'brace' || node.kind === 'subst';
}

/** Whether the offset is inside a string literal, not just at its edge. */
function insideString(chain: Node[], offset: number): boolean {
  return chain.some((n) => n.kind === 'string' && ((n.start < offset && offset < n.end) || (!n.closed && offset >= n.end)));
}

function oneLine(text: string | undefined): string {
  return text ? text.split('\n')[0]! : '';
}

function markdown(...parts: Array<string | undefined>): { kind: typeof MarkupKind.Markdown; value: string } {
  return { kind: MarkupKind.Markdown, value: parts.filter((p) => p).join('\n\n') };
}

/** Completion for the position, from the command database and the variables in scope. */
export function completions(document: TextDocument, analysis: Analysis, schema: Schema | null, position: Position): CompletionItem[] {
  const text = document.getText();
  const offset = document.offsetAt(position);
  if (analysis.script.comments.some((c) => offset > c.start && offset <= c.end)) return [];

  const dollar = /\$([A-Za-z0-9]*)$/.exec(text.slice(0, offset));
  if (dollar) {
    const typed = dollar[1]!;
    const range = rangeOf(document, offset - typed.length, offset);
    return variablesAt(analysis.bound, offset).map((d) => ({
      label: d.name,
      kind: CompletionItemKind.Variable,
      detail: `${d.kind} variable`,
      textEdit: { range, newText: d.name },
    }));
  }

  const chain = ancestorsAt(analysis.script, offset);
  if (insideString(chain, offset) || !schema || !analysis.commands) return [];

  const holder = [...chain].reverse().find(isHolder);
  if (!holder) return [];
  const list = holder.kind === 'script' ? holder.statements : holder.body;
  const statement = [...list].reverse().find((s) => s.start <= offset && (offset <= s.end || /^[ \t]*$/.test(text.slice(s.end, offset))));
  const commands = analysis.commands;

  const nodeAt = (path: readonly string[]): NodeInfo => {
    let node = schema.root;
    for (const name of path) node = node.c?.[name] ?? node;
    return node;
  };

  if (!statement) {
    const previous = [...list].reverse().find((s) => s.end <= offset);
    const path: Path | undefined = previous ? (commands.after.has(previous) ? commands.after.get(previous) : commands.contexts.get(previous)) : holder.kind === 'script' ? [] : commands.bodies.get(holder);
    if (!path) return [];
    return menuItems(nodeAt(path), rangeOf(document, offset, offset));
  }

  const elements = statement.elements;
  if (elements.some((e) => e.kind === 'word' && e.text === 'where' && e.end <= offset)) return [];

  const partial = partialWord(statement, offset);
  const range = partial ? rangeOf(document, partial.start + partial.skip, offset) : rangeOf(document, offset, offset);
  const typedStart = partial ? partial.start : offset;
  const inside = commands.resolutions.filter((r) => r.start >= statement.start && r.end <= statement.end);
  const before = inside.filter((r) => r.end <= offset);
  const commandRes = [...before].reverse().find((r) => r.kind === 'command');

  // Typing the command word itself counts as choosing a command, not as an argument.
  if (!commandRes || (partial && partial.start === commandRes.start)) {
    const menus = before.filter((r) => r.kind === 'menu' && r.end <= typedStart);
    const last = menus[menus.length - 1];
    let path: Path | undefined;
    if (last) path = last.path;
    else if (statement.prefix === '/' || statement.prefix === ':') path = [];
    else path = commands.contexts.get(statement);
    if (!path) return [];
    return menuItems(nodeAt(path), range);
  }

  const command = commandRes.node;
  // the word being typed does not count as given
  const provided = new Set(inside.filter((r): r is Extract<WordResolution, { kind: 'parameter' }> => r.kind === 'parameter' && r.end <= typedStart).map((r) => r.name));

  const named = elements.find((e): e is Extract<Element, { kind: 'named' }> => e.kind === 'named' && e.name.start < offset && offset > e.equalsAt && offset <= (e.value?.end ?? e.equalsAt + 1));
  if (named) {
    const parameter = inside.find((r): r is Extract<WordResolution, { kind: 'parameter' }> => r.kind === 'parameter' && r.start === named.name.start);
    const valueStart = named.value && named.value.kind === 'word' ? named.value.start : offset;
    return valueItems(parameter?.arg, rangeOf(document, valueStart, offset));
  }

  return parameterItems(command, provided, range);
}

function rangeOf(document: TextDocument, start: number, end: number): Range {
  return { start: document.positionAt(start), end: document.positionAt(end) };
}

/** The word being typed at the cursor, with how many leading characters belong to a path separator. */
function partialWord(statement: Statement, offset: number): { start: number; skip: number } | null {
  for (const e of statement.elements) {
    if (e.kind === 'word' && e.start < offset && offset <= e.end) {
      return { start: e.start, skip: Math.max(0, e.text.lastIndexOf('/') + 1) };
    }
    if (e.kind === 'named' && e.name.start < offset && offset <= e.equalsAt) return { start: e.name.start, skip: 0 };
  }
  return null;
}

function menuItems(node: NodeInfo, range: Range): CompletionItem[] {
  const items: CompletionItem[] = [];
  for (const [name, child] of Object.entries(node.c ?? {})) {
    items.push({
      label: name,
      kind: child.k ? CompletionItemKind.Function : CompletionItemKind.Module,
      detail: oneLine(child.d),
      documentation: child.d ? markdown(child.d) : undefined,
      textEdit: { range, newText: name },
      sortText: (child.k ? '1' : '0') + name,
    });
  }
  return items;
}

function parameterItems(command: NodeInfo, provided: ReadonlySet<string>, range: Range): CompletionItem[] {
  const items: CompletionItem[] = [];
  const required = new Set(command.r ?? []);
  for (const [name, arg] of Object.entries(command.a ?? {})) {
    if (provided.has(name)) continue;
    const flag = arg.f === 1;
    items.push({
      label: name,
      kind: CompletionItemKind.Property,
      detail: [required.has(name) ? 'required' : '', arg.t ?? ''].filter(Boolean).join(', '),
      documentation: describeArg(name, arg),
      textEdit: { range, newText: flag ? name : `${name}=` },
      sortText: (required.has(name) ? '0' : '1') + name,
    });
  }
  return items;
}

function valueItems(arg: ArgInfo | undefined, range: Range): CompletionItem[] {
  return (arg?.e ?? []).map((value) => ({
    label: value,
    kind: CompletionItemKind.EnumMember,
    textEdit: { range, newText: value },
  }));
}

export function describeArg(name: string, arg: ArgInfo): { kind: typeof MarkupKind.Markdown; value: string } | undefined {
  if (!arg.d && !arg.t && !arg.e?.length) return undefined;
  const values = arg.e?.length ? `${arg.x ? 'Values' : 'Suggested values'}: ${arg.e.slice(0, 20).map((v) => `\`${v}\``).join(', ')}${arg.e.length > 20 ? ', ...' : ''}` : undefined;
  return markdown(arg.d, arg.t ? `Type: \`${arg.t}\`` : undefined, values);
}
