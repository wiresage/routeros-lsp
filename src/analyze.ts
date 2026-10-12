import { bind, type BindResult } from './binder/binder.js';
import { checkCommands, type CommandAnalysis } from './checker/commands.js';
import { checkVariables, type RuleFinding } from './checker/variables.js';
import { DEFAULT_CONTEXT_VARIABLES, type ScopeMode } from './config.js';
import { RULES, type RuleId, type Severity } from './rules.js';
import { Schema } from './schema/schema.js';
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
  /** The command database. Defaults to the one that ships with the package; null turns the command checks off. */
  readonly schema?: Schema | null;
}

let bundled: Schema | null | undefined;

/** The command database that ships with the package, loaded once. */
export function bundledSchema(): Schema | null {
  if (bundled === undefined) {
    try {
      bundled = Schema.bundled();
    } catch {
      bundled = null;
    }
  }
  return bundled;
}

export interface Analysis {
  readonly script: Script;
  readonly bound: BindResult;
  /** What the words of the command lines resolved to; null when no command database is in use. */
  readonly commands: CommandAnalysis | null;
  readonly findings: Finding[];
}

export function analyze(text: string, options: AnalyzeOptions = {}): Analysis {
  const { script, diagnostics } = parse(text);
  const bound = bind(script, text, {
    mode: options.scope ?? 'import',
    contextVariables: new Set(options.contextVariables ?? DEFAULT_CONTEXT_VARIABLES),
  });
  const schema = options.schema === undefined ? bundledSchema() : options.schema;
  const commands = schema ? checkCommands(script, schema) : null;
  const all: RuleFinding[] = [...diagnostics, ...checkVariables(bound), ...(commands ? commands.findings : [])];
  // The hint about a "#" is redundant where the argument count already rejects the same word, and says it better.
  const rejected = new Set(all.filter((f) => f.rule === 'schema/unexpected-argument').map((f) => f.start));
  const raw = all.filter((f) => !(f.rule === 'syntax/trailing-comment' && rejected.has(f.start)));

  const findings: Finding[] = [];
  for (const d of raw) {
    const severity = options.severities?.[d.rule] ?? RULES[d.rule].severity;
    if (severity !== 'off') findings.push({ ...d, severity });
  }
  findings.sort((a, b) => a.start - b.start || a.end - b.end);
  return { script, bound, commands, findings };
}
