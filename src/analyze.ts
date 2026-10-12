import { RULES, type RuleId, type Severity } from './rules.js';
import type { Script } from './syntax/ast.js';
import { parse } from './syntax/parser.js';

export interface Finding {
  readonly rule: RuleId;
  readonly message: string;
  readonly start: number;
  readonly end: number;
  readonly severity: Exclude<Severity, 'off'>;
}

export interface AnalyzeOptions {
  /** Overrides the default severity of a rule; 'off' drops it. */
  readonly severities?: Partial<Record<RuleId, Severity>>;
}

export interface Analysis {
  readonly script: Script;
  readonly findings: Finding[];
}

export function analyze(text: string, options: AnalyzeOptions = {}): Analysis {
  const { script, diagnostics } = parse(text);
  const findings: Finding[] = [];
  for (const d of diagnostics) {
    const severity = options.severities?.[d.rule] ?? RULES[d.rule].severity;
    if (severity !== 'off') findings.push({ ...d, severity });
  }
  return { script, findings };
}
