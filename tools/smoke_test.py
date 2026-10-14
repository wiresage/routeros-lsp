"""Starts an installed routeros-lsp the way an editor does and checks that it works.

The release pipeline runs this against the built wheel, in a clean virtual environment, before anything is published. That proves
what the unit tests cannot: that the wheel contains the command database, that the entry point is wired, and that nothing but
protocol messages reaches stdout.

    python tools/smoke_test.py routeros-lsp [--expect-version 1.2.3]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys


def send(process: subprocess.Popen[bytes], message: dict[str, object]) -> None:
    body = json.dumps(message).encode("utf-8")
    assert process.stdin is not None
    process.stdin.write(b"Content-Length: %d\r\n\r\n%s" % (len(body), body))
    process.stdin.flush()


def receive(process: subprocess.Popen[bytes]) -> dict[str, object]:
    assert process.stdout is not None
    length = None
    while True:
        line = process.stdout.readline()
        if not line:
            raise SystemExit("the server closed stdout before answering")
        line = line.strip()
        if not line:
            break
        name, _, value = line.partition(b":")
        if name.lower() == b"content-length":
            length = int(value)
    if length is None:
        raise SystemExit("a message without Content-Length: stdout carries more than the protocol")
    message: dict[str, object] = json.loads(process.stdout.read(length))
    return message


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", help="the routeros-lsp executable")
    parser.add_argument("--expect-version", help="the version --version must print")
    args = parser.parse_args()

    version = subprocess.run([args.command, "--version"], capture_output=True, text=True, check=True, timeout=60).stdout.strip()
    print(f"version: {version}")
    if args.expect_version and version != args.expect_version:
        raise SystemExit(f"expected version {args.expect_version}, the command reports {version}")

    process = subprocess.Popen([args.command, "--stdio"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        send(process, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"processId": None, "rootUri": None, "capabilities": {}}})
        info = receive(process)["result"]
        assert isinstance(info, dict)
        print(f"server: {info['serverInfo']}")
        if args.expect_version and info["serverInfo"]["version"] != args.expect_version:
            raise SystemExit(f"the server reports version {info['serverInfo']['version']}, expected {args.expect_version}")
        send(process, {"jsonrpc": "2.0", "method": "initialized", "params": {}})

        text = "/ip address add address=1.1.1.1/32 interface=ether1\n/nonsense\n:put 1 # c\n"
        document = {"uri": "file:///smoke.rsc", "languageId": "routeros", "version": 1, "text": text}
        send(process, {"jsonrpc": "2.0", "method": "textDocument/didOpen", "params": {"textDocument": document}})
        published = receive(process)
        params = published["params"]
        assert isinstance(params, dict)
        codes = sorted(d["code"] for d in params["diagnostics"])
        print(f"diagnostics: {codes}")
        # unknown-command needs the bundled command database, so this fails on a wheel that left the data file out
        if codes != ["schema/unexpected-argument", "schema/unknown-command"]:
            raise SystemExit(f"unexpected diagnostics {codes}")

        send(process, {"jsonrpc": "2.0", "id": 2, "method": "shutdown", "params": None})
        receive(process)
        send(process, {"jsonrpc": "2.0", "method": "exit"})
        code = process.wait(timeout=30)
        if code != 0:
            raise SystemExit(f"the server exited with {code} after a clean shutdown")
    finally:
        if process.poll() is None:
            process.kill()
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                stream.close()
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
