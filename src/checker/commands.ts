import { matchName, suggest, type ArgInfo, type NodeInfo, type Schema } from '../schema/schema.js';
import type { Brace, Element, Named, Script, Statement, Subst, Word } from '../syntax/ast.js';
import type { RuleFinding } from './variables.js';

/**
 * The menu path in effect at a point of the script. RouterOS resolves it while compiling, in source order, and only a
 * line that is nothing but a path changes it; a full command does not (probes s1 to s30 and l1 to l24):
 *   top level, a bare { } block, a statement-level [ ] and the block after a path ("/ip { route }") carry it forward;
 *   the bodies of :if, :do, functions and so on, and every command argument, start from it but cannot change it.
 * `null` means unknown, after a mistake in a path. Nothing is reported about relative words until an absolute path resets it.
 */
export type Path = readonly string[] | null;

type Head =
  | { readonly kind: 'path'; readonly path: Path; readonly rest: readonly Element[] }
  | { readonly kind: 'command'; readonly node: NodeInfo; readonly word: Word; readonly args: readonly Element[]; readonly menuPath: readonly string[]; readonly commandPath: readonly string[] }
  | { readonly kind: 'failed' }
  | { readonly kind: 'unchecked' };

/** What a word of a command line turned out to be. Hover and completion read these. */
export type WordResolution =
  | { readonly kind: 'menu' | 'command'; readonly start: number; readonly end: number; readonly name: string; readonly path: readonly string[]; readonly node: NodeInfo }
  | { readonly kind: 'parameter'; readonly start: number; readonly end: number; readonly name: string; readonly path: readonly string[]; readonly node: NodeInfo; readonly arg: ArgInfo; readonly required: boolean };

export interface CommandAnalysis {
  readonly findings: RuleFinding[];
  readonly resolutions: WordResolution[];
  /** The menu path in effect at the start of every statement; null where it is unknown. */
  readonly contexts: Map<Statement, Path>;
  /** The menu path after every statement, which differs from the one before only for a line that is just a path. */
  readonly after: Map<Statement, Path>;
  /** The menu path in effect where each block and command substitution starts. */
  readonly bodies: Map<Brace | Subst, Path>;
}

export function checkCommands(script: Script, schema: Schema): CommandAnalysis {
  return new CommandChecker(schema).run(script);
}

/** Splits a word such as "ip/address" or "..add" into the names it holds, with their offsets. */
function segments(text: string): Array<{ text: string; offset: number }> {
  const out: Array<{ text: string; offset: number }> = [];
  let offset = 0;
  for (const part of text.split('/')) {
    let at = offset;
    let rest = part;
    while (rest.startsWith('..')) {
      out.push({ text: '..', offset: at });
      rest = rest.slice(2);
      at += 2;
    }
    if (rest !== '') out.push({ text: rest, offset: at });
    offset += part.length + 1;
  }
  return out;
}

function nameOf(named: Named): string {
  return named.name.kind === 'word' ? named.name.text : named.name.value;
}

/**
 * Commands that accept any parameter, or the same parameter again: the router compiled `:do command=0 zzznope=0` and
 * `/ip recursive-print zzznope=0` (research/tools/differential.py). Their parameters are not checked.
 */
const FREE_FORM = new Set(['do', 'time', 'retry', 'onerror', 'recursive-print', 'shell']);

/** Commands that exist only inside the body of a loop. They are not in the command tree (probes p19, p20). */
const LOOP_COMMANDS = new Set(['break', 'continue']);
const LOOP_STATEMENTS = new Set(['for', 'foreach', 'while', 'do']);
const LOOP_ONLY_NODE: NodeInfo = { k: 1, d: 'Leave the loop or go on with its next round. Valid only inside a loop.' };

class CommandChecker {
  private loopDepth = 0;
  private readonly findings: RuleFinding[] = [];
  private readonly resolutions: WordResolution[] = [];
  private readonly contexts = new Map<Statement, Path>();
  private readonly after = new Map<Statement, Path>();
  private readonly bodies = new Map<Brace | Subst, Path>();

  constructor(private readonly schema: Schema) {}

  run(script: Script): CommandAnalysis {
    this.statements(script.statements, [], true);
    return { findings: this.findings, resolutions: this.resolutions, contexts: this.contexts, after: this.after, bodies: this.bodies };
  }

  private report(rule: RuleFinding['rule'], message: string, start: number, end: number): void {
    this.findings.push({ rule, message, start, end });
  }

  private node(path: readonly string[]): NodeInfo {
    let node = this.schema.root;
    for (const name of path) node = node.c?.[name] ?? node;
    return node;
  }

  // ---------------------------------------------------------------------------------------------------------------
  // Walking

  /**
   * The statements of one list see each other's path changes. What the list returns is the path after it when `carry` is
   * set (the caller keeps it) and the path it was given otherwise.
   *
   * `lenient` is for braces that may be an array rather than code: only lines that are clearly commands (they start with
   * ":" or "/") are checked, because `{1;2;3}` and `{ add ... }` cannot be told apart by their syntax.
   */
  private statements(list: readonly Statement[], path: Path, carry: boolean, lenient = false): Path {
    let current = path;
    for (const statement of list) {
      current = this.statement(statement, current, lenient);
      this.after.set(statement, current);
    }
    return carry ? current : path;
  }

  private statement(statement: Statement, path: Path, lenient = false): Path {
    this.contexts.set(statement, path);
    const head = this.head(statement, path, lenient);
    const elements = statement.elements;

    // Statement-level { } and [ ] and the block after a path share the path with the code around them. A path written
    // with a colon (":ip route") reaches the menu but does not make it the current one (probe in session, suite 20).
    if (head.kind === 'path') {
      let current = statement.prefix === ':' ? path : head.path;
      let closed = false;
      for (const element of head.rest) {
        if (closed) {
          // nothing can follow a block on its line (probes z23, z24)
          this.report('schema/unexpected-argument', "Nothing can follow a closing brace or bracket on the same line. Put ';' or a line break after it.", element.start, element.end);
          closed = false;
        }
        if (element.kind === 'brace' || element.kind === 'subst') {
          this.bodies.set(element, current);
          current = this.statements(element.body, current, true);
          closed = true;
        } else this.nested(element, current);
      }
      return current;
    }

    const base = path;
    if (head.kind === 'command') {
      this.arguments(head.node, head.commandPath, head.word, head.args);
      // "/ip address remove [find]" runs find in /ip address; a global command keeps the path of the code around it.
      const inside = statement.prefix === ':' ? base : head.menuPath;
      const loops = head.commandPath.length === 1 && LOOP_STATEMENTS.has(head.commandPath[0]!);
      if (loops) this.loopDepth++;
      for (const element of head.args) this.nested(element, inside);
      if (loops) this.loopDepth--;
    } else {
      for (const element of elements) this.nested(element, base);
    }
    return head.kind === 'failed' ? null : path;
  }

  /** Visits the constructs inside an element. They see `path` and cannot change it. */
  private nested(element: Element, path: Path): void {
    switch (element.kind) {
      case 'named':
        if (element.value) this.nested(element.value, path);
        break;
      case 'brace':
        this.bodies.set(element, path);
        this.statements(element.body, path, false, element.role !== 'block');
        break;
      case 'subst':
        this.bodies.set(element, path);
        this.statements(element.body, path, false);
        break;
      case 'group':
        for (const expr of element.exprs) this.expr(expr, path);
        break;
      case 'string':
        for (const part of element.parts) {
          if (part.kind === 'command') this.nested(part.subst, path);
          else if (part.kind === 'expression') this.nested(part.group, path);
        }
        break;
      default:
        break;
    }
  }

  private expr(expr: import('../syntax/ast.js').Expr, path: Path): void {
    switch (expr.kind) {
      case 'binary':
        this.expr(expr.left, path);
        this.expr(expr.right, path);
        break;
      case 'unary':
        this.expr(expr.operand, path);
        break;
      case 'word':
      case 'missing':
        break;
      default:
        this.nested(expr, path);
    }
  }

  // ---------------------------------------------------------------------------------------------------------------
  // The words at the start of a command line: menu path and command

  private head(statement: Statement, path: Path, lenient: boolean): Head {
    const elements = statement.elements;
    const { prefix } = statement;
    if (prefix === '/' && elements.length === 0) return { kind: 'path', path: [], rest: [] };
    if (elements.length === 0) return { kind: 'path', path, rest: [] };
    if (lenient && prefix === null) return { kind: 'unchecked' };
    // a line that is only [ ... ] runs its command with the path of the code around it, and keeps any path it sets (probe l9)
    if (prefix === null && elements.length === 1 && elements[0]!.kind === 'subst') return { kind: 'path', path, rest: elements };

    let current: readonly string[];
    if (prefix === '/' || prefix === ':') current = [];
    else if (path === null) return { kind: 'unchecked' };
    else current = path;

    // After ':' the word may still be a menu: ":log info" is the command info of the menu log.
    const colon = prefix === ':';
    let node = this.node(current);
    for (let i = 0; i < elements.length; i++) {
      const element = elements[i]!;
      if (element.kind === 'brace' && !colon) return { kind: 'path', path: current, rest: elements.slice(i) };
      if (element.kind !== 'word') {
        // a value where a name is expected: nothing sensible to say about the path
        return i === 0 ? { kind: 'unchecked' } : { kind: 'path', path: current, rest: elements.slice(i) };
      }
      for (const segment of segments(element.text)) {
        const start = element.start + segment.offset;
        const end = start + segment.text.length;
        if (segment.text === '..') {
          current = current.slice(0, -1);
          node = this.node(current);
          continue;
        }
        const match = matchName(node.c, segment.text);
        if (match.kind === 'none' && this.loopDepth > 0 && current.length === 0 && LOOP_COMMANDS.has(segment.text)) {
          return { kind: 'command', node: LOOP_ONLY_NODE, word: element, args: elements.slice(i + 1), menuPath: current, commandPath: [segment.text] };
        }
        if (match.kind === 'ambiguous') {
          this.report('schema/ambiguous-name', `'${segment.text}' could be any of ${match.candidates.slice(0, 6).join(', ')}${match.candidates.length > 6 ? ' ...' : ''}. Write more of the name.`, start, end);
          return { kind: 'failed' };
        }
        if (match.kind === 'none') {
          this.unknownCommand(segment.text, node, current, colon, start, end);
          return { kind: 'failed' };
        }
        this.resolutions.push({ kind: match.value.k ? 'command' : 'menu', start, end, name: match.name, path: [...current, match.name], node: match.value });
        if (match.value.k) {
          const rest = elements.slice(i + 1);
          return { kind: 'command', node: match.value, word: element, args: rest, menuPath: current, commandPath: [...current, match.name] };
        }
        current = [...current, match.name];
        node = match.value;
      }
    }
    return { kind: 'path', path: current, rest: [] };
  }

  private unknownCommand(word: string, node: NodeInfo, path: readonly string[], colon: boolean, start: number, end: number): void {
    const where = path.length === 0 ? (colon ? 'the global commands' : 'the top level') : `/${path.join(' ')}`;
    let message = `'${word}' is not a ${colon ? 'global command' : 'menu or command'} in ${where} of the RouterOS ${this.schema.version} command database.`;
    const close = suggest(Object.keys(node.c ?? {}), word);
    if (close.length > 0) message += ` Did you mean ${close.map((n) => `'${n}'`).join(', ')}?`;
    else if (!colon && path.length > 0 && this.schema.root.c?.[word]?.k) message += ` Global commands need a ':' inside a menu: ':${word}'.`;
    else if (!colon && path.length > 0 && this.schema.root.c?.[word]) message += ` '${word}' is a top-level menu; start the line with '/' to reach it from here.`;
    this.report('schema/unknown-command', message, start, end);
  }

  // ---------------------------------------------------------------------------------------------------------------
  // The arguments of a command

  private arguments(command: NodeInfo, commandPath: readonly string[], word: Word, args: readonly Element[]): void {
    const table = command.a;
    const allowedUnnamed = command.u ?? 0;
    // find takes any property as a condition (probes w1 to w6)
    const commandName = commandPath[commandPath.length - 1]!;
    const conditions = commandName === 'find' && table !== undefined && 'where' in table;
    const openConditions = conditions || FREE_FORM.has(commandName);
    const provided = new Set<string>();
    let unnamed = 0;
    // RouterOS reports the first problem of a command line only. A missing parameter that follows from a mistyped or
    // surplus one is not worth a second message.
    let mistaken = false;

    const takeUnnamed = (element: Element): void => {
      unnamed++;
      if (unnamed === allowedUnnamed + 1) {
        mistaken = true;
        const what = allowedUnnamed === 0 ? 'This command takes no unnamed arguments' : `This command takes at most ${allowedUnnamed} unnamed ${allowedUnnamed === 1 ? 'argument' : 'arguments'}`;
        const comment = element.kind === 'word' && element.text.startsWith('#');
        const message = comment
          ? `${what}, and a '#' only starts a comment at the beginning of a command, so RouterOS reads this as an argument. Put ';' before the comment.`
          : `${what}. Name the parameter (name=value), or check for a missing ';' between commands.`;
        this.report('schema/unexpected-argument', message, element.start, element.end);
      }
    };

    for (const element of args) {
      if (element.kind === 'word') {
        if (element.text === 'where') {
          // RouterOS needs a condition after it (probe b15)
          if (element === args[args.length - 1] && table !== undefined && 'where' in table) {
            mistaken = true;
            this.report('schema/parameter-needs-value', "'where' needs a condition after it.", element.start, element.end);
          }
          break;
        }
        if (element.text.startsWith('!')) continue;
        const match = matchName(table, element.text);
        if (conditions) continue;
        // Where a command takes unnamed values, a word that is only the start of a parameter name is such a value
        // (probes b1 to b3). Where it takes none, only a flag can stand without a value (b5, b6).
        if (match.kind === 'found' && (allowedUnnamed === 0 || match.name === element.text || match.value.f === 1)) {
          provided.add(match.name);
          this.parameter(command, commandPath, match.name, match.value, element.start, element.end);
          if (allowedUnnamed === 0 && match.value.f !== 1) {
            mistaken = true;
            this.report('schema/parameter-needs-value', `'${match.name}' takes a value: write ${match.name}=...`, element.start, element.end);
          }
        } else if (match.kind === 'ambiguous' && allowedUnnamed === 0) {
          mistaken = true;
          this.ambiguous(element.text, match.candidates, element.start, element.end);
        } else takeUnnamed(element);
      } else if (element.kind === 'named') {
        const key = nameOf(element);
        const match = matchName(table, key);
        const end = element.name.end;
        if (match.kind === 'found') {
          if (provided.has(match.name) && !openConditions) {
            this.report('schema/duplicate-parameter', `'${match.name}' is given more than once.`, element.start, end);
          }
          provided.add(match.name);
          this.parameter(command, commandPath, match.name, match.value, element.name.start, end);
          if (match.value.f === 1) {
            mistaken = true;
            this.report('schema/flag-with-value', `'${match.name}' is a flag and takes no value: write it without '=' (probes b13, b14).`, element.equalsAt, element.equalsAt + 1);
          }
        } else if (match.kind === 'ambiguous') {
          mistaken = true;
          this.ambiguous(key, match.candidates, element.start, end);
        } else if (!openConditions) {
          mistaken = true;
          const close = suggest(Object.keys(table ?? {}), key);
          const hint = close.length > 0 ? ` Did you mean ${close.map((n) => `'${n}'`).join(', ')}?` : '';
          this.report('schema/unknown-parameter', `'${key}' is not a parameter of this command in the RouterOS ${this.schema.version} command database.${hint}`, element.start, end);
        }
      } else if (element.kind !== 'operator') {
        takeUnnamed(element);
      }
    }

    // Unnamed values fill the required arguments that were not named, in the order RouterOS lists them.
    const required = (command.r ?? []).filter((name) => !provided.has(name));
    const missing = required.slice(Math.min(unnamed, required.length));
    if (missing.length > 0 && !mistaken) {
      this.report('schema/missing-required', `Missing ${missing.length === 1 ? 'a value' : 'values'} for ${missing.join(', ')}.`, word.start, word.end);
    }
  }

  private parameter(command: NodeInfo, path: readonly string[], name: string, arg: ArgInfo, start: number, end: number): void {
    this.resolutions.push({ kind: 'parameter', start, end, name, path, node: command, arg, required: command.r?.includes(name) ?? false });
  }

  private ambiguous(word: string, candidates: string[], start: number, end: number): void {
    this.report('schema/ambiguous-name', `'${word}' could be any of ${candidates.slice(0, 6).join(', ')}${candidates.length > 6 ? ' ...' : ''}. Write more of the name.`, start, end);
  }
}
