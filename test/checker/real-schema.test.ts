import { describe, expect, it } from 'vitest';
import { analyze } from '../../src/analyze.js';

// These run against the bundled RouterOS 7.21.4 database and guard against false positives that the differential run
// (research/tools/differential.py, 16,900 generated command lines judged by a router) and the probe suites turned up.
function findings(text: string): string[] {
  return analyze(text).findings.map((f) => `${f.rule}: ${f.message}`);
}

describe('valid input produces no findings against the bundled database', () => {
  it.each([
    // arrays and blocks in argument position are not command lists (probes f5, a4, z7)
    ':foreach i in={1;2} do={ :put $i }',
    ':foreach k,v in={1;2} do={ :put $k }',
    ':put {1;2;3}',
    ':local a {1;2;3}; :put ($a->1)',
    // a word that only starts a parameter name is a value for a command that takes values
    ':foreach i in=[:toarray "1,2"] do={ :put $i }',
    // a colon can lead into a menu (probe p23)
    ':log info "x"',
    ':ip address print',
    // find takes property conditions without where (probes w1 to w6, r19)
    '/ip address remove [find address=1.1.1.1/32]',
    '/interface ethernet set [find default-name=ether1] disable-running-check=no',
    // loop-only commands inside a loop (probe p20)
    ':foreach i in={1} do={ :break }',
    ':while (true) do={ :continue }',
    // commands that take free-form parameters
    ':do command=0 command=0',
    ':onerror e in={ } do={ }',
    ':retry command={ :put 1 } delay=1 max=1',
    '/ip recursive-print zzz=0',
    // statement-level substitution and colon lines keep the path rules (probes l9, suite 20)
    '[/ip route]\nadd dst-address=0.0.0.0/0 gateway=1.1.1.1',
    ':if (true) do={ /ip route; add dst-address=0.0.0.0/0 gateway=1.1.1.1 }',
    // :local name=x names the parameter
    ':local name=abc; :put $abc',
  ])('%j', (text) => {
    expect(findings(text)).toEqual([]);
  });

  it('still reports the mistakes next to them', () => {
    expect(findings(':break').join('\n')).toContain("'break'");
    expect(findings(':local a=1').join('\n')).toContain('Declare a variable as');
    expect(findings('[/ip route]\nprint\nadd address=1.1.1.1/32 interface=ether1').join('\n')).toContain("'address'");
    expect(findings(':put 1 # c').join('\n')).toContain('Put');
  });
});
