"""Runs `/import ... dry-run` on local .rsc files and prints one JSON verdict per file.

Usage: MIKROTIK_INVENTORY_FILE=... python research/tools/check_files.py [--device RouterA] FILE... > verdicts.json
Nothing is executed on the router and nothing is changed; the uploaded copy is removed afterwards.
"""
import json, logging, os, re, sys
logging.disable(logging.CRITICAL)
if "MIKROTIK_INVENTORY_FILE" not in os.environ:
    sys.exit("set MIKROTIK_INVENTORY_FILE to a mikrotik-mcp inventory file (see research/README.md)")
import paramiko
from mcp_mikrotik.inventory import _load_devices

args = sys.argv[1:]
device = "RouterA"
if args[:1] == ["--device"]:
    device, args = args[1], args[2:]
DEV = next(d for d in _load_devices() if d.title == device)
NL, CR = chr(10), chr(13)
ERR_RE = re.compile(r"\(line \d+ column \d+\)|^Script Error|found \d+ error|^syntax error|^bad command|^expected |^invalid |^failure|^not enough", re.I)


def classify(out):
    errs = []
    for ln in out.replace(CR, "").split(NL):
        if ln.startswith("#line") or not ln.strip() or ln.startswith("Script Error: found"):
            continue
        if ERR_RE.search(ln):
            errs.append(ln.strip())
    return {"valid": not errs and "No syntax errors" in out, "errors": errs}


c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(DEV.host, port=DEV.port, username=DEV.username, password=DEV.password, look_for_keys=False, allow_agent=False, timeout=20)
sftp = c.open_sftp()
result = {}
for path in args:
    with open(path, "rb") as f:
        data = f.read()
    with sftp.open("lspcheck.rsc", "wb") as f:
        f.write(data)
    _, out, err = c.exec_command("/import file-name=lspcheck.rsc verbose=yes dry-run", timeout=60)
    text = out.read().decode("utf-8", "replace") + err.read().decode("utf-8", "replace")
    result[os.path.basename(path)] = classify(text)
c.exec_command('/file remove [find name="lspcheck.rsc"]')
print(json.dumps(result, indent=1, ensure_ascii=False))
