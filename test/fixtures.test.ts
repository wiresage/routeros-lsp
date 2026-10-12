import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { analyze } from '../src/analyze.js';
import verdicts from './fixtures/verdicts.json' with { type: 'json' };

const root = join(import.meta.dirname, 'fixtures');
const folders = ['scripts', 'crlf', 'cr'];

// verdicts.json holds what `/import file dry-run` said about each file (research/tools/check_files.py).
// A file RouterOS accepts must produce no finding at all: a false positive on valid input is the worst failure.
describe('files that RouterOS accepts', () => {
  for (const folder of folders) {
    for (const name of readdirSync(join(root, folder)).filter((f) => f.endsWith('.rsc'))) {
      it(`${folder}/${name} has no findings`, () => {
        const verdict = (verdicts as Record<string, { valid: boolean; errors: string[] }>)[name];
        expect(verdict, `no recorded verdict for ${name}; run research/tools/check_files.py`).toBeDefined();
        expect(verdict?.valid, `RouterOS rejects ${name}: ${verdict?.errors.join('; ')}`).toBe(true);

        const text = readFileSync(join(root, folder, name), 'utf8');
        const { findings } = analyze(text);
        expect(findings.map((f) => `${f.rule} at ${f.start}: ${f.message}`)).toEqual([]);
      });
    }
  }
});
