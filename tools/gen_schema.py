#!/usr/bin/env python3
"""Generates the command database from a RouterOS device.

Reads the command tree, descriptions, argument types and enumerations through /console/inspect, and learns which
arguments are required and how many unnamed arguments a command takes by compiling probe scripts with
`/import ... dry-run`. Nothing is executed on the device and its configuration is not changed; the only file it writes
there is `lspgen.rsc`, which it removes again.

Usage:
    ROUTEROS_PASSWORD=... python tools/gen_schema.py --host 192.0.2.1 --user admin --out data/routeros-7.21.4.json.gz

Needs `pip install paramiko`. The device decides what is in the database: menus of packages that are not installed
(wireless, LTE ...) and parameters that only some hardware has are missing. Generate the file from your own device to
get yours.
"""
import argparse
import gzip
import json
import os
import re
import sys
import time

import paramiko

NL = chr(10)
CR = chr(13)
LINE = re.compile(r"^#line (\d+)$")
MISSING = re.compile(r"missing value(?:\(s\))? of argument(?:\(s\))? (.*)$")
REJECTED = re.compile(r"expected end of command|syntax error")
CHUNK = 250


class Router:
    def __init__(self, host, port, user, password):
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.client.connect(host, port=port, username=user, password=password, look_for_keys=False, allow_agent=False, timeout=30)
        self.sftp = self.client.open_sftp()

    def run(self, command, timeout=600):
        _, out, err = self.client.exec_command(command, timeout=timeout)
        return (out.read().decode("utf-8", "replace") + err.read().decode("utf-8", "replace")).replace(CR, "")

    def script(self, text, args="", timeout=1800):
        """Uploads `text` as a script and imports it; returns what it printed."""
        with self.sftp.open("lspgen.rsc", "wb") as f:
            f.write(text.encode("utf-8"))
        try:
            return self.run("/import file-name=lspgen.rsc " + args, timeout=timeout)
        finally:
            self.run('/file remove [find name="lspgen.rsc"]')


def quote(path):
    return '"' + ",".join(path) + '"'


def chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i : i + size]


# ---------------------------------------------------------------------------------------------------------------------
# Phase 1: the tree


def walk_tree(router, log):
    """Breadth first, one script per level. Returns ({path: [(name, node-type), ...]}, {path: node-type})."""
    tree = {}
    kinds = {}
    level = [()]
    depth = 0
    while level:
        depth += 1
        found = []
        for batch in chunks(level, 400):
            if batch == [()]:
                body = ':foreach c in=[/console/inspect as-value request=child] do={ :if (($c->"type") = "child") do={ :put ("N||" . ($c->"name") . "|" . ($c->"node-type")) } }'
            else:
                body = (
                    ":foreach p in={ " + "; ".join(quote(p) for p in batch) + " } do={ "
                    ':foreach c in=[/console/inspect as-value request=child path=$p] do={ '
                    ':if (($c->"type") = "child") do={ :put ("N|" . $p . "|" . ($c->"name") . "|" . ($c->"node-type")) } } }'
                )
            for line in router.script(body).split(NL):
                if line.startswith("N|"):
                    _, path, name, kind = line.split("|", 3)
                    found.append((tuple(path.split(",")) if path else (), name, kind.strip()))
        nxt = []
        for path, name, kind in found:
            if not path and name == "root":
                continue
            tree.setdefault(path, []).append((name, kind))
            kinds[path + (name,)] = kind
            # commands are visited too: their children are the arguments
            if kind in ("dir", "path", "cmd") and len(path) < 12:
                nxt.append(path + (name,))
        for p in nxt:
            tree.setdefault(p, [])
        level = nxt
        log(f"level {depth}: {len(found)} nodes, {len(level)} to visit")
    return tree, kinds


# ---------------------------------------------------------------------------------------------------------------------
# Phase 2 and 3: descriptions, types, enumerations


def inspect_many(router, request, paths, tag, log):
    """Runs /console/inspect for each path; returns {path tuple: parsed json}."""
    results = {}
    for n, batch in enumerate(chunks(paths, CHUNK)):
        body = (
            ":foreach p in={ " + "; ".join(quote(p) for p in batch) + " } do={ "
            ":local r [/console/inspect as-value request=" + request + " path=$p]; "
            ':put ("' + tag + '|" . $p . "|" . [:serialize to=json $r]) }'
        )
        if batch == [()]:
            body = (
                ":local r [/console/inspect as-value request=" + request + "]; "
                ':put ("' + tag + '||" . [:serialize to=json $r])'
            )
        for line in router.script(body).split(NL):
            if line.startswith(tag + "|"):
                _, path, payload = line.split("|", 2)
                try:
                    results[tuple(path.split(",")) if path else ()] = json.loads(payload)
                except json.JSONDecodeError:
                    pass
        if n % 10 == 0:
            log(f"{request}: {min((n + 1) * CHUNK, len(paths))}/{len(paths)}")
    return results


def as_list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def describe_children(syntax):
    """From a dir or command syntax reply: {child or argument name: description}."""
    out = {}
    for item in as_list(syntax):
        if item.get("symbol-type") == "explanation" and item.get("nested") == 1 and item.get("symbol"):
            name = str(item["symbol"]).strip("<>")
            if item.get("text"):
                out[name] = str(item["text"])
    return out


SIMPLE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+_-]*$")
FILE_NAME = re.compile(r"\.[A-Za-z0-9]{2,4}$|/$")


def dynamic_names(router):
    """Names of interfaces, files and users on this router. Lists of values that include one of them depend on this router
    and are left out of the database. (Names such as "all" and "none" also appear in the configuration but are fixed
    words in other lists, so only these three kinds are collected.)"""
    names = set()
    for command in (
        ':foreach i in=[/interface find] do={ :put [/interface get $i name]; :put [/interface get $i default-name] }',
        ':foreach i in=[/file find] do={ :put [/file get $i name] }',
        ':foreach i in=[/user find] do={ :put [/user get $i name] }',
    ):
        names.update(x.strip() for x in router.run(command).split(NL) if x.strip())
    return names


def depends_on_router(values, dynamic):
    return any(v in dynamic or FILE_NAME.search(v) for v in values) or len(values) > 80


def parse_type(syntax):
    """From an argument syntax reply: (type text, [enum values from the syntax])."""
    items = as_list(syntax)
    texts = []
    enums = []
    for item in items:
        text = " ".join(str(item.get("text") or "").split())
        kind = item.get("symbol-type")
        if kind == "definition" and text and len(texts) < 3:
            texts.append(text)
            if "|" in text:
                parts = [p.strip() for p in re.split(r"[|,\[\]*]", text) if p.strip() and p.strip() != "..."]
                if parts and all(SIMPLE.match(p) for p in parts):
                    enums.extend(parts)
        elif kind == "explanation" and (item.get("nested") or 0) >= 3 and item.get("symbol") and SIMPLE.match(str(item["symbol"])):
            enums.append(str(item["symbol"]))
    if not texts and items:
        symbol = str(items[0].get("symbol") or "").strip()
        if symbol:
            texts.append(symbol)
        elif items[0].get("text"):
            texts.append(" ".join(str(items[0]["text"]).split()))
    seen = []
    for e in enums:
        if e not in seen:
            seen.append(e)
    return "; ".join(texts)[:200], seen[:200]


def parse_completion(reply):
    """From a completion reply: (values, closed). `closed` means the values are all there is; an entry that stands for
    "any value", "any number" or "an item id" makes the list a set of suggestions."""
    values = []
    open_ended = False
    for item in as_list(reply):
        text = str(item.get("completion", ""))
        if item.get("style") == "syntax-meta":
            continue
        if text == "*" or (text.startswith("<") and text.endswith(">")):
            open_ended = True
        elif (item.get("preference") or 0) > 0 and text:
            values.append(text)
    return values[:200], bool(values) and not open_ended


# ---------------------------------------------------------------------------------------------------------------------
# Phase 4: required and unnamed arguments, by compiling probe scripts


def statement_for(path, suffix):
    base = (":" + path[0]) if len(path) == 1 else "/" + " ".join(path)
    return base + (" " + suffix if suffix else "")


SUMMARY = re.compile(r"found (\d+) error")


def compile_lines(router, lines, log, label):
    """Compiles each line with /import dry-run and returns the messages printed for it, one list per line.

    RouterOS stops reporting after 100 errors, so a long file is processed in pieces: the piece ends at the line where the
    limit was reached, and the next piece starts at that line again (its messages may have been cut off).
    """
    results = [None] * len(lines)
    pos = 0
    while pos < len(lines):
        batch = lines[pos : pos + 1500]
        out = router.script(NL.join(batch) + NL, "verbose=yes dry-run")
        messages = {}
        block = None
        errors = 0
        for line in out.split(NL):
            m = LINE.match(line)
            if m:
                block = int(m.group(1))
                messages[block] = []
            elif block is not None and line.strip():
                found = SUMMARY.search(line)
                if found and line.startswith("Script Error: found"):
                    errors = int(found.group(1))
                else:
                    messages[block].append(line.strip())
        last = max(messages) if messages else 0
        capped = errors >= 100
        keep = last - 1 if capped and last > 1 else last
        if keep == 0:
            keep = 1
        for i in range(keep):
            results[pos + i] = messages.get(i + 1, [])[1:]  # the first line is the statement itself
        pos += keep
        if pos % 3000 < keep:
            log(f"{label}: {pos}/{len(lines)}")
    return results


# Dummy unnamed arguments. A command may only take one of the forms: :if and :while need a group, :execute a block.
DUMMIES = ["0", "(0)", "{}"]


def probe_required(router, commands, log):
    """Returns {path: [required parameter names]} from compiling each bare command."""
    bare = compile_lines(router, [statement_for(p, "") for p in commands], log, "required")
    result = {}
    for i, p in enumerate(commands):
        required = []
        for message in bare[i]:
            m = MISSING.search(message)
            if m:
                required = m.group(1).split()
        result[p] = required
    return result


def probe_commands(router, commands, log):
    """Returns {path: {"required": [...], "unnamed": n}}.

    Required parameters come from compiling the bare command. The number of unnamed arguments is the largest count (0 to 3,
    where 3 stands for "more") that any of the dummy forms is accepted with.
    """
    bare = compile_lines(router, [statement_for(p, "") for p in commands], log, "commands")
    accepted = [0] * len(commands)
    for dummy in DUMMIES:
        for k in (1, 2, 3):
            suffix = " ".join([dummy] * k)
            answers = compile_lines(router, [statement_for(p, suffix) for p in commands], log, f"commands + {suffix!r}")
            for i, messages in enumerate(answers):
                if not any(REJECTED.search(m) for m in messages):
                    accepted[i] = max(accepted[i], k)
    result = {}
    for i, p in enumerate(commands):
        required = []
        for message in bare[i]:
            m = MISSING.search(message)
            if m:
                required = m.group(1).split()
        result[p] = {"required": required, "unnamed": accepted[i] if accepted[i] < 3 else 99}
    return result


def probe_flags(router, arg_paths, log):
    """Returns the set of arguments that can be written without a value (print's detail, brief ...): a bare name that is not
    rejected. A parameter that needs a value is rejected with "expected end of command". Only meaningful for commands that
    take no unnamed arguments; otherwise the bare name is accepted as such a value."""
    lines = [statement_for(p[:-1], p[-1]) for p in arg_paths]
    answers = compile_lines(router, lines, log, "flags")
    return {p for p, messages in zip(arg_paths, answers) if not any(REJECTED.search(m) for m in messages)}


# ---------------------------------------------------------------------------------------------------------------------


def assemble(tree, kinds, descriptions, types, completions, probes, flags, dynamic, meta):
    def node_for(path):
        kids = tree.get(path, [])
        node = {}
        desc = descriptions.get(path[:-1], {}).get(path[-1], "") if path else ""
        if desc:
            node["d"] = desc
        if path and kinds.get(path) == "cmd":
            node["k"] = 1
            args = {}
            arg_desc = descriptions.get(path, {})
            for name, kind in kids:
                if kind != "arg":
                    continue
                arg = {}
                if arg_desc.get(name):
                    arg["d"] = arg_desc[name]
                t, enums = types.get(path + (name,), ("", []))
                values, closed = completions.get(path + (name,), ([], False))
                merged = list(dict.fromkeys(enums + values))
                if depends_on_router(merged, dynamic):
                    merged, closed = [], False
                    t = ""  # the type text of such an argument is the list of this router's values
                if t:
                    arg["t"] = t
                if merged:
                    arg["e"] = merged
                    if closed:
                        arg["x"] = 1
                if path + (name,) in flags:
                    arg["f"] = 1
                args[name] = arg
            if args:
                node["a"] = args
            probe = probes.get(path, {})
            if probe.get("required"):
                node["r"] = probe["required"]
            if probe.get("unnamed"):
                node["u"] = probe["unnamed"]
        else:
            children = {name: node_for(path + (name,)) for name, kind in kids if kind in ("dir", "path", "cmd")}
            if children:
                node["c"] = children
        return node

    return {"format": 1, **meta, "root": node_for(())}


class Cache:
    """Keeps the raw answers of each phase so that a failure late in a long run does not cost the whole run."""

    def __init__(self, directory):
        self.directory = directory
        if directory:
            os.makedirs(directory, exist_ok=True)

    def get(self, name, compute, encode=lambda v: v, decode=lambda v: v):
        path = os.path.join(self.directory, name + ".json") if self.directory else None
        if path and os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return decode(json.load(f))
        value = compute()
        if path:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(encode(value), f)
        return value


def key(path):
    return ",".join(path)


def unkey(text):
    return tuple(text.split(",")) if text else ()


def encode_map(m):
    return {key(k): v for k, v in m.items()}


def decode_map(m):
    return {unkey(k): v for k, v in m.items()}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", required=True)
    ap.add_argument("--port", type=int, default=22)
    ap.add_argument("--user", default="admin")
    ap.add_argument("--out", required=True, help="output file, .json or .json.gz")
    ap.add_argument("--cache", help="directory for intermediate results; a rerun reuses them")
    ap.add_argument("--password-env", default="ROUTEROS_PASSWORD", help="environment variable that holds the password")
    args = ap.parse_args(argv)

    password = os.environ.get(args.password_env, "")
    log = lambda m: print(f"[{time.strftime('%H:%M:%S')}] {m}", file=sys.stderr, flush=True)
    router = Router(args.host, args.port, args.user, password)

    version = router.run(":put [/system resource get version]").strip()
    board = router.run(":put [/system resource get board-name]").strip()
    arch = router.run(":put [/system resource get architecture-name]").strip()
    packages = [ln.split()[0] for ln in router.run(":foreach p in=[/system package find where !disabled] do={ :put [/system package get $p name] }").split(NL) if ln.strip()]
    log(f"RouterOS {version} on {board} ({arch}); packages: {', '.join(packages)}")

    cache = Cache(args.cache)
    tree, kinds = cache.get(
        "tree",
        lambda: walk_tree(router, log),
        lambda v: [{key(k): [list(x) for x in kids] for k, kids in v[0].items()}, encode_map(v[1])],
        lambda v: ({unkey(k): [tuple(x) for x in kids] for k, kids in v[0].items()}, decode_map(v[1])),
    )
    cmd_paths = sorted(p for p, k in kinds.items() if k == "cmd")
    menu_paths = [()] + sorted(p for p, k in kinds.items() if k in ("dir", "path"))
    arg_paths = sorted(p + (name,) for p in cmd_paths for name, kind in tree.get(p, []) if kind == "arg")
    log(f"{len(menu_paths)} menus, {len(cmd_paths)} commands, {len(arg_paths)} arguments")

    syntax = cache.get("syntax", lambda: inspect_many(router, "syntax", [p for p in menu_paths + cmd_paths if p], "S", log), encode_map, decode_map)
    # the top level has no path to put in a list, so it is asked for on its own
    syntax.update(cache.get("root-syntax", lambda: inspect_many(router, "syntax", [()], "S", log), encode_map, decode_map))
    arg_syntax = cache.get("arg-syntax", lambda: inspect_many(router, "syntax", arg_paths, "T", log), encode_map, decode_map)
    arg_completion = cache.get("arg-completion", lambda: inspect_many(router, "completion", arg_paths, "C", log), encode_map, decode_map)
    probes = cache.get("probes", lambda: probe_commands(router, cmd_paths, log), encode_map, decode_map)
    required = cache.get("required", lambda: probe_required(router, cmd_paths, log), encode_map, decode_map)
    for p in cmd_paths:
        probes[p] = {**probes.get(p, {}), "required": required.get(p, [])}
    flag_candidates = [p for p in arg_paths if probes.get(p[:-1], {}).get("unnamed", 0) == 0]
    flags = {
        tuple(x)
        for x in cache.get("flags", lambda: [list(p) for p in sorted(probe_flags(router, flag_candidates, log))])
    }
    dynamic = set(cache.get("dynamic", lambda: sorted(dynamic_names(router))))

    descriptions = {path: describe_children(reply) for path, reply in syntax.items()}
    types = {p: parse_type(r) for p, r in arg_syntax.items()}
    completions = {p: parse_completion(r) for p, r in arg_completion.items()}

    meta = {"version": version.split()[0], "board": board, "architecture": arch, "packages": packages}
    data = assemble(tree, kinds, descriptions, types, completions, probes, flags, dynamic, meta)
    text = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    opener = gzip.open if args.out.endswith(".gz") else open
    with opener(args.out, "wt", encoding="utf-8", newline="") as f:
        f.write(text)
    log(f"wrote {args.out}: {len(text) / 1e6:.2f} MB of JSON")
    return 0


if __name__ == "__main__":
    sys.exit(main())
