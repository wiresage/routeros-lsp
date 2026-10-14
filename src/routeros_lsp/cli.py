"""Command line entry point: ``routeros-lsp --stdio``."""

from __future__ import annotations

import sys

from . import __version__

NAME = "routeros-lsp"

USAGE = f"""{NAME} {__version__}

Language server for MikroTik RouterOS scripts (.rsc).

Usage:
  {NAME} --stdio                 Run the language server over stdin/stdout
  {NAME} check [options] PATH... Check script files and print the findings (see: {NAME} check --help)
  {NAME} --version               Print the version
  {NAME} --help                  Print this help
"""


def check(args: list[str]) -> int:
    from .cli_check import run

    # a file name or a message may hold characters the console cannot encode; print a replacement, never fail on it
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="replace")
    return run(args, sys.stdin.buffer, sys.stdout, sys.stderr)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args and args[0] == "check":
        return check(args[1:])
    if "--version" in args or "-v" in args:
        sys.stdout.write(f"{__version__}\n")
        return 0
    if "--help" in args or "-h" in args:
        sys.stdout.write(USAGE)
        return 0
    if "--stdio" not in args:
        sys.stderr.write(f"{NAME}: no transport given, use --stdio.\n\n{USAGE}")
        return 2

    import os

    from .server import Server

    # stdout carries the protocol and nothing else; anything that prints there would corrupt it.
    reader = sys.stdin.buffer
    writer = sys.stdout.buffer
    sys.stdout = sys.stderr
    code = Server(reader, writer).run()
    # The thread that reads stdin is still blocked in read(). Leaving through the normal shutdown would make the interpreter
    # wait for it, or die trying; the protocol says the session is over, so flush and leave.
    writer.flush()
    sys.stderr.flush()
    os._exit(code)


if __name__ == "__main__":
    sys.exit(main())
