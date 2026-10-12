import type { RuleId } from '../rules.js';
import type {
  Binary,
  Brace,
  Element,
  Expr,
  Group,
  Named,
  Operand,
  Operator,
  Script,
  Span,
  Statement,
  StringLit,
  StringPart,
  Subst,
  Variable,
  Word,
} from './ast.js';

export interface SyntaxDiagnostic {
  readonly rule: RuleId;
  readonly message: string;
  readonly start: number;
  readonly end: number;
}

export interface ParseResult {
  readonly script: Script;
  readonly diagnostics: SyntaxDiagnostic[];
}

type Role = 'block' | 'unknown';

const MAX_DEPTH = 100;

/** Parameters whose braces hold commands. The value of any other name= is an array or a block, and the syntax cannot say which. */
const BLOCK_PARAMS = new Set(['do', 'else', 'on-error']);

const TWO_CHAR_OPS = ['&&', '||', '<<', '>>', '<=', '>=', '!=', '->', '<>'];
const ONE_CHAR_OPS = '+-*/%<>=~&|^.,';

/**
 * The documentation gives no precedence table. This is the order observed on RouterOS 7.21.4 (docs/ambiguities.md O-01):
 * "* / %" over "+ -" over "." over comparison, "&&" over "||". Placing the bitwise operators between "." and comparison
 * is a guess; it cannot change which scripts are valid, only how they are grouped.
 */
const PRECEDENCE: Record<string, number> = {
  '||': 1,
  or: 1,
  '&&': 2,
  and: 2,
  '=': 3,
  '!=': 3,
  '<>': 3,
  '<': 3,
  '>': 3,
  '<=': 3,
  '>=': 3,
  '~': 3,
  in: 3,
  '|': 4,
  '^': 4,
  '&': 4,
  '<<': 4,
  '>>': 4,
  '.': 5,
  ',': 5,
  '+': 6,
  '-': 6,
  '*': 7,
  '/': 7,
  '%': 7,
  '->': 8,
};

const SIMPLE_ESCAPES: Record<string, string> = {
  '"': '"',
  '\\': '\\',
  n: '\n',
  r: '\r',
  t: '\t',
  $: '$',
  _: ' ',
  a: '\x07',
  b: '\b',
  // The documentation says 0xFF; RouterOS 7.21.4 produces 0x0C (docs/ambiguities.md E-01).
  f: '\f',
  v: '\v',
  // Documented as removed in 7.1rc2, still accepted (E-02).
  '?': '?',
};

/** Characters that end a bare word. Everything else, including # ~ ! < | & + * % ^ - . , / : and @, belongs to it. */
const NON_WORD = new Set([' ', '\t', '\n', '\r', ';', '"', '$', '[', ']', '(', ')', '{', '}', '=', '\\', '?', "'", '`']);

function isEol(c: string): boolean {
  return c === '\n' || c === '\r';
}

function isAlnum(c: string): boolean {
  return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z');
}

function isUpperHex(c: string): boolean {
  return (c >= '0' && c <= '9') || (c >= 'A' && c <= 'F');
}

function isWordChar(c: string): boolean {
  return c !== '' && c.charCodeAt(0) < 0x80 && !NON_WORD.has(c);
}

function isAtomStart(c: string): boolean {
  return isAlnum(c) || c === '_' || c === '.' || c === ':';
}

function isAtomChar(c: string): boolean {
  return isAtomStart(c) || c === '/';
}

function printable(c: string): string {
  return c === '' ? 'the end of the file' : isEol(c) ? 'the end of the line' : `'${c}'`;
}

export function parse(text: string): ParseResult {
  return new Parser(text).run();
}

class Parser {
  private pos = 0;
  private depth = 0;
  /** Closers of the constructs currently open, innermost last. Lets a missing closer be told apart from a stray one. */
  private readonly closers: string[] = [];
  private readonly found: SyntaxDiagnostic[] = [];
  private readonly comments: Span[] = [];

  constructor(private readonly text: string) {}

  run(): ParseResult {
    if (this.text.charCodeAt(0) === 0xfeff) {
      this.report('syntax/bom', 'The file starts with a byte order mark, which RouterOS rejects. Save it as UTF-8 without BOM.', 0, 1);
      this.pos = 1;
    }
    const { body } = this.parseStatements(null, 'block');
    const script: Script = { kind: 'script', start: 0, end: this.text.length, statements: body, comments: this.comments };
    return { script, diagnostics: this.finish() };
  }

  private finish(): SyntaxDiagnostic[] {
    const seen = new Set<string>();
    const unique: SyntaxDiagnostic[] = [];
    for (const d of this.found) {
      const key = `${d.rule}:${d.start}:${d.end}`;
      if (!seen.has(key)) {
        seen.add(key);
        unique.push(d);
      }
    }
    return unique.sort((a, b) => a.start - b.start || a.end - b.end);
  }

  private report(rule: RuleId, message: string, start: number, end: number): void {
    this.found.push({ rule, message, start, end });
  }

  private peek(offset = 0): string {
    return this.text.charAt(this.pos + offset);
  }

  private atStatementEnd(): boolean {
    const c = this.peek();
    return c === '' || c === ';' || isEol(c) || c === '}' || c === ']' || c === ')';
  }

  /** Index just past the line break that starts at p (CR LF counts as one). */
  private afterEol(p: number): number {
    return this.text[p] === '\r' && this.text[p + 1] === '\n' ? p + 2 : p + 1;
  }

  private skipToEol(): void {
    while (this.pos < this.text.length && !isEol(this.text[this.pos]!)) this.pos++;
  }

  private skipComment(): void {
    const start = this.pos;
    this.skipToEol();
    // A comment can be reached twice when the parser backs up after an omitted value; positions only ever grow.
    const last = this.comments[this.comments.length - 1];
    if (!last || last.start < start) this.comments.push({ start, end: this.pos });
  }

  /**
   * Skips spaces, tabs and line joins (a backslash before the line break). Returns true when anything was skipped.
   * A backslash that does not end the line is ignored by RouterOS although the documentation calls it illegal (L-03).
   */
  private skipInline(): boolean {
    const from = this.pos;
    for (;;) {
      const c = this.peek();
      if (c === ' ' || c === '\t') {
        this.pos++;
      } else if (c === '\\') {
        let p = this.pos + 1;
        while (this.text[p] === ' ' || this.text[p] === '\t') p++;
        if (p >= this.text.length) {
          this.pos = p;
        } else if (isEol(this.text[p]!)) {
          this.pos = this.afterEol(p);
          // A line that starts with # right after a join is a comment line (docs/ambiguities.md L-01, probe z30).
          if (this.peek() === '#') this.skipComment();
        } else {
          this.report('syntax/stray-backslash', 'A backslash is only valid at the end of a line or inside a string. RouterOS ignores it here.', this.pos, this.pos + 1);
          this.pos++;
        }
      } else {
        break;
      }
    }
    return this.pos > from;
  }

  /** Skips whatever can sit between commands: blank space, line breaks, ";" and comments. */
  private skipSeparators(): void {
    for (;;) {
      if (this.skipInline()) continue;
      const c = this.peek();
      if (c === ';' || isEol(c)) {
        this.pos++;
      } else if (c === '#') {
        this.skipComment();
      } else {
        return;
      }
    }
  }

  // ---------------------------------------------------------------------------------------------------------------
  // Statements

  private parseStatements(closer: ')' | ']' | '}' | null, role: Role): { body: Statement[]; closed: boolean } {
    const body: Statement[] = [];
    for (;;) {
      this.skipSeparators();
      if (this.pos >= this.text.length) return { body, closed: false };
      const c = this.peek();
      if (c === closer) return { body, closed: true };
      if (c === ')' || c === ']' || c === '}') {
        if (this.closers.includes(c)) return { body, closed: false };
        this.strayCloser(c);
        continue;
      }
      body.push(this.parseStatement(role));
    }
  }

  private strayCloser(c: string): void {
    if (c === ')') {
      this.report('syntax/unexpected-closer', "This ')' has no matching '('.", this.pos, this.pos + 1);
    } else {
      this.report('syntax/stray-closer', `This '${c}' has no matching '${c === '}' ? '{' : '['}'. RouterOS accepts it, but it is almost certainly a mistake.`, this.pos, this.pos + 1);
    }
    this.pos++;
  }

  private parseStatement(role: Role): Statement {
    const start = this.pos;
    let prefix: ':' | '/' | null = null;
    const first = this.peek();
    if (first === ':' || first === '/') {
      prefix = first;
      this.pos++;
      this.skipInline();
      // A lone ':' is accepted and does nothing.
      if (prefix === ':' && this.peek() === ':') {
        this.report('syntax/expected-command', "Expected a command name after ':'.", this.pos, this.pos + 1);
      }
    }

    const elements: Element[] = [];
    let end = this.pos;
    let where = false;
    for (;;) {
      const spaced = this.skipInline();
      if (this.atStatementEnd()) break;
      const at = this.pos;
      const c = this.peek();
      const prev = elements[elements.length - 1];

      // After "where" the expression language applies and operators sit next to values (where address~"x").
      if (!spaced && prev && !where && prev.kind !== 'operator') this.checkAdjacent(prev, at, c);

      let el: Element | null = null;
      switch (c) {
        case '"':
          el = this.parseStringOrKey();
          break;
        case '$':
          el = this.parseVariable();
          break;
        case '[':
          el = this.parseSubst();
          break;
        case '(':
          el = this.parseGroup();
          break;
        case '{':
          // A brace on a line of its own holds commands. Anywhere else the syntax cannot tell a block from an array.
          el = this.parseBrace(elements.length === 0 && prefix === null ? 'block' : 'unknown');
          break;
        case '=':
          el = this.parseLooseEquals(spaced, where);
          break;
        default:
          if (isWordChar(c)) el = this.parseWordOrNamed();
          else this.invalidCharacter();
      }
      end = this.pos;
      if (!el) continue;

      if (el.kind === 'word' && elements.length > 0) this.checkWordPosition(el);
      if (el.kind === 'word' && el.text === 'where' && elements.length > 0) where = true;
      elements.push(el);
    }

    const head = elements[0];
    if (role === 'block' && head) this.checkStatementHead(head, prefix);
    return { kind: 'statement', start, end, prefix, elements };
  }

  private checkAdjacent(prev: Element, at: number, c: string): void {
    if (c !== '"' && c !== '$' && c !== '[' && c !== '(' && c !== '{' && !isWordChar(c)) return;
    let message = 'Put a space before this. RouterOS needs whitespace between values.';
    if (prev.kind === 'variable' && !prev.quoted && (c === '_' || c === '-')) {
      message = `A variable name ends at the first character that is not a letter or digit. Quote the name to include '${c}': $"${prev.name}${c}...".`;
    }
    this.report('syntax/adjacent-tokens', message, at, at + 1);
  }

  private checkWordPosition(word: Word): void {
    if (word.text.startsWith('#')) {
      this.report(
        'syntax/trailing-comment',
        "A '#' only starts a comment at the beginning of a command. Here RouterOS reads it as an argument and the line fails with 'expected end of command'. Put ';' before the comment.",
        word.start,
        word.start + 1,
      );
    } else if (/^:[A-Za-z]/.test(word.text)) {
      this.report('syntax/missing-separator', `'${word.text}' looks like the start of another command. Separate commands with ';' or a line break.`, word.start, word.end);
    }
  }

  private checkStatementHead(head: Element, prefix: ':' | '/' | null): void {
    if (head.kind === 'named') {
      this.reportPairStatement(head);
    } else if (head.kind === 'string' && prefix === null) {
      this.report('syntax/expected-command', 'A command name is expected here, not a string.', head.start, head.start + 1);
    } else if (head.kind === 'word' && prefix === null && /^[!,~*]/.test(head.text)) {
      this.report('syntax/expected-command', `A command name is expected here. A command cannot start with '${head.text[0]}'.`, head.start, head.start + 1);
    } else if (head.kind === 'word' && /[A-Z]/.test(head.text)) {
      this.report('syntax/expected-command', `Command and menu names are lowercase, '${head.text}' is not accepted.`, head.start, head.end);
    }
  }

  private reportPairStatement(head: Named): void {
    const name = head.name.kind === 'word' ? head.name.text : head.name.value;
    const continuation = ['else', 'do', 'while', 'on-error', 'in'].includes(name);
    const message = continuation
      ? `'${name}=' cannot start a command line. Keep it on the same line as the closing brace of the command it belongs to, or end the previous line with a backslash.`
      : `'${name}=...' cannot start a command line: a command name is expected here. Inside braces, name=value is only valid in an array.`;
    this.report('syntax/statement-starts-with-pair', message, head.equalsAt, head.equalsAt + 1);
  }

  /** Reports and skips the character at the cursor, which cannot start or continue a bare word. */
  private invalidCharacter(): void {
    const c = this.peek();
    const code = c.charCodeAt(0);
    const width = code >= 0xd800 && code <= 0xdbff && this.peek(1) !== '' ? 2 : 1;
    const shown = this.text.slice(this.pos, this.pos + width);
    let message = `The character '${shown}' is not accepted outside a string. Put the value in double quotes.`;
    if (c === "'") message = 'Single quotes do not quote a string in RouterOS. Use double quotes.';
    else if (code >= 0x80) message = `Non-ASCII characters such as '${shown}' are only accepted inside double quotes or in a comment.`;
    this.report('syntax/invalid-character', message, this.pos, this.pos + width);
    this.pos += width;
  }

  // ---------------------------------------------------------------------------------------------------------------
  // Elements

  private parseWordOrNamed(): Word | Named {
    const start = this.pos;
    while (isWordChar(this.peek())) this.pos++;
    const word: Word = { kind: 'word', start, end: this.pos, text: this.text.slice(start, this.pos) };
    return this.peek() === '=' ? this.finishNamed(word) : word;
  }

  private parseStringOrKey(): StringLit | Named {
    const str = this.parseString();
    return this.peek() === '=' ? this.finishNamed(str) : str;
  }

  private finishNamed(name: Word | StringLit): Named {
    const equalsAt = this.pos;
    this.pos++;
    const afterEquals = this.pos;
    // A space after "=" is accepted: the documentation's own correct example writes "from= 1".
    this.skipInline();
    let value: Element | null = null;
    if (!this.atStatementEnd()) {
      const key = name.kind === 'word' ? name.text : name.value;
      value = this.parseOperand(BLOCK_PARAMS.has(key) ? 'block' : 'unknown');
    }
    if (!value) this.pos = afterEquals;
    return { kind: 'named', start: name.start, end: value ? value.end : afterEquals, name, equalsAt, value };
  }

  /** A value: what follows name= or sits in an argument position. */
  private parseOperand(braceRole: Role): Element | null {
    switch (this.peek()) {
      case '"':
        return this.parseString();
      case '$':
        return this.parseVariable();
      case '[':
        return this.parseSubst();
      case '(':
        return this.parseGroup();
      case '{':
        return this.parseBrace(braceRole);
      case '=':
        return this.parseLooseEquals(false, false);
      default: {
        const start = this.pos;
        while (isWordChar(this.peek())) this.pos++;
        if (this.pos === start) {
          this.invalidCharacter();
          return null;
        }
        return { kind: 'word', start, end: this.pos, text: this.text.slice(start, this.pos) };
      }
    }
  }

  private parseLooseEquals(spaced: boolean, where: boolean): Operator {
    const start = this.pos;
    this.pos++;
    if (!where) {
      if (spaced) {
        this.report('syntax/space-before-equals', "Remove the space before '='. Parameters are written name=value.", start, start + 1);
      } else {
        this.report('syntax/unexpected-equals', "Unexpected '='. A parameter value cannot contain '='; put the value in double quotes.", start, start + 1);
      }
    }
    return { kind: 'operator', start, end: this.pos, op: '=' };
  }

  // ---------------------------------------------------------------------------------------------------------------
  // Strings and variables

  private parseString(): StringLit {
    const start = this.pos;
    this.pos++;
    const parts: StringPart[] = [];
    let value = '';
    let textStart = this.pos;
    let closed = false;
    const flush = (end: number): void => {
      if (end > textStart) {
        const text = this.text.slice(textStart, end);
        parts.push({ kind: 'text', start: textStart, end, text });
        value += text;
      }
    };
    while (this.pos < this.text.length) {
      const c = this.text[this.pos]!;
      if (c === '"') {
        flush(this.pos);
        this.pos++;
        closed = true;
        break;
      }
      if (c === '\\') {
        flush(this.pos);
        value += this.parseEscape(parts);
        textStart = this.pos;
      } else if (c === '$') {
        flush(this.pos);
        this.parseInterpolation(parts);
        textStart = this.pos;
      } else {
        this.pos++;
      }
    }
    if (!closed) {
      flush(this.pos);
      this.report('syntax/unterminated-string', 'This string is never closed. Add the closing double quote.', start, start + 1);
    }
    return { kind: 'string', start, end: this.pos, value, parts, closed };
  }

  /** Returns the text the escape stands for. */
  private parseEscape(parts: StringPart[]): string {
    const start = this.pos;
    const n = this.text.charAt(start + 1);
    if (n === '') {
      this.pos++;
      return '';
    }
    if (isEol(n)) {
      // Backslash, line break and the next line's leading whitespace vanish together (docs/ambiguities.md L-04).
      let p = this.afterEol(start + 1);
      while (this.text[p] === ' ' || this.text[p] === '\t') p++;
      this.pos = p;
      parts.push({ kind: 'escape', start, end: p, text: '' });
      return '';
    }
    const simple = SIMPLE_ESCAPES[n];
    if (simple !== undefined) {
      this.pos = start + 2;
      parts.push({ kind: 'escape', start, end: this.pos, text: simple });
      return simple;
    }
    const n2 = this.text.charAt(start + 2);
    if (isUpperHex(n) && isUpperHex(n2)) {
      this.pos = start + 3;
      const text = String.fromCharCode(parseInt(n + n2, 16));
      parts.push({ kind: 'escape', start, end: this.pos, text });
      return text;
    }
    const hexLike = /[0-9a-fA-F]/.test(n) && /[0-9a-fA-F]/.test(n2);
    this.report(
      'syntax/invalid-escape',
      hexLike
        ? `Invalid escape '\\${n}${n2}'. A hexadecimal escape is a backslash and two digits written with capital letters, for example \\4F.`
        : `Invalid escape '\\${n}'. The valid escapes are \\" \\\\ \\n \\r \\t \\$ \\_ \\a \\b \\f \\v and \\ followed by two capital hex digits.`,
      start,
      start + 2,
    );
    this.pos = start + 2;
    return '';
  }

  private parseInterpolation(parts: StringPart[]): void {
    const start = this.pos;
    const n = this.peek(1);
    if (n === '(') {
      this.pos++;
      const group = this.parseGroup();
      parts.push({ kind: 'expression', start, end: this.pos, group });
    } else if (n === '[') {
      this.pos++;
      const subst = this.parseSubst();
      parts.push({ kind: 'command', start, end: this.pos, subst });
    } else if (isAlnum(n)) {
      this.pos++;
      const nameStart = this.pos;
      while (isAlnum(this.peek())) this.pos++;
      parts.push({ kind: 'variable', start, end: this.pos, name: this.text.slice(nameStart, this.pos) });
    } else {
      this.report(
        'syntax/bad-interpolation',
        "A '$' in a string must be followed by a variable name, '(' or '['. Write \\$ for a literal dollar sign.",
        start,
        start + 1,
      );
      this.pos++;
    }
  }

  /** $name, $"quoted name". Recovers from $( and $[ outside a string by parsing the group or command. */
  private parseVariable(): Variable | Group | Subst {
    const start = this.pos;
    const n = this.peek(1);
    if (n === '"') {
      this.pos++;
      const str = this.parseString();
      return { kind: 'variable', start, end: this.pos, name: str.value, quoted: true };
    }
    if (isAlnum(n)) {
      this.pos++;
      const nameStart = this.pos;
      while (isAlnum(this.peek())) this.pos++;
      return { kind: 'variable', start, end: this.pos, name: this.text.slice(nameStart, this.pos), quoted: false };
    }
    if (n === '(' || n === '[') {
      this.report(
        'syntax/dollar-expression-outside-string',
        `'$${n}' is only valid inside a string. Outside a string write ${n === '(' ? '(expression)' : '[command]'} without the '$'.`,
        start,
        start + 1,
      );
      this.pos++;
      return n === '(' ? this.parseGroup() : this.parseSubst();
    }
    this.report('syntax/bare-dollar', `Expected a variable name after '$', found ${printable(n)}.`, start, start + 1);
    this.pos++;
    return { kind: 'variable', start, end: this.pos, name: '', quoted: false };
  }

  // ---------------------------------------------------------------------------------------------------------------
  // Brackets

  private tooDeep(start: number): void {
    this.report('syntax/too-deeply-nested', 'Brackets are nested too deeply to analyse the rest of the file.', start, start + 1);
    this.pos = this.text.length;
  }

  private parseSubst(): Subst {
    const start = this.pos;
    if (this.depth >= MAX_DEPTH) {
      this.tooDeep(start);
      return { kind: 'subst', start, end: this.pos, body: [], closed: true };
    }
    this.pos++;
    this.depth++;
    this.closers.push(']');
    const { body, closed } = this.parseStatements(']', 'block');
    this.closers.pop();
    this.depth--;
    if (closed) this.pos++;
    else this.report('syntax/missing-closer', "Missing ']' for this '['.", start, start + 1);
    return { kind: 'subst', start, end: this.pos, body, closed };
  }

  private parseBrace(role: Role): Brace {
    const start = this.pos;
    if (this.depth >= MAX_DEPTH) {
      this.tooDeep(start);
      return { kind: 'brace', start, end: this.pos, body: [], role, closed: true };
    }
    this.pos++;
    this.depth++;
    this.closers.push('}');
    const { body, closed } = this.parseStatements('}', role);
    this.closers.pop();
    this.depth--;
    if (closed) this.pos++;
    else this.report('syntax/missing-closer', "Missing '}' for this '{'.", start, start + 1);
    return { kind: 'brace', start, end: this.pos, body, role, closed };
  }

  private parseGroup(): Group {
    const start = this.pos;
    if (this.depth >= MAX_DEPTH) {
      this.tooDeep(start);
      return { kind: 'group', start, end: this.pos, exprs: [], closed: true };
    }
    this.pos++;
    this.depth++;
    this.closers.push(')');
    const exprs = this.parseExprSeq();
    this.closers.pop();
    this.depth--;
    const closed = this.peek() === ')';
    if (closed) {
      this.pos++;
      if (exprs.length === 0) this.report('syntax/empty-expression', 'This group is empty. Put an expression between the parentheses.', start, this.pos);
    } else {
      this.report('syntax/missing-closer', "Missing ')' for this '('.", start, start + 1);
    }
    return { kind: 'group', start, end: this.pos, exprs, closed };
  }

  // ---------------------------------------------------------------------------------------------------------------
  // Expressions, inside ( )

  /** Whitespace inside an expression. A bare line break is an error; a backslash join is fine. */
  private skipExprSpace(): void {
    for (;;) {
      this.skipInline();
      const c = this.peek();
      if (!isEol(c)) return;
      this.report('syntax/newline-in-parens', "A line break is not allowed inside '( )'. End the line with a backslash to continue it.", this.pos, this.pos + 1);
      this.pos = this.afterEol(this.pos);
    }
  }

  private parseExprSeq(): Expr[] {
    const exprs: Expr[] = [];
    for (;;) {
      this.skipExprSpace();
      const c = this.peek();
      if (c === '' || c === ')') break;
      if ((c === ']' || c === '}') && this.closers.includes(c)) break;
      if (c === ';' || c === ']' || c === '}') {
        this.report('syntax/unexpected-token', `'${c}' cannot appear inside '( )'.`, this.pos, this.pos + 1);
        this.pos++;
        continue;
      }
      const before = this.pos;
      // Operands written next to each other are accepted by RouterOS, so each one is simply the next expression.
      exprs.push(this.parseExpr(0));
      if (this.pos === before) this.pos++;
    }
    return exprs;
  }

  private parseExpr(minPrec: number): Expr {
    let left = this.parseUnary();
    for (;;) {
      this.skipExprSpace();
      const op = this.peekBinary();
      if (!op || op.prec < minPrec) return left;
      const opStart = this.pos;
      this.pos += op.len;
      const right = this.parseOperandAfter(op.text, opStart, op.prec + 1);
      const binary: Binary = {
        kind: 'binary',
        op: op.text,
        opStart,
        start: left.start,
        end: Math.max(right.end, opStart + op.len),
        left,
        right,
      };
      left = binary;
    }
  }

  private parseOperandAfter(op: string, opStart: number, prec: number): Expr {
    this.skipExprSpace();
    const c = this.peek();
    if (c === '' || c === ')' || c === ';' || ((c === ']' || c === '}') && this.closers.includes(c))) {
      this.report('syntax/expected-operand', `Expected a value after '${op}'.`, opStart, opStart + op.length);
      return { kind: 'missing', start: this.pos, end: this.pos };
    }
    return this.parseExpr(prec);
  }

  private parseUnary(): Expr {
    this.skipExprSpace();
    const c = this.peek();
    if (c === '-' || c === '!' || c === '~') {
      const start = this.pos;
      this.pos++;
      const operand = this.parseOperandAfter(c, start, 9);
      return { kind: 'unary', op: c, start, end: Math.max(operand.end, start + 1), operand };
    }
    return this.parsePrimary();
  }

  private parsePrimary(): Expr {
    const c = this.peek();
    let operand: Operand;
    switch (c) {
      case '$':
        operand = this.parseVariable();
        break;
      case '"':
        operand = this.parseString();
        break;
      case '[':
        operand = this.parseSubst();
        break;
      case '(':
        operand = this.parseGroup();
        break;
      case '{':
        operand = this.parseBrace('unknown');
        break;
      default: {
        if (!isAtomStart(c)) {
          this.report('syntax/expected-operand', `Expected a value here, found ${printable(c)}.`, this.pos, this.pos + (c === '' ? 0 : 1));
          return { kind: 'missing', start: this.pos, end: this.pos };
        }
        const start = this.pos;
        while (isAtomChar(this.peek())) this.pos++;
        operand = { kind: 'word', start, end: this.pos, text: this.text.slice(start, this.pos) };
      }
    }
    return operand;
  }

  private peekBinary(): { text: string; len: number; prec: number } | null {
    const c = this.peek();
    if (c === '') return null;
    const two = this.text.substr(this.pos, 2);
    if (TWO_CHAR_OPS.includes(two)) return { text: two, len: 2, prec: PRECEDENCE[two]! };
    if (ONE_CHAR_OPS.includes(c)) return { text: c, len: 1, prec: PRECEDENCE[c]! };
    if (c === 'a' || c === 'o' || c === 'i') {
      const m = /^(and|or|in)(?![A-Za-z0-9_])/.exec(this.text.slice(this.pos, this.pos + 4));
      if (m) return { text: m[1]!, len: m[1]!.length, prec: PRECEDENCE[m[1]!]! };
    }
    return null;
  }
}
