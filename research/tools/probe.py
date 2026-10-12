"""RouterOS script conformance probes (run with the pkgtest venv; needs paramiko).

Modes
  check : upload the snippet as lspprobe.rsc and run `/import ... verbose=yes dry-run`.
          Reports errors, executes nothing, changes nothing. Closest to what a .rsc file meets.
  eval  : run a single-line pure expression through the console and show the output.
  run   : REAL import of a benign snippet (only :put / :local / print style lines) and show what it printed.
Nothing here changes router configuration. The only files written are lspprobe.rsc, removed at the end.
"""
import os, re, sys
if "MIKROTIK_INVENTORY_FILE" not in os.environ:
    sys.exit("set MIKROTIK_INVENTORY_FILE to a mikrotik-mcp inventory file (see research/README.md)")
import logging
logging.disable(logging.CRITICAL)
import paramiko
from mcp_mikrotik.inventory import _load_devices

DEV = next(d for d in _load_devices() if d.title == (sys.argv[2] if len(sys.argv) > 2 else "RouterA"))
SUITE = sys.argv[1]
NL = chr(10)
CR = chr(13)


def connect():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(DEV.host, port=DEV.port, username=DEV.username, password=DEV.password,
              look_for_keys=False, allow_agent=False, timeout=20)
    return c


C = connect()
SFTP = C.open_sftp()


def run(cmd, timeout=30):
    _, out, err = C.exec_command(cmd, timeout=timeout)
    return (out.read().decode("utf-8", "replace") + err.read().decode("utf-8", "replace")).strip()


def put(name, data):
    with SFTP.open(name, "wb") as f:
        f.write(data)


ERR_RE = re.compile(r"\(line \d+ column \d+\)|^Script Error|found \d+ error|^syntax error|^bad command|^expected |^invalid |^failure|^not enough", re.I)


def classify(out):
    """Reduce an import dry-run transcript to the error lines it reports."""
    errs, summary = [], ""
    for ln in out.replace(CR, "").split(NL):
        if ln.startswith("#line") or not ln.strip():
            continue
        if ln.startswith("Script Error: found"):
            summary = ln.strip()
        elif ERR_RE.search(ln):
            errs.append(ln.strip())
    if errs or summary:
        return "ERR: " + " ; ".join(errs)[:170] + ("   [" + summary + "]" if summary else "")
    return "OK" if "No syntax errors" in out else "?? " + out.replace(NL, " | ")[:100]


def probe(mode, snippet):
    data = snippet.encode("utf-8") if isinstance(snippet, str) else snippet
    if mode == "eval":
        return run(snippet)
    if mode == "check":
        put("lspprobe.rsc", data)
        return classify(run("/import file-name=lspprobe.rsc verbose=yes dry-run"))
    if mode == "run":
        put("lspprobe.rsc", data)
        out = run("/import file-name=lspprobe.rsc verbose=yes").replace(CR, "")
        src = [x.strip() for x in snippet.split(NL)]
        keep = [x for x in out.split(NL) if x.strip() and not x.startswith("#line") and x.strip() not in src]
        return ("OUT: " + " | ".join(keep)) if keep else "OUT: (nothing)"
    raise ValueError(mode)


def main():
    ns = {}
    exec(open(SUITE, encoding="utf-8").read(), ns)
    print("version:", run(":put [/system resource get version]"))
    for item in ns["PROBES"]:
        if isinstance(item, str):
            print(NL + "== " + item)
            continue
        pid, mode, snippet, note = item
        try:
            res = probe(mode, snippet)
        except Exception as e:
            res = "<%s: %s>" % (type(e).__name__, e)
        shown = snippet.replace(CR, "\\r").replace(NL, "\\n") if isinstance(snippet, str) else repr(snippet)[:60]
        print("%-4s %-5s %-60s -> %s" % (pid, mode, shown[:60], res.replace(NL, " | ")[:150]) + ("   # " + note if note else ""))
    run('/file remove [find name="lspprobe.rsc"]')
    print(NL + "cleanup: probe files left on the router:", run('/file print count-only where name~"lspprobe"'))


main()
