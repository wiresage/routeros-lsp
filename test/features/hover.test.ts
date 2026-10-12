import { describe, expect, it } from 'vitest';
import { hoverAt } from '../../src/features/hover.js';
import { withCaret } from './helpers.js';

function hover(source: string): string | null {
  const { document, analysis, offset } = withCaret(source);
  const result = hoverAt(document, analysis, offset);
  return result ? (result.contents as { value: string }).value : null;
}

describe('hover', () => {
  it('describes a menu with its contents', () => {
    const text = hover('/i|p address print');
    expect(text).toContain('**/ip** menu');
    expect(text).toContain('IP addressing and routing');
    expect(text).toContain('`address`');
  });

  it('describes a command with its required and optional parameters', () => {
    const text = hover('/ip address a|dd address=1.1.1.1/32 interface=ether1');
    expect(text).toContain('**/ip address add** command');
    expect(text).toContain('Create a new item');
    expect(text).toContain('Required: `address`, `interface`');
    expect(text).toContain('Parameters: `comment`, `disabled`');
  });

  it('describes a parameter with its type and values', () => {
    const text = hover('/ip address add dis|abled=yes address=1.1.1.1/32 interface=ether1');
    expect(text).toContain('**disabled** parameter of `/ip address add`');
    expect(text).toContain('Defines whether item is ignored or used');
    expect(text).toContain('Type: `yes | no`');
    expect(text).toContain('Values: `yes`, `no`');
  });

  it('marks a required parameter', () => {
    expect(hover('/ip address add addr|ess=1.1.1.1/32 interface=ether1')).toContain('(required)');
  });

  it('resolves an abbreviated name to the full one', () => {
    expect(hover('/ip addr|ess pr')).toContain('**/ip address**');
    expect(hover('/ip address pr|')).toContain('**/ip address print** command');
  });

  it('describes a variable and where it was declared', () => {
    expect(hover('{\n  :local abc 1\n  :put $a|bc\n}')).toContain('local variable, declared on line 2');
    expect(hover(':put $n|ope')).toContain('not declared in this file');
  });

  it('says nothing about plain text', () => {
    expect(hover(':put "hel|lo"')).toBeNull();
  });
});
