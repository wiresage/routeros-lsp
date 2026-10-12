import { RULES, type RuleId, type Severity } from './rules.js';

export type ScopeMode = 'import' | 'script';

export interface Settings {
  /** Overrides the default severity of individual rules. 'off' disables a rule. */
  readonly severities: Partial<Record<RuleId, Severity>>;
  /**
   * How the file is run. 'import' (the default) treats every top-level command as a scope of its own, which is what
   * /import does and what pasting into the terminal does. 'script' treats the whole file as one scope, as in the
   * source of a /system script.
   */
  readonly scope: ScopeMode;
  /** Variables that the environment provides and that are therefore never reported as undeclared. */
  readonly contextVariables: readonly string[];
}

/** Variables a DHCP server sets for a lease script (docs/ambiguities.md V-14; the documentation does not list them). */
export const DEFAULT_CONTEXT_VARIABLES = ['leaseBound', 'leaseServerName', 'leaseActMAC', 'leaseActIP'] as const;

export const DEFAULT_SETTINGS: Settings = { severities: {}, scope: 'import', contextVariables: DEFAULT_CONTEXT_VARIABLES };

const SEVERITIES: readonly string[] = ['error', 'warning', 'information', 'hint', 'off'];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/**
 * Reads settings from `initializationOptions` or a `workspace/didChangeConfiguration` payload. Both the bare object and
 * one nested under a "routeros" key are accepted. Anything unrecognised is reported through `warn` and ignored.
 */
export function parseSettings(raw: unknown, warn: (message: string) => void = () => undefined): Settings {
  const root = isRecord(raw) && isRecord(raw['routeros']) ? raw['routeros'] : raw;
  if (!isRecord(root)) return DEFAULT_SETTINGS;

  const severities: Partial<Record<RuleId, Severity>> = {};
  const given = root['severities'];
  if (given !== undefined && !isRecord(given)) warn('"severities" must be an object of rule id to severity; ignoring it');
  if (isRecord(given)) {
    for (const [rule, value] of Object.entries(given)) {
      if (!(rule in RULES)) warn(`unknown rule "${rule}" in "severities"`);
      else if (typeof value !== 'string' || !SEVERITIES.includes(value)) warn(`"${rule}": expected one of ${SEVERITIES.join(', ')}`);
      else severities[rule as RuleId] = value as Severity;
    }
  }

  let scope: ScopeMode = 'import';
  if (root['scope'] !== undefined) {
    if (root['scope'] === 'import' || root['scope'] === 'script') scope = root['scope'];
    else warn('"scope" must be "import" or "script"');
  }

  let contextVariables: readonly string[] = DEFAULT_CONTEXT_VARIABLES;
  const extra = root['contextVariables'];
  if (extra !== undefined) {
    if (Array.isArray(extra) && extra.every((v) => typeof v === 'string')) contextVariables = [...DEFAULT_CONTEXT_VARIABLES, ...(extra as string[])];
    else warn('"contextVariables" must be an array of variable names');
  }
  return { severities, scope, contextVariables };
}
