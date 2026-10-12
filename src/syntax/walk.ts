import type { Node } from './ast.js';

/** The direct children of a node, in source order. */
export function children(node: Node): Node[] {
  switch (node.kind) {
    case 'script':
      return node.statements;
    case 'statement':
      return node.elements;
    case 'string':
      return node.parts.flatMap<Node>((part) => (part.kind === 'expression' ? [part.group] : part.kind === 'command' ? [part.subst] : []));
    case 'subst':
    case 'brace':
      return node.body;
    case 'group':
      return node.exprs;
    case 'named':
      return node.value ? [node.name, node.value] : [node.name];
    case 'binary':
      return [node.left, node.right];
    case 'unary':
      return [node.operand];
    default:
      return [];
  }
}

/** Depth-first walk. Return false from the callback to skip a node's children. */
export function visit(node: Node, callback: (node: Node, parent: Node | null) => boolean | void, parent: Node | null = null): void {
  if (callback(node, parent) === false) return;
  for (const child of children(node)) visit(child, callback, node);
}

/**
 * The nodes that contain `offset`, outermost first. An offset on the boundary between two nodes counts for both, so a
 * caret right after a word is inside that word.
 */
export function ancestorsAt(root: Node, offset: number): Node[] {
  const chain: Node[] = [];
  let node: Node | undefined = root;
  while (node) {
    chain.push(node);
    node = children(node).find((child) => child.start <= offset && offset <= child.end && child.kind !== 'missing');
  }
  return chain;
}
