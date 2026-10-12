import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { gunzipSync } from 'node:zlib';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

/** One argument of a command. Short keys keep the generated file small (see tools/gen_schema.py). */
export interface ArgInfo {
  /** description */
  readonly d?: string;
  /** type, as RouterOS describes it */
  readonly t?: string;
  /** known values */
  readonly e?: readonly string[];
  /** 1 when `e` is the complete list of accepted values */
  readonly x?: 1;
  /** 1 for a flag: it can be written without a value, like detail or count-only */
  readonly f?: 1;
}

export interface NodeInfo {
  readonly d?: string;
  /** 1 for a command, absent for a menu */
  readonly k?: 1;
  /** children of a menu */
  readonly c?: Readonly<Record<string, NodeInfo>>;
  /** arguments of a command */
  readonly a?: Readonly<Record<string, ArgInfo>>;
  /** arguments the command cannot be compiled without */
  readonly r?: readonly string[];
  /** how many unnamed arguments the command takes; 99 means more than three */
  readonly u?: number;
}

export interface SchemaData {
  readonly format: 1;
  readonly version: string;
  readonly board?: string;
  readonly architecture?: string;
  readonly packages?: readonly string[];
  readonly root: NodeInfo;
}

export type Match<T> =
  | { readonly kind: 'found'; readonly name: string; readonly value: T }
  | { readonly kind: 'ambiguous'; readonly candidates: string[] }
  | { readonly kind: 'none' };

/**
 * RouterOS accepts any unambiguous prefix of a menu, command or argument name (docs/ambiguities.md C-10). An exact match
 * wins even when it is also the prefix of a longer name.
 */
export function matchName<T>(table: Readonly<Record<string, T>> | undefined, word: string): Match<T> {
  if (!table || word === '') return { kind: 'none' };
  const exact = table[word];
  if (exact !== undefined && Object.prototype.hasOwnProperty.call(table, word)) return { kind: 'found', name: word, value: exact };
  const candidates = Object.keys(table).filter((name) => name.startsWith(word));
  if (candidates.length === 1) {
    const name = candidates[0]!;
    return { kind: 'found', name, value: table[name]! };
  }
  if (candidates.length > 1) return { kind: 'ambiguous', candidates: candidates.sort() };
  return { kind: 'none' };
}

/** Names close to `word`, for "did you mean". */
export function suggest(names: Iterable<string>, word: string, limit = 3): string[] {
  const scored: Array<{ name: string; score: number }> = [];
  for (const name of names) {
    const distance = editDistance(name, word);
    const prefixy = name.startsWith(word) || word.startsWith(name);
    const budget = Math.max(1, Math.floor(Math.max(name.length, word.length) / 4));
    if (distance <= budget || prefixy) scored.push({ name, score: prefixy ? distance - 1 : distance });
  }
  return scored.sort((a, b) => a.score - b.score || a.name.localeCompare(b.name)).slice(0, limit).map((s) => s.name);
}

function editDistance(a: string, b: string): number {
  if (Math.abs(a.length - b.length) > 4) return 99;
  let previous = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i++) {
    const row = [i];
    for (let j = 1; j <= b.length; j++) {
      row[j] = Math.min(previous[j]! + 1, row[j - 1]! + 1, previous[j - 1]! + (a[i - 1] === b[j - 1] ? 0 : 1));
    }
    previous = row;
  }
  return previous[b.length]!;
}

export class Schema {
  constructor(readonly data: SchemaData) {}

  get root(): NodeInfo {
    return this.data.root;
  }

  get version(): string {
    return this.data.version;
  }

  static fromJson(text: string): Schema {
    const data = JSON.parse(text) as SchemaData;
    if (data.format !== 1 || !data.root) throw new Error('not a routeros-lsp command database');
    return new Schema(data);
  }

  static fromFile(path: string): Schema {
    const bytes = readFileSync(path);
    const text = path.endsWith('.gz') ? gunzipSync(bytes).toString('utf8') : bytes.toString('utf8');
    return Schema.fromJson(text);
  }

  /** The command database that ships with the package: the newest file in data/. */
  static bundled(): Schema | null {
    const here = fileURLToPath(import.meta.url);
    for (const dir of [join(here, '..', '..', 'data'), join(here, '..', '..', '..', 'data'), join(here, '..', '..', '..', '..', 'data')]) {
      if (!existsSync(dir)) continue;
      const files = readdirSync(dir)
        .filter((f) => /^routeros-.*\.json(\.gz)?$/.test(f))
        .sort(compareVersions);
      const newest = files[files.length - 1];
      if (newest) return Schema.fromFile(join(dir, newest));
    }
    return null;
  }
}

function compareVersions(a: string, b: string): number {
  const parts = (s: string): number[] => (/routeros-([\d.]+)/.exec(s)?.[1] ?? '0').split('.').map(Number);
  const [pa, pb] = [parts(a), parts(b)];
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const d = (pa[i] ?? 0) - (pb[i] ?? 0);
    if (d !== 0) return d;
  }
  return 0;
}
