import { bind, type BindResult } from './binder/binder.js';
import { checkVariables, type RuleFinding } from './checker/variables.js';
import { DEFAULT_CONTEXT_VARIABLES, type ScopeMode } from './config.js';
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
  /** See Settings.scope. Defaults to 'import'. */
  readonly scope?: ScopeMode;
  /** Variables the environment provides. Defaults to the DHCP lease script variables. */
  readonly contextVariables?: readonly string[];
}

export interface Analysis {
  readonly script: Script;
  readonly bound: BindResult;
  readonly findings: Finding[];
}

export function analyze(text: string, options: AnalyzeOptions = {}): Analysis {
  const { script, diagnostics } = parse(text);
  const bound = bind(script, text, {
    mode: options.scope ?? 'import',
    contextVariables: new Set(options.contextVariables ?? DEFAULT_CONTEXT_VARIABLES),
  });
  const raw: RuleFinding[] = [...diagnostics, ...checkVariables(bound)];

  const findings: Finding[] = [];
  for (const d of raw) {
    const severity = options.severities?.[d.rule] ?? RULES[d.rule].severity;
    if (severity !== 'off') findings.push({ ...d, severity });
  }
  findings.sort((a, b) => a.start - b.start || a.end - b.end);
  return { script, bound, findings };
}
