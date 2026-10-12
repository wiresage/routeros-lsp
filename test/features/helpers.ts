import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { TextDocument } from 'vscode-languageserver-textdocument';
import { analyze, type AnalyzeOptions } from '../../src/analyze.js';
import { Schema } from '../../src/schema/schema.js';

export const miniSchema = Schema.fromJson(readFileSync(join(import.meta.dirname, '..', 'fixtures', 'mini-schema.json'), 'utf8'));

/** Splits "text with a | caret" into the document and the caret offset. */
export function withCaret(source: string, options: AnalyzeOptions = {}) {
  const offset = source.indexOf('|');
  if (offset < 0) throw new Error('no caret marker in ' + JSON.stringify(source));
  const text = source.slice(0, offset) + source.slice(offset + 1);
  const document = TextDocument.create('file:///t.rsc', 'routeros', 1, text);
  const analysis = analyze(text, { schema: miniSchema, ...options });
  return { document, analysis, offset, position: document.positionAt(offset) };
}
