import { PassThrough } from 'node:stream';
import { createConnection, ProposedFeatures } from 'vscode-languageserver/node';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { createServer } from '../../src/server.js';
import { TestClient } from './client.js';

const URI = 'file:///work/test.rsc';

let client: TestClient;

async function start(initializationOptions?: unknown): Promise<void> {
  const toServer = new PassThrough();
  const fromServer = new PassThrough();
  const connection = createConnection(ProposedFeatures.all, toServer, fromServer);
  createServer(connection);
  connection.listen();
  client = new TestClient(fromServer, toServer);
  await client.initialize(initializationOptions);
}

beforeEach(async () => {
  await start();
});

afterEach(async () => {
  await client.shutdown();
});

describe('server over a stream pair', () => {
  it('announces what it can do', async () => {
    const toServer = new PassThrough();
    const fromServer = new PassThrough();
    const connection = createConnection(ProposedFeatures.all, toServer, fromServer);
    createServer(connection);
    connection.listen();
    const second = new TestClient(fromServer, toServer);
    const result = await second.initialize();
    expect(result.serverInfo?.name).toBe('routeros-lsp');
    expect(result.capabilities).toMatchObject({
      textDocumentSync: 2,
      documentSymbolProvider: true,
      foldingRangeProvider: true,
    });
    await second.shutdown();
  });

  it('publishes diagnostics when a document opens', async () => {
    const pending = client.nextDiagnostics(URI);
    await client.open(URI, ':put 1 # trailing\n/ip address print\n');
    const diagnostics = await pending;
    expect(diagnostics).toHaveLength(1);
    expect(diagnostics[0]).toMatchObject({
      code: 'schema/unexpected-argument',
      source: 'routeros-lsp',
      severity: 1,
      range: { start: { line: 0, character: 7 }, end: { line: 0, character: 8 } },
    });
  });

  it('labels device-only and unspecified rules in the message', async () => {
    const pending = client.nextDiagnostics(URI);
    await client.open(URI, ':put "a"\n}\n');
    const [diagnostic] = await pending;
    expect(diagnostic?.code).toBe('syntax/stray-closer');
    expect(diagnostic?.severity).toBe(2);
    expect(diagnostic?.message).toContain('the documentation does not specify this');
  });

  it('clears diagnostics once the text is fixed and on close', async () => {
    let pending = client.nextDiagnostics(URI);
    await client.open(URI, ':put "unterminated\n');
    expect((await pending).map((d) => d.code)).toEqual(['syntax/unterminated-string']);

    pending = client.nextDiagnostics(URI);
    await client.change(URI, ':put "fixed"\n', 2);
    expect(await pending).toEqual([]);

    pending = client.nextDiagnostics(URI);
    await client.change(URI, ':put (\n', 3);
    expect((await pending).map((d) => d.code)).toContain('syntax/missing-closer');

    pending = client.nextDiagnostics(URI);
    await client.close(URI);
    expect(await pending).toEqual([]);
  });

  it('applies rule severities from configuration and revalidates open documents', async () => {
    let pending = client.nextDiagnostics(URI);
    await client.open(URI, ':put 1 # c\n');
    expect((await pending)[0]?.severity).toBe(1);

    pending = client.nextDiagnostics(URI);
    await client.configure({ routeros: { severities: { 'schema/unexpected-argument': 'warning' } } });
    expect((await pending)[0]?.severity).toBe(2);

    pending = client.nextDiagnostics(URI);
    await client.configure({ severities: { 'schema/unexpected-argument': 'off', 'syntax/trailing-comment': 'off' } });
    expect(await pending).toEqual([]);
  });

  it('reads severities from initialization options', async () => {
    await client.shutdown();
    await start({ severities: { 'schema/unexpected-argument': 'hint' } });
    const pending = client.nextDiagnostics(URI);
    await client.open(URI, ':put 1 # c\n');
    expect((await pending)[0]?.severity).toBe(4);
  });

  it('returns a symbol outline', async () => {
    const pending = client.nextDiagnostics(URI);
    await client.open(
      URI,
      [
        '/ip firewall filter',
        'add chain=input',
        'add chain=forward',
        '/system script',
        ':global hello do={',
        '  :local inner 1',
        '  :put $inner',
        '}',
        ':global counter 0',
        '',
      ].join('\n'),
    );
    await pending;
    const symbols = await client.symbols(URI);
    expect(symbols.map((s) => [s.name, s.kind, s.detail])).toEqual([
      ['/ip firewall filter', 3, '2 commands'],
      ['/system script', 3, '2 commands'],
      ['hello', 12, 'global'],
      ['counter', 13, 'global'],
    ]);
    // the function is nested under its section; the section ranges stop before the next header
    expect(symbols[0]?.range.end.line).toBeLessThan(symbols[1]!.range.start.line + 1);
  });

  it('returns folding ranges', async () => {
    const pending = client.nextDiagnostics(URI);
    await client.open(URI, ['# one', '# two', ':if (true) do={', '  :put 1', '}', ':put "a', 'b"', ''].join('\n'));
    await pending;
    const ranges = await client.folding(URI);
    expect(ranges).toEqual([
      { startLine: 0, endLine: 1, kind: 'comment' },
      { startLine: 2, endLine: 3 },
      { startLine: 5, endLine: 6 },
    ]);
  });

  it('survives requests for documents it does not have', async () => {
    expect(await client.symbols('file:///nope.rsc')).toEqual([]);
    expect(await client.folding('file:///nope.rsc')).toEqual([]);
  });
});
