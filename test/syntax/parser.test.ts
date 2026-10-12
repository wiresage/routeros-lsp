import { describe, expect, it } from 'vitest';
import type { Binary, Brace, Element, Expr, Group, Named, Statement, StringLit } from '../../src/syntax/ast.js';
import { parse } from '../../src/syntax/parser.js';

function statements(text: string): Statement[] {
  return parse(text).script.statements;
}

function first(text: string): Statement {
  const s = statements(text)[0];
  if (!s) throw new Error(`no statement in ${JSON.stringify(text)}`);
  return s;
}

function rules(text: string): string[] {
  return parse(text).diagnostics.map((d) => d.rule);
}

function group(text: string): Group {
  const el = first(text).elements.find((e): e is Group => e.kind === 'group');
  if (!el) throw new Error('no group');
  return el;
}

/** Renders an expression with explicit grouping, to compare precedence. */
function show(e: Expr): string {
  switch (e.kind) {
    case 'binary':
      return `(${show(e.left)} ${e.op} ${show(e.right)})`;
    case 'unary':
      return `${e.op}${show(e.operand)}`;
    case 'word':
      return e.text;
    case 'variable':
      return `$${e.name}`;
    case 'string':
      return JSON.stringify(e.value);
    case 'missing':
      return '?';
    default:
      return e.kind;
  }
}

describe('statements and elements', () => {
  it('splits prefix, path words and arguments', () => {
    const s = first('/ip address add address=10.0.0.1/24 interface=ether1');
    expect(s.prefix).toBe('/');
    expect(s.elements.map((e) => e.kind)).toEqual(['word', 'word', 'word', 'named', 'named']);
    const named = s.elements[3] as Named;
    expect(named.name).toMatchObject({ kind: 'word', text: 'address' });
    expect(named.value).toMatchObject({ kind: 'word', text: '10.0.0.1/24' });
  });

  it('reads the global command prefix with or without a space', () => {
    expect(first(':put 1').prefix).toBe(':');
    expect(first(': put 1').elements[0]).toMatchObject({ text: 'put' });
    expect(first('put 1').prefix).toBeNull();
  });

  it('separates statements on newlines, semicolons and all three line endings', () => {
    expect(statements(':put 1;:put 2\n:put 3\r\n:put 4\r:put 5')).toHaveLength(5);
  });

  it('keeps the menu path across lines as separate statements', () => {
    const list = statements('/ip address\nadd address=1.1.1.1/32\nprint');
    expect(list.map((s) => s.prefix)).toEqual(['/', null, null]);
  });

  it('allows an omitted value and a space after the equals sign', () => {
    const [a, b] = statements('/system identity set name=\n/ip address add comment= x');
    expect((a!.elements[3] as Named).value).toBeNull();
    expect(((b!.elements[3] as Named).value as Element).kind).toBe('word');
  });

  it('joins lines that end in a backslash, with CR LF as well', () => {
    expect(statements(':put \\\n  1')).toHaveLength(1);
    expect(statements(':put \\\r\n  1')).toHaveLength(1);
    expect(statements(':put \\ \n  1')).toHaveLength(1);
  });

  it('treats # only as a comment at the start of a command', () => {
    expect(statements('# one\n:put 1; # two\n{ # three\n}')).toHaveLength(2);
    expect(rules(':put a#b')).toEqual([]);
    expect(rules(':put 1 # comment')).toEqual(['syntax/trailing-comment']);
  });

  it('parses an empty file and a file of only comments', () => {
    expect(statements('')).toEqual([]);
    expect(statements('# only a comment')).toEqual([]);
  });
});

describe('strings', () => {
  const str = (text: string): StringLit => first(`:put ${text}`).elements[1] as StringLit;

  it('decodes escapes', () => {
    expect(str('"a\\tb\\n\\"\\\\\\$\\_\\41"').value).toBe('a\tb\n"\\$ A');
  });

  it('records interpolation parts', () => {
    const s = str('"x $name $(1+2) $[:len "a"]"');
    expect(s.parts.map((p) => p.kind)).toEqual(['text', 'variable', 'text', 'expression', 'text', 'command']);
    expect(s.value).toBe('x   ');
  });

  it('removes a backslash line join and the next line indentation', () => {
    expect(str('"a\\\n    b"').value).toBe('ab');
  });

  it('accepts a raw line break and non-ASCII text inside a string', () => {
    expect(rules(':put "one\ntwo é"')).toEqual([]);
  });

  it('reports an unterminated string at its opening quote', () => {
    const d = parse(':put "abc').diagnostics;
    expect(d).toMatchObject([{ rule: 'syntax/unterminated-string', start: 5, end: 6 }]);
  });

  it.each([
    ['\\q', 'syntax/invalid-escape'],
    ['\\4f', 'syntax/invalid-escape'],
    ['\\4', 'syntax/invalid-escape'],
    ['$ ', 'syntax/bad-interpolation'],
    ['$-', 'syntax/bad-interpolation'],
  ])('rejects %s inside a string', (inside, rule) => {
    expect(rules(`:put "a${inside}b"`)).toContain(rule);
  });

  it('accepts every documented escape', () => {
    expect(rules(':put "\\" \\\\ \\n \\r \\t \\$ \\_ \\a \\b \\f \\v \\? \\0A \\FF"')).toEqual([]);
  });
});

describe('variables', () => {
  it('reads plain and quoted names', () => {
    const els = first(':put $a $"b c" $1').elements;
    expect(els[1]).toMatchObject({ kind: 'variable', name: 'a', quoted: false });
    expect(els[2]).toMatchObject({ kind: 'variable', name: 'b c', quoted: true });
    expect(els[3]).toMatchObject({ kind: 'variable', name: '1' });
  });

  it('ends a name at the first character that is not a letter or digit', () => {
    expect(rules(':put $a_b')).toEqual(['syntax/adjacent-tokens']);
    expect(rules(':put $a-b')).toEqual(['syntax/adjacent-tokens']);
  });

  it('rejects a bare dollar and $( outside a string', () => {
    expect(rules(':put $')).toEqual(['syntax/bare-dollar']);
    expect(rules(':put $(1+2)')).toEqual(['syntax/dollar-expression-outside-string']);
    expect(rules(':put $[:len "a"]')).toEqual(['syntax/dollar-expression-outside-string']);
  });
});

describe('expressions', () => {
  it('uses the observed precedence', () => {
    expect(show(group(':put (1 + 2 * 3)').exprs[0]!)).toBe('(1 + (2 * 3))');
    expect(show(group(':put (1 - 2 - 3)').exprs[0]!)).toBe('((1 - 2) - 3)');
    expect(show(group(':put (a = 1 && b = 2 || c)').exprs[0]!)).toBe('(((a = 1) && (b = 2)) || c)');
    expect(show(group(':put ("a" . "b" = "ab")').exprs[0]!)).toBe('(("a" . "b") = "ab")');
    expect(show(group(':put (!$a && $b)').exprs[0]!)).toBe('(!$a && $b)');
  });

  it('reads word operators and -> ', () => {
    const e = group(':put ($a and $b or $c->0)').exprs[0] as Binary;
    expect(e.op).toBe('or');
    expect(show(e)).toBe('(($a and $b) or ($c -> 0))');
  });

  it('keeps addresses, prefixes and times as single words', () => {
    expect(show(group(':put (10.0.0.0/8)').exprs[0]!)).toBe('10.0.0.0/8');
    expect(show(group(':put (1d2h3m)').exprs[0]!)).toBe('1d2h3m');
    expect(show(group(':put (00:10:00)').exprs[0]!)).toBe('00:10:00');
    expect(show(group(':put (::1)').exprs[0]!)).toBe('::1');
  });

  it('accepts operands next to each other', () => {
    expect(group(':put ($a $b)').exprs).toHaveLength(2);
    expect(rules(':put ($aand$b)')).toEqual([]);
  });

  it.each([
    [':put ()', 'syntax/empty-expression'],
    [':put (5 -)', 'syntax/expected-operand'],
    [':put (1 + + 2)', 'syntax/expected-operand'],
    [':put (* 2)', 'syntax/expected-operand'],
    [':put (1 == 2)', 'syntax/expected-operand'],
    [':put (1 ; 2)', 'syntax/unexpected-token'],
    [':put (1\n+ 2)', 'syntax/newline-in-parens'],
  ])('rejects %j', (text, rule) => {
    expect(rules(text)).toContain(rule);
  });

  it('accepts a backslash join inside parentheses', () => {
    expect(rules(':put (1 \\\n + 2)')).toEqual([]);
  });
});

describe('brackets and recovery', () => {
  it('reports a missing closer at the opener and keeps parsing', () => {
    const r = parse('{\n:put 1\n:put 2\n');
    expect(r.diagnostics).toMatchObject([{ rule: 'syntax/missing-closer', start: 0, end: 1 }]);
    const brace = r.script.statements[0]!.elements[0] as Brace;
    expect(brace.body).toHaveLength(2);
    expect(brace.closed).toBe(false);
  });

  it('closes an inner construct at the closer of an outer one', () => {
    const r = parse('{ :put [:len "a" }\n:put 2');
    expect(r.diagnostics.map((d) => d.rule)).toEqual(['syntax/missing-closer']);
    expect(r.script.statements).toHaveLength(2);
  });

  it('tolerates a stray } or ] with a warning and rejects a stray )', () => {
    expect(rules('}')).toEqual(['syntax/stray-closer']);
    expect(rules(':put 1 ]')).toEqual(['syntax/stray-closer']);
    expect(rules(')')).toEqual(['syntax/unexpected-closer']);
  });

  it('marks a brace on its own line as a block and a brace argument as unknown', () => {
    const block = first('{ :put 1 }').elements[0] as Brace;
    const arg = first(':local a {1;2}').elements[2] as Brace;
    expect(block.role).toBe('block');
    expect(arg.role).toBe('unknown');
    expect((first(':if (true) do={ }').elements[2] as Named).value).toMatchObject({ role: 'block' });
  });

  it('parses pairs in an array and rejects them in a block', () => {
    expect(rules(':local a {a=1; "b c"=2; d={e=3}}')).toEqual([]);
    expect(rules('{ a=1 }')).toEqual(['syntax/statement-starts-with-pair']);
    expect(rules(':if (true) do={ :put 1 }\nelse={ :put 2 }')).toEqual(['syntax/statement-starts-with-pair']);
  });

  it('stays bounded on deeply nested input', () => {
    const text = '('.repeat(5000);
    const r = parse(text);
    expect(r.diagnostics.some((d) => d.rule === 'syntax/too-deeply-nested')).toBe(true);
  });
});

describe('layout rules', () => {
  it.each([
    [':put 1 :put 2', 'syntax/missing-separator'],
    [':if (true) do={ :put 1 } :put 2', 'syntax/missing-separator'],
    ['/ip address add gateway = 3.3.3.3', 'syntax/space-before-equals'],
    ['/ip address add gateway =3.3.3.3', 'syntax/space-before-equals'],
    ['/system identity set name=a=b', 'syntax/unexpected-equals'],
    [':log info a"b"', 'syntax/adjacent-tokens'],
    [':log info "a"b', 'syntax/adjacent-tokens'],
    [':log info (1)(2)', 'syntax/adjacent-tokens'],
    [':log info [:len x][:len y]', 'syntax/adjacent-tokens'],
    [':if (true)do={ }', 'syntax/adjacent-tokens'],
    [':if (true) do={ }else={ }', 'syntax/adjacent-tokens'],
    [':put a?b', 'syntax/invalid-character'],
    [":put 'a'", 'syntax/invalid-character'],
    [':put é', 'syntax/invalid-character'],
    ['﻿:put 1', 'syntax/bom'],
    ['"abc"', 'syntax/expected-command'],
    [':PUT 1', 'syntax/expected-command'],
    ['::', 'syntax/expected-command'],
  ])('flags %j', (text, rule) => {
    expect(rules(text)).toContain(rule);
  });

  it.each([
    ':put a-b',
    ':put a~b',
    ':put a=b',
    '/ip address print where address~"1"',
    '/ip address print where disabled = no',
    '/ip address print where address = 1.1.1.1/32',
    '/ip address print where !disabled && dynamic',
    ':',
    '/',
    ':put 1;',
    '{;}',
    '[;]',
    '/ip { address print }',
    '/ip address .. route print',
    '$f 1 2',
    ':local a ({})',
  ])('accepts %j', (text) => {
    expect(rules(text)).toEqual([]);
  });

  it('warns about a backslash that does not end the line, without an error', () => {
    const d = parse(':put \\ 1').diagnostics;
    expect(d.map((x) => x.rule)).toEqual(['syntax/stray-backslash']);
  });
});
