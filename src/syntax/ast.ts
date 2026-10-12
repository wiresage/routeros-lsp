/** Syntax tree. Offsets are UTF-16 string indexes, the unit LSP positions use. */
export interface Span {
  readonly start: number;
  readonly end: number;
}

export interface Script extends Span {
  readonly kind: 'script';
  readonly statements: Statement[];
  /** Every comment, from the "#" to the end of its line. */
  readonly comments: Span[];
}

/**
 * One command line. The parser does not know which leading words are menu path and which is the command; it keeps every
 * word as an element and leaves that split to the checker, which has the command database.
 */
export interface Statement extends Span {
  readonly kind: 'statement';
  /** ':' for a global command, '/' for an absolute menu path, null when neither is written. */
  readonly prefix: ':' | '/' | null;
  readonly elements: Element[];
}

export type Element = Word | StringLit | Variable | Subst | Group | Brace | Named | Operator;

/** An unquoted word: a command, a menu name, a flag, a literal such as 10s or 1.1.1.1/24. */
export interface Word extends Span {
  readonly kind: 'word';
  readonly text: string;
}

export type StringPart =
  | { readonly kind: 'text'; readonly start: number; readonly end: number; readonly text: string }
  | { readonly kind: 'escape'; readonly start: number; readonly end: number; readonly text: string }
  | { readonly kind: 'variable'; readonly start: number; readonly end: number; readonly name: string }
  | { readonly kind: 'expression'; readonly start: number; readonly end: number; readonly group: Group }
  | { readonly kind: 'command'; readonly start: number; readonly end: number; readonly subst: Subst };

export interface StringLit extends Span {
  readonly kind: 'string';
  /** The text with escapes resolved and substitutions left out. */
  readonly value: string;
  readonly parts: StringPart[];
  readonly closed: boolean;
}

/** $name or $"quoted name". */
export interface Variable extends Span {
  readonly kind: 'variable';
  readonly name: string;
  readonly quoted: boolean;
}

/** [ command ] */
export interface Subst extends Span {
  readonly kind: 'subst';
  readonly body: Statement[];
  readonly closed: boolean;
}

/** ( expression ). Several expressions means operands were written next to each other, which RouterOS accepts. */
export interface Group extends Span {
  readonly kind: 'group';
  readonly exprs: Expr[];
  readonly closed: boolean;
}

/**
 * { ... } is a code block or an array literal and the syntax does not say which. `role` is 'block' where the position
 * makes it certain (a line of its own, a path block, the value of do= or else=) and 'unknown' otherwise.
 */
export interface Brace extends Span {
  readonly kind: 'brace';
  readonly body: Statement[];
  readonly role: 'block' | 'unknown';
  readonly closed: boolean;
}

/** name=value. The value is null when it is left out (name= at the end of a command). */
export interface Named extends Span {
  readonly kind: 'named';
  readonly name: Word | StringLit;
  /** Offset of the "=". */
  readonly equalsAt: number;
  readonly value: Element | null;
}

/** An "=" standing on its own, or any operator word where the expression language applies (after "where"). */
export interface Operator extends Span {
  readonly kind: 'operator';
  readonly op: string;
}

export type Operand = Word | StringLit | Variable | Subst | Group | Brace;

export interface Binary extends Span {
  readonly kind: 'binary';
  readonly op: string;
  readonly opStart: number;
  readonly left: Expr;
  readonly right: Expr;
}

export interface Unary extends Span {
  readonly kind: 'unary';
  readonly op: string;
  readonly operand: Expr;
}

/** Stands in for an operand that is missing, so the tree stays whole after an error. */
export interface Missing extends Span {
  readonly kind: 'missing';
}

export type Expr = Operand | Binary | Unary | Missing;

export type Node = Script | Statement | Element | Expr;
