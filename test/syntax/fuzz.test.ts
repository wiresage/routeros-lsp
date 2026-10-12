import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import type { Node } from '../../src/syntax/ast.js';
import { parse } from '../../src/syntax/parser.js';
import { children, visit } from '../../src/syntax/walk.js';
import cases from '../conformance/cases.json' with { type: 'json' };

/** Small deterministic generator, so a failing input can be reproduced from its seed. */
function rng(seed: number): () => number {
  let s = seed >>> 0;
  return () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const PIECES = ['"', '$', '[', ']', '(', ')', '{', '}', '\\', '\n', '\r\n', ';', '#', '=', ' ', ':', '/', '!', '-', '->', '"x"', '$(', '$[', 'where', '\\\n', 'é', '﻿'];

const fixtureDir = join(import.meta.dirname, '..', 'fixtures');
const seeds: string[] = [
  ...(cases as { source: string }[]).map((c) => c.source),
  ...['scripts', 'crlf', 'cr'].flatMap((d) =>
    readdirSync(join(fixtureDir, d))
      .filter((f) => f.endsWith('.rsc'))
      .map((f) => readFileSync(join(fixtureDir, d, f), 'utf8')),
  ),
];

function mutate(text: string, next: () => number): string {
  let out = text;
  const edits = 1 + Math.floor(next() * 6);
  for (let i = 0; i < edits; i++) {
    const at = Math.floor(next() * (out.length + 1));
    const kind = Math.floor(next() * 4);
    if (kind === 0) out = out.slice(0, at) + out.slice(at + 1 + Math.floor(next() * 8));
    else if (kind === 1) out = out.slice(0, at) + PIECES[Math.floor(next() * PIECES.length)]! + out.slice(at);
    else if (kind === 2) out = out.slice(0, at);
    else out = out.slice(0, at) + out.slice(Math.floor(next() * (out.length + 1)), Math.floor(next() * (out.length + 1))) + out.slice(at);
  }
  return out;
}

function checkTree(text: string, root: Node): string | null {
  let problem: string | null = null;
  visit(root, (node, parent) => {
    if (problem) return false;
    if (node.start < 0 || node.end > text.length || node.start > node.end) {
      problem = `${node.kind} has span ${node.start}..${node.end} in a text of ${text.length}`;
      return false;
    }
    if (parent && (node.start < parent.start || node.end > parent.end) && parent.kind !== 'string') {
      problem = `${node.kind} ${node.start}..${node.end} escapes its ${parent.kind} ${parent.start}..${parent.end}`;
      return false;
    }
    let previousEnd = -1;
    for (const child of children(node)) {
      if (child.start < previousEnd) {
        problem = `children of ${node.kind} overlap or are out of order at ${child.start}`;
        return false;
      }
      previousEnd = child.end;
    }
    return undefined;
  });
  return problem;
}

describe('parser robustness', () => {
  it('has input to mutate', () => {
    expect(seeds.length).toBeGreaterThan(600);
  });

  it('never throws, hangs or builds an inconsistent tree on mutated input', () => {
    const next = rng(20261012);
    const started = Date.now();
    for (let i = 0; i < 4000; i++) {
      const base = seeds[Math.floor(next() * seeds.length)]!;
      const text = mutate(base, next);
      let result;
      try {
        result = parse(text);
      } catch (error) {
        throw new Error(`parse threw on iteration ${i}: ${String(error)}\n${JSON.stringify(text)}`, { cause: error });
      }
      const problem = checkTree(text, result.script);
      expect(problem, `iteration ${i}: ${problem}\n${JSON.stringify(text)}`).toBeNull();
      for (const d of result.diagnostics) {
        expect(d.start >= 0 && d.end <= text.length && d.start <= d.end, `iteration ${i}: bad range ${d.start}..${d.end}\n${JSON.stringify(text)}`).toBe(true);
      }
    }
    expect(Date.now() - started).toBeLessThan(20000);
  });

  it('parses a large file quickly', () => {
    const line = '/ip firewall filter add action=accept chain=input comment="rule" connection-state=established,related\n';
    const text = line.repeat(20000);
    const t0 = Date.now();
    const { script, diagnostics } = parse(text);
    expect(script.statements).toHaveLength(20000);
    expect(diagnostics).toEqual([]);
    expect(Date.now() - t0).toBeLessThan(3000);
  });
});
