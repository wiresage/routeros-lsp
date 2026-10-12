import type { BindResult, Declaration, Scope } from './binder.js';

/** The innermost scope that covers the offset. */
export function scopeAt(bound: BindResult, offset: number): Scope | null {
  let best: Scope | null = null;
  for (const scope of bound.scopes) {
    if (offset < scope.start || offset > scope.end) continue;
    if (!best || scope.end - scope.start <= best.end - best.start) best = scope;
  }
  return best;
}

/**
 * The variables a command at `offset` can read: those declared before it in the scopes around it, up to the edge of a
 * function body (which only sees its own), and every global declared earlier in the file, which RouterOS finds by name.
 */
export function variablesAt(bound: BindResult, offset: number): Declaration[] {
  const found = new Map<string, Declaration>();
  const chain = new Set<Scope>();
  let crossed = false;
  const crossedAt = new Map<Scope, boolean>();
  for (let s = scopeAt(bound, offset); s; s = s.parent) {
    chain.add(s);
    crossedAt.set(s, crossed);
    if (s.kind === 'function') crossed = true;
  }
  for (const d of bound.declarations) {
    if (d.from > offset) continue;
    const inChain = chain.has(d.scope);
    const visible = inChain ? !crossedAt.get(d.scope) || d.kind === 'global' : d.kind === 'global';
    if (visible) found.set(d.name, d);
  }
  return [...found.values()].sort((a, b) => a.name.localeCompare(b.name));
}
