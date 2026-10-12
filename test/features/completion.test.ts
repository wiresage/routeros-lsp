import { describe, expect, it } from 'vitest';
import { completions } from '../../src/features/completion.js';
import { miniSchema, withCaret } from './helpers.js';

function items(source: string) {
  const { document, analysis, position } = withCaret(source);
  return completions(document, analysis, miniSchema, position);
}

function labels(source: string): string[] {
  return items(source).map((i) => i.label);
}

describe('menus and commands', () => {
  it('offers the top level in an empty file and after a colon', () => {
    expect(labels('|')).toEqual(expect.arrayContaining(['ip', 'system', 'put', 'local']));
    // a colon reaches menus as well as global commands: ":log info" is a command of the menu log
    expect(labels(':|')).toEqual(expect.arrayContaining(['if', 'local', 'put', 'ip', 'system']));
  });

  it('offers the children of the menu written so far', () => {
    expect(labels('/ip |').sort()).toEqual(['accounting', 'address', 'firewall', 'route']);
    expect(labels('/ip address |').sort()).toEqual(['add', 'find', 'print', 'remove', 'set']);
    expect(labels('ip address |')).toContain('add');
  });

  it('replaces the word being typed', () => {
    const [first] = items('/ip ad|');
    expect(first).toMatchObject({ label: 'address', textEdit: { range: { start: { line: 0, character: 4 }, end: { line: 0, character: 6 } }, newText: 'address' } });
  });

  it('continues a path set on an earlier line', () => {
    expect(labels('/ip address\n|')).toContain('print');
    expect(labels('/ip address\n:if (true) do={ | }')).toContain('print');
    expect(labels('/ip address print\n|')).not.toContain('print');
  });

  it('starts again from the top level after a colon inside a menu', () => {
    expect(labels('/ip address\n:|')).toEqual(expect.arrayContaining(['if', 'local', 'put', 'ip']));
    expect(labels('/ip address\n:|')).not.toContain('print');
  });

  it('describes each item', () => {
    const address = items('/ip |').find((i) => i.label === 'address');
    expect(address?.detail).toBe('IP address settings');
    expect(items('/ip address |').find((i) => i.label === 'add')?.kind).toBe(3);
  });
});

describe('parameters and values', () => {
  it('offers the parameters of a command, required ones first', () => {
    const list = items('/ip address add |');
    expect(list.map((i) => i.label)).toEqual(['address', 'interface', 'comment', 'disabled']);
    expect(list[0]).toMatchObject({ detail: 'required, A.B.C.D (IP address)', textEdit: { newText: 'address=' } });
    expect(list[0]!.sortText! < list[2]!.sortText!).toBe(true);
  });

  it('leaves out the parameters that are already given', () => {
    expect(labels('/ip address add address=1.1.1.1/32 |')).toEqual(['interface', 'comment', 'disabled']);
  });

  it('completes the part of a parameter name that is typed', () => {
    // every parameter is offered; the editor narrows the list by what is typed, and the edit replaces that text
    const interfaceItem = items('/ip address add inter|').find((i) => i.label === 'interface');
    expect(interfaceItem).toMatchObject({ textEdit: { range: { start: { character: 16 }, end: { character: 21 } }, newText: 'interface=' } });
  });

  it('offers the known values after the equals sign', () => {
    expect(labels('/ip address add disabled=|')).toEqual(['yes', 'no']);
    expect(labels('/ip address add disabled=y|')).toEqual(['yes', 'no']);
    expect(labels('/ip address add comment=|')).toEqual([]);
  });

  it('writes a flag without an equals sign', () => {
    const detail = items('/ip address print |').find((i) => i.label === 'detail');
    expect(detail?.textEdit).toMatchObject({ newText: 'detail' });
  });

  it('offers nothing in a where expression', () => {
    expect(labels('/ip address print where |')).toEqual([]);
  });
});

describe('variables', () => {
  it('offers the variables in scope after a dollar sign', () => {
    expect(labels('{ :local abc 1; :local abd 2; :put $| }')).toEqual(['abc', 'abd']);
    expect(labels('{ :local abc 1; :put $a| }')).toEqual(['abc']);
  });

  it('offers a global declared earlier but not a local of a block that ended', () => {
    expect(labels(':global g 1\n{ :local inner 1 }\n:put $|')).toEqual(['g']);
  });

  it('does not offer the locals of the code around a function', () => {
    expect(labels('{ :local outer 1; :global f do={ :local own 2; :put $| } }')).toEqual(['own']);
  });

  it('works inside a string', () => {
    expect(labels('{ :local abc 1; :put "x $a|" }')).toEqual(['abc']);
  });
});

describe('where nothing is offered', () => {
  it('stays quiet in comments and strings', () => {
    expect(labels('# /ip |')).toEqual([]);
    expect(labels(':put "/ip |"')).toEqual([]);
  });

  it('stays quiet when the path is unknown', () => {
    expect(labels('/nonsense\n|')).toEqual([]);
  });

  it('returns nothing without a command database', () => {
    const { document, analysis, position } = withCaret('/ip |');
    expect(completions(document, analysis, null, position)).toEqual([]);
  });
});
