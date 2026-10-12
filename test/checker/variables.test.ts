import { describe, expect, it } from 'vitest';
import { analyze as analyzeWithSchema, type AnalyzeOptions } from '../../src/analyze.js';

/** These tests are about variables only, so the command database is left out. */
const analyze = (text: string, options: AnalyzeOptions = {}) => analyzeWithSchema(text, { schema: null, ...options });

function rules(text: string, options?: AnalyzeOptions): string[] {
  return analyze(text, options).findings.map((f) => f.rule);
}

/** Probe ids refer to research/suites/suite14_declare.py and suite13_scope.py; each was judged by /import dry-run. */
describe(':set needs a declaration in scope', () => {
  it.each([
    ['d1: local on the same line', ':local a; :set a 1'],
    ['d2: global on the same line', ':global a; :set a 1'],
    ['d4: block inside the declaring block', '{ :local a; { :set a 1 } }'],
    ['d6: do= of the declaring block', ':local a; :if (true) do={ :set a 1 }'],
    ['d7: :for variable', ':for i from=1 to=2 do={ :set i 5 }'],
    ['d8: :foreach variable', ':foreach i in={1;2} do={ :set i 5 }'],
    ['d9: :foreach k,v', ':foreach k,v in={1;2} do={ :set v 5 }'],
    ['d12: local inside a function', ':global f do={ :local a; :set a 1 }'],
    ['d14: global redeclared in a function', ':global f do={ :global g; :set g 1 }'],
    ['d16: through $a', ':local a; :set $a 1'],
    ['d17: array element', ':local a {1;2}; :set ($a->0) 5'],
    ['d19: quoted name', ':local "a b"; :set "a b" 1'],
    ['d20: undeclared quoted name', ':set "a b" 1'],
    ['d21: inside a substitution', ':local a; [:set a 1]'],
    ['d23: :onerror variable', ':onerror e in={ } do={ :set e 1 }'],
    ['d25: outer local inside :do', ':local a; :do { :set a 1 } on-error={ }'],
    ['d26: with no value', ':local a; :set a'],
    ['d29: global then local', ':global a; :local a; :set a 1'],
    ['d36: outer local inside :while', ':local t; :while (false) do={ :set t 1 }'],
    ['d37: outer loop variable', ':for i from=1 to=2 do={ :for j from=1 to=2 do={ :set i 1 } }'],
    ['a backslash join keeps one line', ':local a; \\\n:set a 1'],
    ['a block that spans lines is one scope', ':local a; {\n  :set a 1\n}'],
  ])('accepts %s', (_name, text) => {
    expect(rules(text)).toEqual([]);
  });

  it.each([
    ['v5: never declared', ':set nope "x"'],
    ['d3: declared after', ':set a 1; :local a'],
    ['d5: inner block ended', '{ { :local a }; :set a 1 }'],
    ['d10: function argument', ':global f do={ :set a 5 }'],
    ['d11: positional argument', ':global f do={ :set 1 5 }'],
    ['d13: global of the code around a function', ':global g; :global f do={ :set g 1 }'],
    ['d15: local of the code around a function', ':local a; :global f do={ :set a 1 }'],
    ['d30: lease variable', ':set leaseBound 1'],
    ['d32: inside a declaration value', ':local a [:set b 1]'],
    ['d34: local of an outer function', ':global f do={ :local x; :local g do={ :set x 1 } }'],
    ['d38: inside :retry', ':retry command={ :set q 1 } delay=1 max=1'],
    ['h25: global from an earlier line', ':global g 1\n:set g 2'],
    ['h26: global declared empty on an earlier line', ':global g\n:set g 2'],
    ['case matters', ':local "A"; :set a 1'],
  ])('rejects %s', (_name, text) => {
    expect(rules(text)).toContain('vars/set-undeclared');
  });

  it('does not check the base of an array element, which is only read (probe d18)', () => {
    expect(rules(':set ($nope->0) 5')).toEqual(['vars/undeclared-read']);
  });

  it('explains the line and function rules in the message', () => {
    const [line] = analyze(':global g 1\n:set g 2').findings;
    expect(line?.message).toContain('each line of an imported file is its own scope');
    const [fn] = analyze(':local a; :global f do={ :set a 1 }').findings;
    expect(fn?.message).toContain('A function cannot set variables of the code around it');
  });

  it('lets the whole file share one scope in script mode', () => {
    expect(rules(':global g 1\n:set g 2', { scope: 'script' })).toEqual([]);
    expect(rules(':local a\n:global f do={ :set a 1 }', { scope: 'script' })).toContain('vars/set-undeclared');
  });
});

describe('reading a variable', () => {
  it('stays quiet about declared variables', () => {
    expect(rules(':local a 1; :put $a')).toEqual([]);
    expect(rules('{\n:local a 1\n:put $a\n:put "v=$a"\n:put ($a + 1)\n}')).toEqual([]);
    expect(rules(':foreach i in={1;2} do={ :put $i }')).toEqual([]);
    expect(rules(':global g 1\n:put $g')).toEqual([]);
  });

  it('warns once, at the first read, about a variable that is never declared', () => {
    const { findings } = analyze(':put $nope\n:put $nope\n:put "x $nope"');
    expect(findings).toHaveLength(1);
    expect(findings[0]).toMatchObject({ rule: 'vars/undeclared-read', severity: 'warning', start: 5, end: 10 });
    expect(findings[0]?.message).toContain('2 more times');
  });

  it('warns about a local read on a later line of an imported file (probe q1)', () => {
    const { findings } = analyze(':local a 1\n:put $a\n:put $a');
    expect(findings.map((f) => f.rule)).toEqual(['vars/local-out-of-scope']);
    expect(findings[0]?.message).toContain('1 more time');
  });

  it('does not warn when the local is in the same block or a block around it', () => {
    expect(rules('{\n  :local a 1\n  :if (true) do={ :put $a }\n}')).toEqual([]);
  });

  it('treats a global as readable from anywhere in the file (probes q2 and q3)', () => {
    expect(rules(':global g 5\n:global f do={ :put $g }')).toEqual([]);
    expect(rules(':global g 5\n:put $g')).toEqual([]);
  });

  it('does not check reads inside a function, where a name may be an argument (probes q5, q7, q8)', () => {
    expect(rules(':global f do={ :put $a; :put $1; :put $anything }')).toEqual([]);
  });

  it('exempts positional names and the configured context variables', () => {
    expect(rules(':put $1')).toEqual([]);
    expect(rules(':if ($leaseBound = 1) do={ :put $leaseActIP }')).toEqual([]);
    expect(rules(':put $custom', { contextVariables: ['custom'] })).toEqual([]);
    expect(rules(':put $custom')).toEqual(['vars/undeclared-read']);
  });

  it('shares one scope in script mode', () => {
    expect(rules(':local a 1\n:put $a', { scope: 'script' })).toEqual([]);
  });

  it('sees a variable named with quotes', () => {
    expect(rules('{ :local "my var" 1; :put $"my var" }')).toEqual([]);
    expect(rules(':put $"my var"')).toEqual(['vars/undeclared-read']);
  });

  it('declares a name only after its own value is read', () => {
    expect(rules(':local a $a')).toEqual(['vars/undeclared-read']);
  });
});

describe('variable names', () => {
  it.each([
    [':local a_b', 8],
    [':local a-b', 8],
    [':local a.b', 8],
    [':global a:b', 9],
    [':foreach a_b in={1} do={ }', 10],
    [':foreach a,b_c in={1} do={ }', 12],
    [':for a-b from=1 to=2 do={ }', 6],
    [':local a,b', 8],
  ])('rejects %j at offset %i', (text, offset) => {
    const finding = analyze(text).findings.find((f) => f.rule === 'vars/invalid-name');
    expect(finding?.start).toBe(offset);
  });

  it('rejects a $ where a name is declared', () => {
    expect(rules(':local $a')).toContain('vars/invalid-name');
  });

  it.each([':local "a_b"', ':local 1a', ':local A1', ':foreach a,b in={1} do={ }', ':set "a-b" 1'])('accepts %j', (text) => {
    expect(rules(text)).not.toContain('vars/invalid-name');
  });

  it('warns about keywords as names, because the documentation reserves them', () => {
    const { findings } = analyze(':local and 1; :local or 2; :local in 3');
    expect(findings.filter((f) => f.rule === 'vars/keyword-name')).toHaveLength(3);
    expect(findings[0]?.severity).toBe('warning');
  });
});

describe('severity overrides', () => {
  it('can turn a rule off or change its level', () => {
    expect(rules(':put $nope', { severities: { 'vars/undeclared-read': 'off' } })).toEqual([]);
    expect(analyze(':put $nope', { severities: { 'vars/undeclared-read': 'error' } }).findings[0]?.severity).toBe('error');
  });
});
