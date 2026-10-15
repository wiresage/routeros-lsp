"""A minimal LSP client for tests: just enough to open documents and read what the server says."""

from __future__ import annotations

import contextlib
import os
import subprocess
import sys
import threading
from collections import defaultdict
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, BinaryIO

from routeros_lsp.server import Server, read_message, write_message

ROOT = Path(__file__).resolve().parent.parent
TIMEOUT = 10.0


class LspClient:
    def __init__(self, reader: BinaryIO, writer: BinaryIO) -> None:
        self.reader = reader
        self.writer = writer
        self.errors: list[BaseException] = []
        self.initialize_result: dict[str, Any] = {}
        self.logs: list[dict[str, Any]] = []
        self._cv = threading.Condition()
        self._responses: dict[int | None, dict[str, Any]] = {}
        self._published: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._next_id = 1
        self._closed = False
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self) -> None:
        try:
            while True:
                message = read_message(self.reader)
                if message is None:
                    break
                with self._cv:
                    method = message.get("method")
                    if method == "textDocument/publishDiagnostics":
                        self._published[message["params"]["uri"]].append(message["params"])
                    elif method == "window/logMessage":
                        self.logs.append(message["params"])
                    elif "id" in message and method is None:
                        self._responses[message["id"]] = message
                    self._cv.notify_all()
        except BaseException as error:
            self.errors.append(error)
        finally:
            with self._cv:
                self._closed = True
                self._cv.notify_all()

    # -- plumbing ---------------------------------------------------------------------------------------------------------

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        write_message(self.writer, {"jsonrpc": "2.0", "method": method, "params": params or {}})

    def request_raw(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        write_message(self.writer, {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}})
        with self._cv:
            if not self._cv.wait_for(lambda: request_id in self._responses or self._closed, TIMEOUT):
                raise TimeoutError(f"no answer to {method}")
            if request_id not in self._responses:
                raise ConnectionError(f"the server closed the stream before answering {method}")
            return self._responses.pop(request_id)

    def send_unusable(self, body: bytes) -> dict[str, Any]:
        """Sends a correctly framed body that is not a JSON-RPC message and returns the answer, which has no request id."""
        self.writer.write(b"Content-Length: %d\r\n\r\n%s" % (len(body), body))
        self.writer.flush()
        with self._cv:
            if not self._cv.wait_for(lambda: None in self._responses or self._closed, TIMEOUT):
                raise TimeoutError("no answer to an unusable message")
            if None not in self._responses:
                raise ConnectionError("the server closed the stream instead of answering an unusable message")
            return self._responses.pop(None)

    def request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        response = self.request_raw(method, params)
        if "error" in response:
            raise RuntimeError(response["error"])
        return response.get("result")

    def published(self, uri: str) -> list[dict[str, Any]]:
        with self._cv:
            return list(self._published[uri])

    def _after(self, uri: str, action: Callable[[], None]) -> list[dict[str, Any]]:
        """Runs ``action`` and returns the diagnostics of the next publishDiagnostics for ``uri``."""
        with self._cv:
            before = len(self._published[uri])
        action()
        with self._cv:
            if not self._cv.wait_for(lambda: len(self._published[uri]) > before, TIMEOUT):
                raise TimeoutError(f"no diagnostics for {uri} within {TIMEOUT} s")
            return list(self._published[uri][-1]["diagnostics"])

    def wait_for_version(self, uri: str, version: int) -> list[dict[str, Any]]:
        """Blocks until diagnostics for the given document version were published and returns them."""

        def found() -> dict[str, Any] | None:
            return next((p for p in self._published[uri] if p.get("version") == version), None)

        with self._cv:
            if not self._cv.wait_for(found, TIMEOUT):
                raise TimeoutError(f"no diagnostics for version {version} of {uri} within {TIMEOUT} s")
            return list(found()["diagnostics"])  # type: ignore[index]

    # -- the protocol -----------------------------------------------------------------------------------------------------

    def initialize(self, initialization_options: Any = None) -> dict[str, Any]:
        params: dict[str, Any] = {"processId": None, "rootUri": None, "capabilities": {}}
        if initialization_options is not None:
            params["initializationOptions"] = initialization_options
        result = self.request("initialize", params)
        self.notify("initialized", {})
        return result  # type: ignore[no-any-return]

    def open(self, uri: str, text: str, version: int = 1) -> list[dict[str, Any]]:
        document = {"uri": uri, "languageId": "routeros", "version": version, "text": text}
        return self._after(uri, lambda: self.notify("textDocument/didOpen", {"textDocument": document}))

    def change(self, uri: str, text: str, version: int) -> list[dict[str, Any]]:
        params = {"textDocument": {"uri": uri, "version": version}, "contentChanges": [{"text": text}]}
        return self._after(uri, lambda: self.notify("textDocument/didChange", params))

    def edit(self, uri: str, changes: list[dict[str, Any]], version: int) -> list[dict[str, Any]]:
        params = {"textDocument": {"uri": uri, "version": version}, "contentChanges": changes}
        return self._after(uri, lambda: self.notify("textDocument/didChange", params))

    def close(self, uri: str) -> list[dict[str, Any]]:
        return self._after(uri, lambda: self.notify("textDocument/didClose", {"textDocument": {"uri": uri}}))

    def configure(self, settings: Any, revalidate: str) -> list[dict[str, Any]]:
        """Sends new settings and returns the diagnostics the server publishes again for ``revalidate``."""
        return self._after(revalidate, lambda: self.notify("workspace/didChangeConfiguration", {"settings": settings}))

    def symbols(self, uri: str) -> list[dict[str, Any]]:
        return self.request("textDocument/documentSymbol", {"textDocument": {"uri": uri}})  # type: ignore[no-any-return]

    def folding(self, uri: str) -> list[dict[str, Any]]:
        return self.request("textDocument/foldingRange", {"textDocument": {"uri": uri}})  # type: ignore[no-any-return]

    def hover(self, uri: str, line: int, character: int) -> dict[str, Any] | None:
        return self.request(
            "textDocument/hover", {"textDocument": {"uri": uri}, "position": {"line": line, "character": character}}
        )  # type: ignore[no-any-return]

    def completion(self, uri: str, line: int, character: int) -> list[dict[str, Any]]:
        params = {"textDocument": {"uri": uri}, "position": {"line": line, "character": character}}
        return self.request("textDocument/completion", params)  # type: ignore[no-any-return]

    def shutdown(self) -> None:
        self.request("shutdown")
        self.notify("exit")


@contextmanager
def in_process(initialization_options: Any = None, initialize: bool = True) -> Iterator[LspClient]:
    """The server in a thread of this process, connected to a client through pipes."""
    to_server_r, to_server_w = os.pipe()
    from_server_r, from_server_w = os.pipe()
    server_in, server_out = os.fdopen(to_server_r, "rb"), os.fdopen(from_server_w, "wb")
    server = Server(server_in, server_out)

    def serve() -> None:
        try:
            server.run()
        finally:
            # like a process that ends: the client sees the end of the stream instead of waiting for an answer
            server_out.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    client = LspClient(os.fdopen(from_server_r, "rb"), os.fdopen(to_server_w, "wb"))
    try:
        if initialize:
            client.initialize_result = client.initialize(initialization_options)
        yield client
    finally:
        # a test may have ended the session itself; then there is nobody left to shut down
        if thread.is_alive():
            with contextlib.suppress(OSError, TimeoutError, ConnectionError, RuntimeError):
                client.shutdown()
        thread.join(timeout=5)
        client.writer.close()
        server_in.close()


@contextmanager
def spawned(initialization_options: Any = None) -> Iterator[tuple[LspClient, subprocess.Popen[bytes]]]:
    """The real command, ``python -m routeros_lsp --stdio``, as a child process."""
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    process = subprocess.Popen(
        [sys.executable, "-m", "routeros_lsp", "--stdio"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    assert process.stdin is not None and process.stdout is not None
    client = LspClient(process.stdout, process.stdin)
    try:
        client.initialize(initialization_options)
        yield client, process
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                stream.close()
