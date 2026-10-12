import { execFileSync, spawn, type ChildProcessWithoutNullStreams } from 'node:child_process';
import { join } from 'node:path';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { TestClient } from './client.js';

const root = join(import.meta.dirname, '..', '..');
const cli = join(root, 'lib', 'cli.mjs');

let child: ChildProcessWithoutNullStreams;
let client: TestClient;
const stderr: string[] = [];

beforeAll(async () => {
  execFileSync(process.execPath, [join(root, 'scripts', 'build.mjs')], { cwd: root });
  child = spawn(process.execPath, [cli, '--stdio'], { cwd: root });
  child.stderr.on('data', (chunk: Buffer) => stderr.push(chunk.toString()));
  client = new TestClient(child.stdout, child.stdin);
  await client.initialize();
}, 30000);

afterAll(async () => {
  await client.shutdown();
  await new Promise<void>((resolve) => {
    if (child.exitCode !== null) resolve();
    else child.once('exit', () => resolve());
  });
});

describe('the built binary over real stdio', () => {
  it('answers with well-formed protocol messages and nothing else on stdout', async () => {
    const pending = client.nextDiagnostics('file:///e2e.rsc');
    await client.open('file:///e2e.rsc', '/ip address add address=1.1.1.1/32 comment="x" # note\n');
    const diagnostics = await pending;
    expect(diagnostics.map((d) => d.code)).toEqual(['schema/unexpected-argument']);
    // A stray write to stdout would have broken the framing and been reported by the message reader.
    expect(client.errors).toEqual([]);
  });

  it('reports a clean file as clean', async () => {
    const pending = client.nextDiagnostics('file:///clean.rsc');
    await client.open('file:///clean.rsc', '/ip address\nadd address=1.1.1.1/32 interface=ether1\n');
    expect(await pending).toEqual([]);
  });
});

describe('the command line', () => {
  it('prints its version and usage', () => {
    const run = (...args: string[]): string => execFileSync(process.execPath, [cli, ...args], { encoding: 'utf8' });
    expect(run('--version')).toMatch(/^\d+\.\d+\.\d+/);
    expect(run('--help')).toContain('--stdio');
  });

  it('refuses to run without a transport', () => {
    expect(() => execFileSync(process.execPath, [cli], { stdio: 'pipe' })).toThrow(/use --stdio/);
  });
});
