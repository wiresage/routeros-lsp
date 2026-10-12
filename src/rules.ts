/**
 * Every diagnostic the server can produce is a rule with a stable id, a default severity and a source.
 *
 * Sources say how well the rule is founded, so a message never presents a router quirk as the language specification:
 *   doc          the Scripting documentation states it
 *   doc-example  not stated, but shown by a documentation example
 *   device       observed on a router, not documented (see docs/ambiguities.md)
 *   open         the documentation is silent or contradictory
 */
export type RuleSource = 'doc' | 'doc-example' | 'device' | 'open';
export type Severity = 'error' | 'warning' | 'information' | 'hint' | 'off';

export interface RuleInfo {
  readonly source: RuleSource;
  readonly severity: Severity;
  /** One line for documentation and configuration listings. */
  readonly summary: string;
  /** Row ids in docs/ambiguities.md, when the rule rests on one. */
  readonly ambiguity?: readonly string[];
}

export const RULES = {
  'syntax/bom': {
    source: 'device',
    severity: 'error',
    summary: 'A byte order mark at the start of the file is rejected by RouterOS.',
    ambiguity: ['L-06'],
  },
  'syntax/unterminated-string': {
    source: 'doc',
    severity: 'error',
    summary: 'A string literal is not closed.',
  },
  'syntax/invalid-escape': {
    source: 'doc',
    severity: 'error',
    summary: 'Backslash followed by something that is not a documented escape sequence.',
    ambiguity: ['E-03', 'E-04'],
  },
  'syntax/bad-interpolation': {
    source: 'doc',
    severity: 'error',
    summary: 'A "$" inside a string that is not followed by a variable name, "(" or "[".',
  },
  'syntax/bare-dollar': {
    source: 'device',
    severity: 'error',
    summary: 'A "$" that is not followed by a variable name.',
  },
  'syntax/dollar-expression-outside-string': {
    source: 'device',
    severity: 'error',
    summary: '"$(" and "$[" are only valid inside a string.',
    ambiguity: ['O-09'],
  },
  'syntax/missing-closer': {
    source: 'doc',
    severity: 'error',
    summary: 'A "(", "[" or "{" is never closed.',
  },
  'syntax/unexpected-closer': {
    source: 'device',
    severity: 'error',
    summary: 'A ")" without a matching "(".',
  },
  'syntax/stray-closer': {
    source: 'open',
    severity: 'warning',
    summary: 'A "}" or "]" without a matching opener. RouterOS accepts it.',
    ambiguity: ['L-13'],
  },
  'syntax/adjacent-tokens': {
    source: 'device',
    severity: 'error',
    summary: 'Two values written with no space between them.',
    ambiguity: ['L-10', 'L-16'],
  },
  'syntax/space-before-equals': {
    source: 'doc',
    severity: 'error',
    summary: 'Whitespace before "=" in a parameter.',
    ambiguity: ['L-09'],
  },
  'syntax/unexpected-equals': {
    source: 'device',
    severity: 'error',
    summary: 'An "=" that does not belong to a parameter.',
    ambiguity: ['L-16'],
  },
  'syntax/statement-starts-with-pair': {
    source: 'device',
    severity: 'error',
    summary: 'A command line that starts with name=value, for example "else=" on its own line.',
    ambiguity: ['C-12', 'A-01'],
  },
  'syntax/trailing-comment': {
    source: 'device',
    severity: 'error',
    summary: 'A "#" after the first word of a command is an argument, not a comment.',
    ambiguity: ['L-01'],
  },
  'syntax/missing-separator': {
    source: 'device',
    severity: 'error',
    summary: 'Two commands on one line without ";" between them.',
    ambiguity: ['L-11'],
  },
  'syntax/invalid-character': {
    source: 'device',
    severity: 'error',
    summary: 'A character that RouterOS does not accept outside a string.',
    ambiguity: ['L-15', 'L-16'],
  },
  'syntax/newline-in-parens': {
    source: 'device',
    severity: 'error',
    summary: 'A line break inside "( )" without a backslash.',
  },
  'syntax/empty-expression': {
    source: 'device',
    severity: 'error',
    summary: 'An empty "( )".',
  },
  'syntax/expected-operand': {
    source: 'device',
    severity: 'error',
    summary: 'An operator without the value it needs.',
  },
  'syntax/unexpected-token': {
    source: 'device',
    severity: 'error',
    summary: 'A token that cannot appear inside an expression.',
  },
  'syntax/expected-command': {
    source: 'doc',
    severity: 'error',
    summary: 'A prefix such as ":" with no command after it, or a line that starts with something that cannot be a command.',
  },
  'syntax/stray-backslash': {
    source: 'open',
    severity: 'warning',
    summary: 'A backslash outside a string that does not end the line. The documentation calls it illegal; RouterOS ignores it.',
    ambiguity: ['L-03'],
  },
  'syntax/too-deeply-nested': {
    source: 'open',
    severity: 'error',
    summary: 'Brackets nested deeper than the parser follows.',
  },
  'vars/set-undeclared': {
    source: 'device',
    severity: 'error',
    summary: ':set of a variable that is not declared in the same or an enclosing block.',
    ambiguity: ['V-01', 'V-03', 'V-04'],
  },
  'vars/undeclared-read': {
    source: 'doc',
    severity: 'warning',
    summary: 'A variable is read but never declared in the file. RouterOS reads it as empty.',
    ambiguity: ['V-01', 'V-14'],
  },
  'vars/local-out-of-scope': {
    source: 'device',
    severity: 'warning',
    summary: 'A local variable is read where its scope has ended, for example on a later top-level line of an imported file.',
    ambiguity: ['V-03'],
  },
  'vars/invalid-name': {
    source: 'device',
    severity: 'error',
    summary: 'A variable name with characters other than letters and digits, written without quotes, or with a "$" where it is declared.',
    ambiguity: ['V-07'],
  },
  'vars/keyword-name': {
    source: 'doc',
    severity: 'warning',
    summary: 'A variable named and, or or in. The documentation reserves them; RouterOS accepts them.',
    ambiguity: ['V-08'],
  },
} as const satisfies Record<string, RuleInfo>;

export type RuleId = keyof typeof RULES;

export function ruleInfo(id: RuleId): RuleInfo {
  return RULES[id];
}
