import type { Readable, Writable } from 'node:stream';
import {
  createMessageConnection,
  StreamMessageReader,
  StreamMessageWriter,
  type MessageConnection,
} from 'vscode-jsonrpc/node';
import type { Diagnostic, FoldingRange, DocumentSymbol, InitializeResult, PublishDiagnosticsParams } from 'vscode-languageserver';

/** A minimal LSP client for tests: just enough to open documents and read what the server says. */
export class TestClient {
  readonly connection: MessageConnection;
  private readonly published = new Map<string, PublishDiagnosticsParams[]>();
  private readonly waiters: Array<() => void> = [];
  readonly errors: unknown[] = [];

  constructor(fromServer: Readable, toServer: Writable) {
    this.connection = createMessageConnection(new StreamMessageReader(fromServer), new StreamMessageWriter(toServer));
    this.connection.onNotification('textDocument/publishDiagnostics', (params: PublishDiagnosticsParams) => {
      const list = this.published.get(params.uri) ?? [];
      list.push(params);
      this.published.set(params.uri, list);
      for (const wake of this.waiters.splice(0)) wake();
    });
    this.connection.onError((error) => this.errors.push(error));
    this.connection.onRequest('workspace/configuration', () => []);
    this.connection.onRequest('client/registerCapability', () => null);
    this.connection.listen();
  }

  initialize(initializationOptions?: unknown): Promise<InitializeResult> {
    return this.connection
      .sendRequest<InitializeResult>('initialize', {
        processId: null,
        rootUri: null,
        capabilities: {},
        ...(initializationOptions === undefined ? {} : { initializationOptions }),
      })
      .then(async (result) => {
        await this.connection.sendNotification('initialized', {});
        return result;
      });
  }

  open(uri: string, text: string, version = 1): Promise<void> {
    return this.connection.sendNotification('textDocument/didOpen', {
      textDocument: { uri, languageId: 'routeros', version, text },
    });
  }

  change(uri: string, text: string, version: number): Promise<void> {
    return this.connection.sendNotification('textDocument/didChange', {
      textDocument: { uri, version },
      contentChanges: [{ text }],
    });
  }

  close(uri: string): Promise<void> {
    return this.connection.sendNotification('textDocument/didClose', { textDocument: { uri } });
  }

  configure(settings: unknown): Promise<void> {
    return this.connection.sendNotification('workspace/didChangeConfiguration', { settings });
  }

  symbols(uri: string): Promise<DocumentSymbol[]> {
    return this.connection.sendRequest('textDocument/documentSymbol', { textDocument: { uri } });
  }

  folding(uri: string): Promise<FoldingRange[]> {
    return this.connection.sendRequest('textDocument/foldingRange', { textDocument: { uri } });
  }

  /** Resolves with the next diagnostics notification for `uri` that arrives after this call. */
  nextDiagnostics(uri: string, timeoutMs = 5000): Promise<Diagnostic[]> {
    const seen = this.published.get(uri)?.length ?? 0;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error(`no diagnostics for ${uri} within ${timeoutMs} ms`)), timeoutMs);
      const check = (): void => {
        const list = this.published.get(uri) ?? [];
        if (list.length > seen) {
          clearTimeout(timer);
          resolve(list[list.length - 1]!.diagnostics);
        } else {
          this.waiters.push(check);
        }
      };
      check();
    });
  }

  async shutdown(): Promise<void> {
    await this.connection.sendRequest('shutdown');
    await this.connection.sendNotification('exit');
    this.connection.dispose();
  }
}
