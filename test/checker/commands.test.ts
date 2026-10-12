import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { analyze } from '../../src/analyze.js';
import { Schema, matchName, suggest } from '../../src/schema/schema.js';

const schema = Schema.fromJson(readFileSync(join(import.meta.dirname, '..', 'fixtures', 'mini-schema.json'), 'utf8'));

function rules(text: string): string[] {
  return analyze(text, { schema }).findings.filter((f) => f.rule.startsWith('schema/')).map((f) => f.rule);
}

function messages(text: string): string[] {
  return analyze(text, { schema }).findings.filter((f) => f.rule.startsWith('schema/')).map((f) => f.message);
}

describe('matching names', () => {
  const table = { address: 1, accounting: 2, add: 3, route: 4 };
  it('prefers an exact match, then a unique prefix', () => {
    expect(matchName(table, 'add')).toMatchObject({ kind: 'found', name: 'add' });
    expect(matchName(table, 'rou')).toMatchObject({ kind: 'found', name: 'route' });
    expect(matchName(table, 'ac')).toMatchObject({ kind: 'found', name: 'accounting' });
  });
  it('reports ambiguity and absence', () => {
    expect(matchName(table, 'a')).toEqual({ kind: 'ambiguous', candidates: ['accounting', 'add', 'address'] });
    expect(matchName(table, 'x')).toEqual({ kind: 'none' });
    expect(matchName(table, '')).toEqual({ kind: 'none' });
    expect(matchName(undefined, 'a')).toEqual({ kind: 'none' });
  });
  it('is not fooled by inherited object keys', () => {
    expect(matchName({}, 'constructor')).toEqual({ kind: 'none' });
  });
  it('suggests close names', () => {
    expect(suggest(['filter', 'nat', 'mangle'], 'filtr')).toEqual(['filter']);
    expect(suggest(['filter', 'nat'], 'zzzzzz')).toEqual([]);
  });
});

describe('menus and commands', () => {
  it('accepts valid lines, with full names, prefixes and either path style', () => {
    expect(rules('/ip address print')).toEqual([]);
    expect(rules('/ip/address/print')).toEqual([]);
    expect(rules('/ip addr pr')).toEqual([]);
    expect(rules('ip address print')).toEqual([]);
    expect(rules(':put "x"')).toEqual([]);
    expect(rules(':pu "x"')).toEqual([]);
    expect(rules('put "x"')).toEqual([]);
  });

  it('reports an unknown menu or command and suggests the closest name', () => {
    expect(rules('/foo bar')).toEqual(['schema/unknown-command']);
    expect(rules('/ip address prnt')).toEqual(['schema/unknown-command']);
    expect(messages('/ip firewall filtr add')[0]).toContain("Did you mean 'filter'?");
  });

  it('reports an ambiguous abbreviation as an error', () => {
    const [finding] = analyze('/ip a print', { schema }).findings;
    expect(finding).toMatchObject({ rule: 'schema/ambiguous-name', severity: 'error' });
    expect(finding?.message).toContain('accounting, address');
  });

  it('keeps unknown names a warning by default, because the database depends on the device', () => {
    expect(analyze('/foo bar', { schema }).findings[0]?.severity).toBe('warning');
  });

  it('requires the colon for a global command inside a menu (probes s14 to s17)', () => {
    expect(rules('/ip address\nput "x"')).toEqual(['schema/unknown-command']);
    expect(messages('/ip address\nput "x"')[0]).toContain("Global commands need a ':'");
    expect(rules('/ip address\n:put "x"')).toEqual([]);
  });

  it('lets a colon lead into a menu, but a colon line does not become the current path', () => {
    expect(rules(':ip address print')).toEqual([]);
    expect(rules(':ip address\nprint')).toEqual(['schema/unknown-command']);
  });
});

describe('menu path state', () => {
  it('lets a path-only line set the path for the lines after it (s3)', () => {
    expect(rules('/ip address\nprint')).toEqual([]);
    expect(rules('/ip\naddress\nprint')).toEqual([]);
    expect(rules('/ip address; print')).toEqual([]);
  });

  it('does not let a full command change the path (s1, s2, s4, s5, s20)', () => {
    expect(rules('/ip address print\nadd address=1.1.1.1/32 interface=ether1')).toEqual(['schema/unknown-command']);
    expect(rules('/ip address\n/ip route print\nadd address=1.1.1.1/32 interface=ether1')).toEqual([]);
    // still in /ip address, which has no dst-address or gateway
    expect(rules('/ip address\n/ip route print\nadd dst-address=0.0.0.0/0 gateway=1.1.1.1')).toContain('schema/unknown-parameter');
  });

  it('resolves relative words only against the current menu (s11, s12)', () => {
    expect(rules('/ip address\nroute print')).toEqual(['schema/unknown-command']);
    expect(rules('/ip address\nsystem identity print')).toEqual(['schema/unknown-command']);
    expect(rules('/ip address\n/\nsystem identity print')).toEqual([]);
  });

  it('goes up with .. (s10, s19)', () => {
    expect(rules('/ip address\n..\nroute print')).toEqual([]);
    expect(rules('/ip address\n..route print')).toEqual([]);
  });

  it('carries a path change out of a bare block and a statement-level path block (l1, l12, l18)', () => {
    expect(rules('{ /ip route }\nadd dst-address=0.0.0.0/0 gateway=1.1.1.1')).toEqual([]);
    expect(rules('/ip { route }\nadd dst-address=0.0.0.0/0 gateway=1.1.1.1')).toEqual([]);
    expect(rules('/ip route\n{ /ip address }\nadd address=1.1.1.1/32 interface=ether1')).toEqual([]);
  });

  it('does not carry a change out of bodies and arguments (l2 to l17)', () => {
    for (const construct of [
      ':if (true) do={ /ip route }',
      ':put [/ip route]',
      ':local a { /ip route }',
      ':global f do={ /ip route }',
    ]) {
      expect(rules(`${construct}\nadd dst-address=0.0.0.0/0 gateway=1.1.1.1`), construct).toContain('schema/unknown-command');
    }
  });

  it('lets bodies and arguments start from the current path (s26, s29)', () => {
    expect(rules('/ip address\n:if (true) do={ print }')).toEqual([]);
    expect(rules('/ip address\n:put [print count-only]')).toEqual([]);
  });

  it('stops reporting relative words after a mistake in a path, until an absolute path resets it', () => {
    expect(rules('/ip nonsense\nprint\nadd address=1.1.1.1/32')).toEqual(['schema/unknown-command']);
    expect(rules('/ip nonsense\n/ip address\nprint')).toEqual(['schema/unknown-command']);
  });
});

describe('arguments', () => {
  it('accepts named parameters, flags and abbreviations', () => {
    expect(rules('/ip address add address=1.1.1.1/32 interface=ether1 comment="x"')).toEqual([]);
    expect(rules('/ip address add addr=1.1.1.1/32 inter=ether1')).toEqual([]);
    expect(rules('/ip address print detail count-only')).toEqual([]);
    expect(rules('/ip address print det')).toEqual([]);
  });

  it('reports an unknown parameter and suggests one', () => {
    expect(rules('/ip address add address=1.1.1.1/32 interface=ether1 nope=1')).toEqual(['schema/unknown-parameter']);
    expect(messages('/ip address add adress=1.1.1.1/32 interface=ether1')).toEqual([expect.stringContaining("Did you mean 'address'?")]);
  });

  it('reports a parameter given twice, also under an abbreviation', () => {
    expect(rules('/ip address add address=1.1.1.1/32 address=2.2.2.2/32 interface=ether1')).toEqual(['schema/duplicate-parameter']);
    expect(rules('/ip address add address=1.1.1.1/32 addr=2.2.2.2/32 interface=ether1')).toEqual(['schema/duplicate-parameter']);
  });

  it('reports more unnamed arguments than the command takes', () => {
    expect(rules(':put "a" "b"')).toEqual(['schema/unexpected-argument']);
    expect(rules('/ip address add 1.1.1.1/32 interface=ether1')).toEqual(['schema/unexpected-argument']);
    expect(rules('/ip address print nope')).toEqual(['schema/unexpected-argument']);
    expect(rules('/ip address set 0 comment=x')).toEqual([]);
    expect(rules('/ip address set 0 1 comment=x')).toEqual(['schema/unexpected-argument']);
  });

  it('reports missing required parameters, counting unnamed values for them', () => {
    expect(rules('/ip address add')).toEqual(['schema/missing-required']);
    expect(messages('/ip address add address=1.1.1.1/32')[0]).toContain('interface');
    expect(rules(':put')).toEqual(['schema/missing-required']);
    expect(rules(':put "x"')).toEqual([]);
    expect(rules('/ip address remove')).toEqual(['schema/missing-required']);
    expect(rules('/ip address remove 0')).toEqual([]);
    expect(rules('/ip address remove numbers=0')).toEqual([]);
    expect(rules('/ip address remove [find]')).toEqual([]);
  });

  it('rejects a flag written with a value and a valued parameter written bare (probes b5, b6, b13, b14)', () => {
    expect(rules('/ip address print detail=yes')).toEqual(['schema/flag-with-value']);
    expect(rules('/ip address add address=1.1.1.1/32 interface=ether1 comment')).toEqual(['schema/parameter-needs-value']);
    expect(rules('/ip address add address=1.1.1.1/32 interface=ether1 comm')).toEqual(['schema/parameter-needs-value']);
  });

  it('takes a bare word that names a parameter as a value where the command has unnamed values (probes b1 to b3)', () => {
    expect(rules(':put message')).toEqual([]);
    expect(rules(':put m')).toEqual([]);
  });

  it('does not look past where', () => {
    expect(rules('/ip address print where address~"1" and nonsense=1')).toEqual([]);
  });

  it('checks the commands inside bodies, substitutions and strings', () => {
    expect(rules(':if (true) do={ /nope x }')).toEqual(['schema/unknown-command']);
    expect(rules(':put [/nope x]')).toEqual(['schema/unknown-command']);
    expect(rules(':put "x $[/nope x]"')).toEqual(['schema/unknown-command']);
  });

  it('can be turned off or made strict', () => {
    expect(analyze('/foo bar', { schema: null }).findings).toEqual([]);
    expect(analyze('/foo bar', { schema, severities: { 'schema/unknown-command': 'error' } }).findings[0]?.severity).toBe('error');
  });
});
