import { describe, expect, it } from 'vitest';
import { analyze, type AnalyzeOptions } from '../../src/analyze.js';
import cases from './cases.json' with { type: 'json' };
import gaps from './known-gaps.json' with { type: 'json' };

interface Case {
  id: string;
  section: string;
  note: string;
  source: string;
  valid: boolean;
  message?: string;
  line?: number;
  column?: number;
}

const known = gaps as Record<string, string>;

// The recorded answers come from the device itself, where an unknown name is an error. The server reports those as warnings
// because its command database comes from a CHR (docs/configuration.md), so here they count as errors.
const AS_THE_DEVICE: AnalyzeOptions = {
  severities: { 'schema/unknown-command': 'error', 'schema/unknown-parameter': 'error' },
};

function agrees(c: Case): boolean {
  const failed = analyze(c.source, AS_THE_DEVICE).findings.some((f) => f.severity === 'error');
  return failed === !c.valid;
}

describe('conformance with RouterOS 7.21.4 (/import dry-run verdicts)', () => {
  for (const c of cases as Case[]) {
    const gap = known[c.id];
    const label = `${c.id} ${c.valid ? 'accepts' : 'rejects'} ${JSON.stringify(c.source).slice(0, 70)}`;
    if (gap === undefined) {
      it(label, () => {
        expect(agrees(c), `${c.note}; the router said: ${c.valid ? 'OK' : c.message}`).toBe(true);
      });
    } else {
      // A known gap must still be a gap: when the implementation catches up, the entry has to be removed.
      it(`${label} (known gap: ${gap})`, () => {
        expect(agrees(c), `${c.id} now agrees with the router; remove it from known-gaps.json`).toBe(false);
      });
    }
  }
});
