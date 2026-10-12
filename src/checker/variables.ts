import type { BindResult, Reference } from '../binder/binder.js';
import type { RuleId } from '../rules.js';

export interface RuleFinding {
  readonly rule: RuleId;
  readonly message: string;
  readonly start: number;
  readonly end: number;
}

const KEYWORDS = new Set(['and', 'or', 'in']);

function more(count: number): string {
  return count === 0 ? '' : ` It is read ${count} more ${count === 1 ? 'time' : 'times'} in this file with the same result.`;
}

function checkWrite(reference: Reference): RuleFinding | null {
  const { name, start, end, resolution } = reference;
  if (resolution.kind === 'declared') return null;
  let message = `':set ${name}' needs '${name}' to be declared first, with ':local ${name}' or ':global ${name}' earlier in the same block or in a block around it.`;
  if (resolution.kind === 'local-elsewhere' && resolution.crossedFunction) {
    message += ' A function cannot set variables of the code around it; declare the name inside the function.';
  } else if (resolution.kind === 'local-elsewhere') {
    message += ` '${name}' is declared elsewhere in this file, but each line of an imported file is its own scope and a block that has ended hides its names. Declare it again here or put the commands in one { } block.`;
  }
  return { rule: 'vars/set-undeclared', message, start, end };
}

/**
 * A variable that is read where it does not exist is reported once, at its first read, with the number of further reads.
 * Every later read has the same cause, and one warning per read buries the useful ones.
 */
function checkReads(references: Reference[]): RuleFinding[] {
  const groups = new Map<string, Reference[]>();
  for (const reference of references) {
    if (reference.access !== 'read') continue;
    const { resolution } = reference;
    let key: string | null = null;
    if (resolution.kind === 'none') key = `none:${reference.name}`;
    else if (resolution.kind === 'local-elsewhere') key = `local:${reference.name}:${resolution.declaration.start}`;
    if (key === null) continue;
    const list = groups.get(key) ?? [];
    list.push(reference);
    groups.set(key, list);
  }

  const findings: RuleFinding[] = [];
  for (const list of groups.values()) {
    const first = list[0]!;
    const rest = more(list.length - 1);
    if (first.resolution.kind === 'none') {
      findings.push({
        rule: 'vars/undeclared-read',
        message: `$${first.name} is not declared in this file. The documentation requires a declaration before use; RouterOS 7.21.4 reads an undeclared variable as empty. Declare it with ':local ${first.name}' or ':global ${first.name}', or list it under "contextVariables" if RouterOS provides it.${rest}`,
        start: first.start,
        end: first.end,
      });
    } else {
      findings.push({
        rule: 'vars/local-out-of-scope',
        message: `$${first.name} is a local variable of an earlier line or of a block that has ended, so it is empty here (an imported file gives every line its own scope). Use ':global ${first.name}' or put the commands in one { } block.${rest}`,
        start: first.start,
        end: first.end,
      });
    }
  }
  return findings;
}

function checkNames(bound: BindResult): RuleFinding[] {
  const findings: RuleFinding[] = [];
  for (const site of bound.nameSites) {
    // A quoted name may contain anything.
    if (site.element.kind === 'string') continue;
    if (site.element.kind === 'variable') {
      findings.push({
        rule: 'vars/invalid-name',
        message: "Write the variable name without '$' when you declare it. The '$' is only for reading a variable.",
        start: site.element.start,
        end: site.element.start + 1,
      });
      continue;
    }
    const bad = /[^A-Za-z0-9]/.exec(site.text);
    if (bad) {
      const at = site.start + bad.index;
      findings.push({
        rule: 'vars/invalid-name',
        message: `A variable name written without quotes may only contain letters and digits, not '${bad[0]}'. Quote the name: "${site.text}".`,
        start: at,
        end: at + bad[0].length,
      });
    } else if (KEYWORDS.has(site.text)) {
      findings.push({
        rule: 'vars/keyword-name',
        message: `'${site.text}' is a keyword and the documentation does not allow it as a variable name. RouterOS accepts it, but it is easy to misread.`,
        start: site.start,
        end: site.start + site.text.length,
      });
    }
  }
  return findings;
}

export function checkVariables(bound: BindResult): RuleFinding[] {
  const findings: RuleFinding[] = [];
  for (const named of bound.namedDeclarations) {
    const name = named.name.kind === 'word' ? named.name.text : named.name.value;
    findings.push({
      rule: 'vars/invalid-name',
      message: `Declare a variable as ':local ${name} value', with the name and the value as separate arguments, not as '${name}=value'.`,
      start: named.equalsAt,
      end: named.equalsAt + 1,
    });
  }
  for (const reference of bound.references) {
    if (reference.access !== 'write') continue;
    const finding = checkWrite(reference);
    if (finding) findings.push(finding);
  }
  findings.push(...checkReads(bound.references), ...checkNames(bound));
  return findings;
}
