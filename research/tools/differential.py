"""Differential test: generates command lines from the command database, asks a router what it thinks of each, and
writes the answers to a JSON file that the checker is compared against (see research/README.md).

Usage:
    MIKROTIK_INVENTORY_FILE=... python research/tools/differential.py src/routeros_lsp/data/routeros-7.21.4.json.gz out.json [--device RouterA]

Every line is compiled with /import dry-run. Nothing is executed and nothing is changed on the router.
"""
import gzip
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tools"))
import logging

logging.disable(logging.CRITICAL)
import gen_schema  # noqa: E402

REJECT = gen_schema.REJECTED


def commands(node, path, out):
    if node.get("k"):
        out.append((tuple(path), node))
    for name, child in (node.get("c") or {}).items():
        commands(child, path + [name], out)


def value_for(arg):
    # a yes/no parameter is checked for its value when compiling; everything else takes any word
    return "yes" if arg.get("e") == ["no", "yes"] or arg.get("e") == ["yes", "no"] else "0"


def shortest_prefix(name, names):
    for n in range(1, len(name) + 1):
        if sum(1 for x in names if x.startswith(name[:n])) == 1:
            return name[:n]
    return name


def variants(path, node):
    args = node.get("a") or {}
    required = node.get("r") or []
    base = gen_schema.statement_for(path, "")
    req = [f"{r}={value_for(args.get(r, {}))}" for r in required]
    yield "required", " ".join([base] + req)
    optional = [(n, a) for n, a in args.items() if n not in required and not a.get("f") and n != "where"]
    if optional:
        n, a = optional[0]
        yield "optional", " ".join([base] + req + [f"{n}={value_for(a)}"])
    yield "unknown", " ".join([base] + req + ["zzznope=0"])
    if required:
        r = required[0]
        short = shortest_prefix(r, list(args))
        if short != r:
            rest = [x for x in req[1:]]
            yield "abbreviated", " ".join([base, f"{short}={value_for(args.get(r, {}))}"] + rest)
        yield "duplicate", " ".join([base] + req + [req[0]])
    flags = [n for n, a in args.items() if a.get("f")]
    if flags and not node.get("u"):
        yield "flag", " ".join([base] + req + [flags[0]])
        yield "flag-with-value", " ".join([base] + req + [f"{flags[0]}=yes"])


def main():
    schema_path, out_path = sys.argv[1], sys.argv[2]
    device = "RouterA"
    if "--device" in sys.argv:
        device = sys.argv[sys.argv.index("--device") + 1]
    data = json.load(gzip.open(schema_path, "rt", encoding="utf-8"))
    cmds = []
    commands(data["root"], [], cmds)

    lines = []
    for path, node in cmds:
        for kind, line in variants(path, node):
            lines.append((kind, line))
    print(len(lines), "lines from", len(cmds), "commands", file=sys.stderr)

    from mcp_mikrotik.inventory import _load_devices

    dev = next(d for d in _load_devices() if d.title == device)
    router = gen_schema.Router(dev.host, dev.port, dev.username, dev.password)
    answers = gen_schema.compile_lines(router, [line for _, line in lines], lambda m: print(m, file=sys.stderr, flush=True), "differential")
    result = [{"kind": k, "line": line, "ok": not any(REJECT.search(m) or m.startswith("Script Error") for m in msgs), "messages": msgs} for (k, line), msgs in zip(lines, answers)]
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f)
    ok = sum(1 for r in result if r["ok"])
    print(f"wrote {out_path}: {ok} accepted, {len(result) - ok} rejected", file=sys.stderr)


main()
