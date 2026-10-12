import { MarkupKind, type Hover } from 'vscode-languageserver';
import type { TextDocument } from 'vscode-languageserver-textdocument';
import type { Analysis } from '../analyze.js';
import type { WordResolution } from '../checker/commands.js';
import { describeArg } from './completion.js';

function range(document: TextDocument, start: number, end: number) {
  return { start: document.positionAt(start), end: document.positionAt(end) };
}

function resolutionText(r: WordResolution): string {
  const path = `/${r.path.join(' ')}`;
  if (r.kind === 'parameter') {
    const arg = r.arg;
    const header = `**${r.name}**${r.required ? ' (required)' : ''} parameter of \`${path}\``;
    return [header, describeArg(r.name, arg)?.value].filter(Boolean).join('\n\n');
  }
  const header = r.kind === 'menu' ? `**${path}** menu` : `**${path}** command`;
  const lines = [header, r.node.d];
  if (r.kind === 'menu') {
    const names = Object.keys(r.node.c ?? {});
    if (names.length > 0) lines.push(`Contains: ${names.slice(0, 16).map((n) => `\`${n}\``).join(', ')}${names.length > 16 ? ', ...' : ''}`);
  } else {
    const required = r.node.r ?? [];
    if (required.length > 0) lines.push(`Required: ${required.map((n) => `\`${n}\``).join(', ')}`);
    const optional = Object.keys(r.node.a ?? {}).filter((n) => !required.includes(n));
    if (optional.length > 0) lines.push(`Parameters: ${optional.slice(0, 20).map((n) => `\`${n}\``).join(', ')}${optional.length > 20 ? ', ...' : ''}`);
  }
  return lines.filter(Boolean).join('\n\n');
}

/** Hover for a menu, command, parameter or variable at the offset. */
export function hoverAt(document: TextDocument, analysis: Analysis, offset: number): Hover | null {
  const candidates = (analysis.commands?.resolutions ?? []).filter((r) => r.start <= offset && offset <= r.end);
  const word = candidates.sort((a, b) => a.end - a.start - (b.end - b.start))[0];
  if (word) {
    return { contents: { kind: MarkupKind.Markdown, value: resolutionText(word) }, range: range(document, word.start, word.end) };
  }

  const reference = analysis.bound.references.find((r) => r.start <= offset && offset <= r.end);
  if (reference) {
    const declaration =
      reference.resolution.kind === 'declared' || reference.resolution.kind === 'global-elsewhere' || reference.resolution.kind === 'local-elsewhere'
        ? reference.resolution.declaration
        : null;
    const line = declaration ? document.positionAt(declaration.start).line + 1 : 0;
    const text = declaration
      ? `**$${reference.name}**: ${declaration.kind} variable, declared on line ${line}${reference.resolution.kind === 'local-elsewhere' ? ' but not in scope here' : ''}.`
      : `**$${reference.name}**: not declared in this file.`;
    return { contents: { kind: MarkupKind.Markdown, value: text }, range: range(document, reference.start, reference.end) };
  }
  const declaration = analysis.bound.declarations.find((d) => d.start <= offset && offset <= d.end);
  if (declaration) {
    return { contents: { kind: MarkupKind.Markdown, value: `**${declaration.name}**: ${declaration.kind} variable.` }, range: range(document, declaration.start, declaration.end) };
  }
  return null;
}
