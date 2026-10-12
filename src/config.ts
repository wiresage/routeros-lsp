import { RULES, type RuleId, type Severity } from './rules.js';

export interface Settings {
  /** Overrides the default severity of individual rules. 'off' disables a rule. */
  readonly severities: Partial<Record<RuleId, Severity>>;
}

export const DEFAULT_SETTINGS: Settings = { severities: {} };

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
  return { severities };
}
