import {
  TextDocumentSyncKind,
  TextDocuments,
  type Connection,
  type InitializeParams,
  type InitializeResult,
} from 'vscode-languageserver';
import { TextDocument } from 'vscode-languageserver-textdocument';
import { analyze } from './analyze.js';
import { DEFAULT_SETTINGS, parseSettings, type Settings } from './config.js';
import { toDiagnostics } from './features/diagnostics.js';
import { foldingRanges } from './features/folding.js';
import { documentSymbols } from './features/symbols.js';
import { NAME, VERSION } from './version.js';

/** Wires the language features to an LSP connection. The caller starts listening. */
export function createServer(connection: Connection): void {
  const documents = new TextDocuments(TextDocument);
  let settings: Settings = DEFAULT_SETTINGS;

  const warn = (message: string): void => connection.console.warn(`${NAME}: ${message}`);

  async function validate(document: TextDocument): Promise<void> {
    const diagnostics = toDiagnostics(document, { severities: settings.severities });
    await connection.sendDiagnostics({ uri: document.uri, version: document.version, diagnostics });
  }

  connection.onInitialize((params: InitializeParams): InitializeResult => {
    settings = parseSettings(params.initializationOptions, warn);
    return {
      serverInfo: { name: NAME, version: VERSION },
      capabilities: {
        textDocumentSync: TextDocumentSyncKind.Incremental,
        documentSymbolProvider: true,
        foldingRangeProvider: true,
      },
    };
  });

  connection.onDidChangeConfiguration((change) => {
    settings = parseSettings(change.settings, warn);
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

  documents.listen(connection);
}
