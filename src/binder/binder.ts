import type { Element, Expr, Named, Script, Statement, StringLit, Variable, Word } from '../syntax/ast.js';

/**
 * Scopes follow what RouterOS 7.21.4 does (docs/ambiguities.md V-01 to V-05, probe suites 13 to 15):
 *  - a name is declared by :local, :global, the variable of :for, :foreach and :onerror, and only for the commands after it
 *  - a block sees the declarations of the blocks around it, a function body only its own
 *  - in an imported file every line is a scope of its own, however many commands ";" puts on it; in a script body the
 *    whole file is one (probes d1 and h25)
 */
export type ScopeKind = 'file' | 'statement' | 'block' | 'loop' | 'function';
export type ScopeMode = 'import' | 'script';

export interface Scope {
  readonly kind: ScopeKind;
  readonly parent: Scope | null;
  readonly declarations: Map<string, Declaration>;
  /** The source range the scope covers. A line scope grows with each statement added to the line. */
  start: number;
  end: number;
}

export interface Declaration {
  readonly name: string;
  readonly kind: 'local' | 'global' | 'loop';
  readonly start: number;
  readonly end: number;
  readonly scope: Scope;
  /** From this offset on the name exists: the end of the declaring command, so a command's own value does not see it. */
  readonly from: number;
}

export type Resolution =
  /** In scope. */
  | { readonly kind: 'declared'; readonly declaration: Declaration }
  /** A global declared elsewhere in the file. RouterOS finds it at run time without a new declaration. */
  | { readonly kind: 'global-elsewhere'; readonly declaration: Declaration }
  /** A local that exists in the file but is not visible here. */
  | { readonly kind: 'local-elsewhere'; readonly declaration: Declaration; readonly crossedFunction: boolean }
  /** Not checked: a positional name, a name RouterOS provides, or any name inside a function body (it may be an argument). */
  | { readonly kind: 'exempt' }
  | { readonly kind: 'none' };

export interface Reference {
  readonly name: string;
  readonly start: number;
  readonly end: number;
  readonly access: 'read' | 'write';
  readonly resolution: Resolution;
}

/** A place where a variable name is written without a $: the checker validates the characters. */
export interface NameSite {
  readonly element: Word | StringLit | Variable;
  readonly text: string;
  /** Offset of the first character of `text` in the document. */
  readonly start: number;
}

export interface BindOptions {
  readonly mode: ScopeMode;
  /** Variables the environment provides, for example the lease script variables. */
  readonly contextVariables: ReadonlySet<string>;
}

export interface BindResult {
  readonly scopes: Scope[];
  readonly declarations: Declaration[];
  readonly references: Reference[];
  readonly nameSites: NameSite[];
  /** ":local name=value" and ":global name=value", which RouterOS rejects: the name and value are separate arguments. */
  readonly namedDeclarations: Named[];
}

function wordText(element: Element | undefined): string | null {
  return element?.kind === 'word' ? element.text : null;
}

export function bind(script: Script, text: string, options: BindOptions): BindResult {
  return new Binder(text, options).run(script);
}

/** Whether a line break that a backslash does not join lies between the two offsets. */
function breaksLine(text: string, from: number, to: number): boolean {
  for (let i = from; i < to; i++) {
    const c = text[i];
    if (c !== '\n' && c !== '\r') continue;
    // the LF of a CR LF pair belongs to the break already counted at the CR
    if (c === '\n' && i - 1 >= from && text[i - 1] === '\r') continue;
    let p = i - 1;
    if (text[p] === '\r') p--;
    while (p >= from && (text[p] === ' ' || text[p] === '\t')) p--;
    if (p < from || text[p] !== '\\') return true;
  }
  return false;
}

class Binder {
  private readonly scopes: Scope[] = [];
  private readonly declarations: Declaration[] = [];
  private readonly references: Reference[] = [];
  private readonly nameSites: NameSite[] = [];
  private readonly namedDeclarations: Named[] = [];

  constructor(
    private readonly text: string,
    private readonly options: BindOptions,
  ) {}

  run(script: Script): BindResult {
    const file = this.scope('file', null, 0, script.end);
    let line = this.scope('statement', null, 0, 0);
    let previousEnd = 0;
    for (const statement of script.statements) {
      if (this.options.mode === 'import' && breaksLine(this.text, previousEnd, statement.start)) line = this.scope('statement', null, statement.start, statement.start);
      const scope = this.options.mode === 'import' ? line : file;
      if (scope === line) {
        if (line.end === line.start) line.start = statement.start;
        line.end = statement.end;
      }
      this.statement(statement, scope);
      previousEnd = statement.end;
    }
    return { scopes: this.scopes, declarations: this.declarations, references: this.references, nameSites: this.nameSites, namedDeclarations: this.namedDeclarations };
  }

  private scope(kind: ScopeKind, parent: Scope | null, start: number, end: number): Scope {
    const scope: Scope = { kind, parent, declarations: new Map(), start, end };
    this.scopes.push(scope);
    return scope;
  }

  private declare(scope: Scope, name: string, kind: Declaration['kind'], start: number, end: number, from: number): void {
    const declaration: Declaration = { name, kind, start, end, scope, from };
    scope.declarations.set(name, declaration);
    this.declarations.push(declaration);
  }

  // ---------------------------------------------------------------------------------------------------------------
  // Commands that declare or assign

  private statement(statement: Statement, scope: Scope): void {
    const head = statement.elements[0];
    const command = statement.prefix === ':' ? wordText(head) : null;
    switch (command) {
      case 'local':
      case 'global':
        this.declaration(statement, scope, command);
        return;
      case 'set':
        this.assignment(statement, scope);
        return;
      case 'for':
      case 'foreach':
        this.loop(statement, scope, ['do'], false);
        return;
      case 'onerror':
        this.loop(statement, scope, ['do', 'in'], true);
        return;
      default:
        this.elements(statement.elements, scope);
    }
  }

  private nameOf(element: Element | undefined): { text: string; start: number; end: number; element: Word | StringLit | Variable } | null {
    if (element?.kind === 'word') return { text: element.text, start: element.start, end: element.end, element };
    if (element?.kind === 'string' && element.closed) return { text: element.value, start: element.start, end: element.end, element };
    if (element?.kind === 'variable') return { text: element.name, start: element.start, end: element.end, element };
    return null;
  }

  private declaration(statement: Statement, scope: Scope, kind: 'local' | 'global'): void {
    // ":local name=x" names the parameter `name` (or an abbreviation of it); any other key is not a parameter at all
    const first = statement.elements[1];
    const key = first?.kind === 'named' ? (first.name.kind === 'word' ? first.name.text : first.name.value) : '';
    const parameter = key !== '' && ['name', 'value', 'do'].some((p) => p.startsWith(key));
    if (first?.kind === 'named' && !parameter) this.namedDeclarations.push(first);
    const byParameter = first?.kind === 'named' && 'name'.startsWith(key) && key !== '' ? first.value : null;
    const name = this.nameOf(byParameter ?? first);
    const rest = statement.elements.slice(byParameter ? 2 : name ? 2 : 1);
    if (name) this.nameSites.push({ element: name.element, text: name.text, start: name.start });

    for (const element of rest) {
      // :global name do={ ... } defines a function. Its body sees neither the locals nor the arguments of the code around it.
      if (element.kind === 'named' && wordText(element.name) === 'do' && element.value?.kind === 'brace') {
        const body = this.scope('function', scope, element.value.start, element.value.end);
        for (const inner of element.value.body) this.statement(inner, body);
      } else {
        this.elements([element], scope);
      }
    }
    // The name exists for the commands after this one, not for its own value.
    if (name && name.element.kind !== 'variable' && name.text !== '') this.declare(scope, name.text, kind, name.start, name.end, statement.end);
  }

  private assignment(statement: Statement, scope: Scope): void {
    const target = statement.elements[1];
    if (target?.kind === 'word') {
      this.nameSites.push({ element: target, text: target.text, start: target.start });
      this.references.push({
        name: target.text,
        start: target.start,
        end: target.end,
        access: 'write',
        resolution: this.resolveWrite(target.text, scope),
      });
      this.elements(statement.elements.slice(2), scope);
    } else {
      // :set "quoted name", :set $name and :set ($array->key) are not checked against the declarations.
      this.elements(statement.elements.slice(1), scope);
    }
  }

  /**
   * :for i, :foreach k,v and :onerror e. The word after the command names the variables its bodies can use.
   * `bodies` are the parameters whose braces see them; with `bareBody` an unnamed brace does too.
   */
  private loop(statement: Statement, scope: Scope, bodies: string[], bareBody: boolean): void {
    const nameIndex = 1;
    const nameElement = statement.elements[nameIndex];
    const names: Array<{ text: string; start: number; end: number }> = [];
    if (nameElement?.kind === 'word') {
      this.nameSites.push(...this.loopNameSites(nameElement));
      let offset = nameElement.start;
      for (const part of nameElement.text.split(',')) {
        if (part !== '') names.push({ text: part, start: offset, end: offset + part.length });
        offset += part.length + 1;
      }
    }
    const inner = this.scope('loop', scope, statement.start, statement.end);
    for (const n of names) this.declare(inner, n.text, 'loop', n.start, n.end, n.end);

    statement.elements.forEach((element, index) => {
      if (index === nameIndex && nameElement?.kind === 'word') return;
      if (element.kind === 'named' && element.value?.kind === 'brace' && bodies.includes(wordText(element.name) ?? '')) {
        for (const s of element.value.body) this.statement(s, inner);
      } else if (bareBody && element.kind === 'brace') {
        for (const s of element.body) this.statement(s, inner);
      } else {
        this.elements([element], scope);
      }
    });
  }

  private loopNameSites(word: Word): NameSite[] {
    const sites: NameSite[] = [];
    let offset = word.start;
    for (const part of word.text.split(',')) {
      sites.push({ element: word, text: part, start: offset });
      offset += part.length + 1;
    }
    return sites;
  }

  // ---------------------------------------------------------------------------------------------------------------
  // Reading

  private elements(elements: readonly Element[], scope: Scope): void {
    for (const element of elements) this.element(element, scope);
  }

  private element(element: Element, scope: Scope): void {
    switch (element.kind) {
      case 'variable':
        this.read(element.name, element.start, element.end, scope);
        break;
      case 'string':
        this.string(element, scope);
        break;
      case 'subst':
        for (const s of element.body) this.statement(s, scope);
        break;
      case 'group':
        for (const e of element.exprs) this.expr(e, scope);
        break;
      case 'brace': {
        const inner = this.scope('block', scope, element.start, element.end);
        for (const s of element.body) this.statement(s, inner);
        break;
      }
      case 'named':
        if (element.name.kind === 'string') this.string(element.name, scope);
        if (element.value) this.element(element.value, scope);
        break;
      default:
        break;
    }
  }

  private expr(expr: Expr, scope: Scope): void {
    switch (expr.kind) {
      case 'binary':
        this.expr(expr.left, scope);
        this.expr(expr.right, scope);
        break;
      case 'unary':
        this.expr(expr.operand, scope);
        break;
      case 'word':
      case 'missing':
        break;
      default:
        this.element(expr, scope);
    }
  }

  private string(literal: StringLit, scope: Scope): void {
    for (const part of literal.parts) {
      if (part.kind === 'variable') this.read(part.name, part.start, part.end, scope);
      else if (part.kind === 'expression') this.element(part.group, scope);
      else if (part.kind === 'command') this.element(part.subst, scope);
    }
  }

  private read(name: string, start: number, end: number, scope: Scope): void {
    if (name === '') return;
    this.references.push({ name, start, end, access: 'read', resolution: this.resolveRead(name, scope) });
  }

  // ---------------------------------------------------------------------------------------------------------------
  // Resolution

  private lookup(name: string, scope: Scope): { declaration: Declaration; crossedFunction: boolean } | null {
    let crossedFunction = false;
    for (let s: Scope | null = scope; s; s = s.parent) {
      const declaration = s.declarations.get(name);
      if (declaration) return { declaration, crossedFunction };
      if (s.kind === 'function') crossedFunction = true;
    }
    return null;
  }

  private insideFunction(scope: Scope): boolean {
    for (let s: Scope | null = scope; s; s = s.parent) if (s.kind === 'function') return true;
    return false;
  }

  /** An earlier declaration of the name anywhere in the file, preferring a global. */
  private elsewhere(name: string): Declaration | null {
    let found: Declaration | null = null;
    for (const d of this.declarations) {
      if (d.name !== name) continue;
      if (d.kind === 'global') return d;
      found = d;
    }
    return found;
  }

  private resolveRead(name: string, scope: Scope): Resolution {
    if (/^[0-9]+$/.test(name) || this.options.contextVariables.has(name)) return { kind: 'exempt' };
    const found = this.lookup(name, scope);
    if (found && !found.crossedFunction) return { kind: 'declared', declaration: found.declaration };
    if (found?.declaration.kind === 'global') return { kind: 'global-elsewhere', declaration: found.declaration };
    // A function body can read any global by name and receives arguments under names the file does not declare.
    if (this.insideFunction(scope)) return { kind: 'exempt' };
    const other = this.elsewhere(name);
    if (other?.kind === 'global') return { kind: 'global-elsewhere', declaration: other };
    if (other) return { kind: 'local-elsewhere', declaration: other, crossedFunction: false };
    return { kind: 'none' };
  }

  private resolveWrite(name: string, scope: Scope): Resolution {
    const found = this.lookup(name, scope);
    if (found && !found.crossedFunction) return { kind: 'declared', declaration: found.declaration };
    if (found) return { kind: 'local-elsewhere', declaration: found.declaration, crossedFunction: true };
    const other = this.elsewhere(name);
    if (other) return { kind: 'local-elsewhere', declaration: other, crossedFunction: false };
    return { kind: 'none' };
  }
}
