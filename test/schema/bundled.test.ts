import { statSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { Schema, type NodeInfo } from '../../src/schema/schema.js';

const schema = Schema.bundled();

function at(...path: string[]): NodeInfo {
  let node = schema!.root;
  for (const name of path) {
    const next = node.c?.[name];
    if (!next) throw new Error(`/${path.join(' ')} is not in the bundled database`);
    node = next;
  }
  return node;
}

function count(node: NodeInfo): { menus: number; commands: number } {
  let menus = 0;
  let commands = 0;
  const walk = (n: NodeInfo): void => {
    if (n.k) commands++;
    else menus++;
    for (const child of Object.values(n.c ?? {})) walk(child);
  };
  walk(node);
  return { menus, commands };
}

// These facts were read off a RouterOS 7.21.4 CHR by tools/gen_schema.py. They guard the generated file against a bad run.
describe('the bundled command database', () => {
  it('is found and describes RouterOS 7.21.4', () => {
    expect(schema).not.toBeNull();
    expect(schema?.version).toBe('7.21.4');
  });

  it('holds the whole command tree', () => {
    const { menus, commands } = count(schema!.root);
    expect(menus).toBeGreaterThan(400);
    expect(commands).toBeGreaterThan(3900);
  });

  it('stays small enough to ship', () => {
    expect(statSync(join(import.meta.dirname, '..', '..', 'data', 'routeros-7.21.4.json.gz')).size).toBeLessThan(400 * 1024);
  });

  it('knows the required parameters', () => {
    expect(at('ip', 'address', 'add').r).toEqual(['address', 'interface']);
    expect(at('interface', 'vlan', 'add').r).toEqual(expect.arrayContaining(['vlan-id', 'interface']));
    expect(at('put').r).toEqual(['message']);
    expect(at('system', 'identity', 'set').r).toBeUndefined();
  });

  it('knows how many unnamed arguments a command takes', () => {
    expect(at('ip', 'address', 'add').u ?? 0).toBe(0);
    expect(at('ip', 'address', 'print').u ?? 0).toBe(0);
    expect(at('ip', 'address', 'set').u).toBe(1);
    expect(at('put').u).toBe(1);
    expect(at('local').u).toBe(2);
    // a condition is an unnamed group, a script an unnamed block
    expect(at('if').u).toBeGreaterThanOrEqual(1);
    expect(at('while').u).toBeGreaterThanOrEqual(1);
    expect(at('execute').u).toBeGreaterThanOrEqual(1);
  });

  it('marks flags only where a bare name is a flag', () => {
    const print = at('ip', 'address', 'print').a!;
    for (const flag of ['detail', 'brief', 'count-only', 'as-value', 'without-paging', 'terse']) expect(print[flag]?.f, flag).toBe(1);
    for (const valued of ['from', 'where', 'file', 'interval', 'proplist']) expect(print[valued]?.f, valued).toBeUndefined();
    expect(at('ip', 'address', 'add').a!['comment']?.f).toBeUndefined();
  });

  it('keeps fixed lists of values and leaves out values that belong to one router', () => {
    const action = at('ip', 'firewall', 'filter', 'add').a!['action']!;
    expect(action.e).toEqual(expect.arrayContaining(['accept', 'drop', 'jump']));
    const interfaceArg = at('ip', 'address', 'add').a!['interface']!;
    expect(interfaceArg.e).toBeUndefined();
    expect(interfaceArg.t ?? '').not.toContain('ether1');
    expect(at('ip', 'address', 'add').a!['disabled']?.e).toEqual(['no', 'yes']);
  });

  it('describes menus, commands and parameters', () => {
    expect(at('ip').d).toBeTruthy();
    expect(at('ip', 'address', 'add').d).toBe('Create a new item');
    expect(at('ip', 'address', 'add').a!['address']).toMatchObject({ d: 'Local IP address', t: 'A.B.C.D (IP address)' });
  });
});
