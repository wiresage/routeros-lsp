import {
  TextDocumentSyncKind,
  TextDocuments,
  type Connection,
  type InitializeParams,
  type InitializeResult,
} from 'vscode-languageserver';
import { TextDocument } from 'vscode-languageserver-textdocument';
import { analyze, bundledSchema } from './analyze.js';
import { DEFAULT_SETTINGS, parseSettings, type Settings } from './config.js';
import { completions } from './features/completion.js';
import { toDiagnostics } from './features/diagnostics.js';
import { foldingRanges } from './features/folding.js';
import { hoverAt } from './features/hover.js';
import { documentSymbols } from './features/symbols.js';
import { Schema } from './schema/schema.js';
import { NAME, VERSION } from './version.js';

/** Wires the language features to an LSP connection. The caller starts listening. */
export function createServer(connection: Connection): void {
  const documents = new TextDocuments(TextDocument);
  let settings: Settings = DEFAULT_SETTINGS;
  let schema: Schema | null = null;

  const warn = (message: string): void => connection.console.warn(`${NAME}: ${message}`);

  function apply(raw: unknown): void {
    settings = parseSettings(raw, warn);
    schema = loadSchema(settings.schema, warn);
  }

  async function validate(document: TextDocument): Promise<void> {
    const diagnostics = toDiagnostics(document, { ...settings, schema });
    await connection.sendDiagnostics({ uri: document.uri, version: document.version, diagnostics });
  }

  connection.onInitialize((params: InitializeParams): InitializeResult => {
    apply(params.initializationOptions);
    return {
      serverInfo: { name: NAME, version: VERSION },
      capabilities: {
        textDocumentSync: TextDocumentSyncKind.Incremental,
        documentSymbolProvider: true,
        foldingRangeProvider: true,
        hoverProvider: true,
        completionProvider: { triggerCharacters: ['$', ':', '/', '=', ' '] },
      },
    };
  });

  connection.onDidChangeConfiguration((change) => {
    apply(change.settings);
    for (const document of documents.all()) void validate(document);
  });

  documents.onDidChangeContent((event) => {
    void validate(event.document);
  });

  documents.onDidClose((event) => {
    void connection.sendDiagnostics({ uri: event.document.uri, diagnostics: [] });
  });

  connection.onDocumentSymbol((params) => {
    const document = documents.get(params.textDocument.uri);
    return document ? documentSymbols(document, analyze(document.getText()).script) : [];
  });

  connection.languages.foldingRange.on((params) => {
    const document = documents.get(params.textDocument.uri);
    return document ? foldingRanges(document, analyze(document.getText()).script) : [];
  });

  // A bug in one feature must not take the server down; the request just gets no answer.
  function guarded<T>(name: string, fallback: T, run: () => T): T {
    try {
      return run();
    } catch (error) {
      connection.console.error(`${NAME}: ${name} failed: ${error instanceof Error ? (error.stack ?? error.message) : String(error)}`);
      return fallback;
    }
  }

  connection.onHover((params) =>
    guarded('hover', null, () => {
      const document = documents.get(params.textDocument.uri);
      return document ? hoverAt(document, analyze(document.getText(), { ...settings, schema }), document.offsetAt(params.position)) : null;
    }),
  );

  connection.onCompletion((params) =>
    guarded('completion', [], () => {
      const document = documents.get(params.textDocument.uri);
      return document ? completions(document, analyze(document.getText(), { ...settings, schema }), schema, params.position) : [];
    }),
  );

  documents.listen(connection);
}

function loadSchema(setting: string, warn: (message: string) => void): Schema | null {
  if (setting === 'off') return null;
  if (setting !== 'bundled') {
    try {
      return Schema.fromFile(setting);
    } catch (error) {
      warn(`cannot read the command database "${setting}" (${String(error)}); using the bundled one`);
    }
  }
  const bundled = bundledSchema();
  if (!bundled) warn('no bundled command database found; menu, command and parameter checks are off');
  return bundled;
}
