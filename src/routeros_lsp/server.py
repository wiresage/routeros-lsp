"""The language server: JSON-RPC over stdio, text document sync, and the language features.

Only the standard library is used. The protocol subset is small: lifecycle, full and incremental document sync,
configuration, diagnostics (pushed), completion, hover, document symbols and folding ranges.

stdout belongs to the protocol. Everything else the process wants to say goes to the client through ``window/logMessage``.
"""

from __future__ import annotations

import json
import queue
import threading
from collections.abc import Callable
from typing import Any, BinaryIO

from . import __version__
from .analyze import Analysis, analyze, load_schema
from .config import DEFAULT_SETTINGS, Settings, has_settings, parse_settings
from .document import Document
from .features.completion import completions
from .features.diagnostics import to_diagnostics
from .features.folding import folding_ranges
from .features.hover import hover_at
from .features.symbols import document_symbols
from .schema.schema import Schema

NAME = "routeros-lsp"

# JSON-RPC and LSP error codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INTERNAL_ERROR = -32603
SERVER_NOT_INITIALIZED = -32002

LOG_ERROR, LOG_WARNING, LOG_INFO = 1, 2, 3

_EOF = object()


class MalformedMessage(ValueError):
    """A frame that was read whole but whose body is not a JSON-RPC message.

    The framing is intact, so the stream is still in step and the session can go on once the error has been answered.
    """

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


def read_message(stream: BinaryIO) -> dict[str, Any] | None:
    """Reads one framed JSON-RPC message, or None at the end of the stream. Raises MalformedMessage for an unusable body."""
    length: int | None = None
    while True:
        line = stream.readline()
        if not line:
            return None
        line = line.strip()
        if not line:
            if length is None:
                continue
            break
        name, _, value = line.partition(b":")
        if name.strip().lower() == b"content-length":
            try:
                length = int(value.strip())
            except ValueError:
                length = None
    body = stream.read(length)
    if len(body) < length:
        return None
    try:
        message = json.loads(body.decode("utf-8"))
    except (ValueError, RecursionError) as error:  # a bad UTF-8 sequence and bad JSON are both ValueErrors
        raise MalformedMessage(PARSE_ERROR, f"the message is not valid JSON: {error}") from error
    if not isinstance(message, dict):
        raise MalformedMessage(INVALID_REQUEST, "a JSON-RPC message must be an object")
    return message


def write_message(stream: BinaryIO, message: dict[str, Any]) -> None:
    body = json.dumps(message, separators=(",", ":")).encode("utf-8")
    stream.write(b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n\r\n" + body)
    stream.flush()


class Server:
    def __init__(self, reader: BinaryIO, writer: BinaryIO) -> None:
        self.reader = reader
        self.writer = writer
        self.documents: dict[str, Document] = {}
        self.settings: Settings = DEFAULT_SETTINGS
        self.schema: Schema | None = None
        self.initialized = False
        self.shutdown_requested = False
        self.exit_code: int | None = None
        self._inbox: queue.Queue[Any] = queue.Queue()
        self._dirty: dict[str, None] = {}
        self._cache: dict[str, tuple[tuple[int, int], Analysis]] = {}
        self._config_id = 0
        self._requests: dict[str, Callable[[dict[str, Any]], Any]] = {
            "initialize": self.on_initialize,
            "shutdown": self.on_shutdown,
            "textDocument/documentSymbol": self.on_document_symbol,
            "textDocument/foldingRange": self.on_folding_range,
            "textDocument/hover": self.on_hover,
            "textDocument/completion": self.on_completion,
        }
        self._notifications: dict[str, Callable[[dict[str, Any]], None]] = {
            "initialized": lambda params: None,
            "exit": self.on_exit,
            "textDocument/didOpen": self.on_did_open,
            "textDocument/didChange": self.on_did_change,
            "textDocument/didClose": self.on_did_close,
            "workspace/didChangeConfiguration": self.on_did_change_configuration,
        }

    # ------------------------------------------------------------------------------------------------------------------
    # Transport

    def send(self, message: dict[str, Any]) -> None:
        write_message(self.writer, {"jsonrpc": "2.0", **message})

    def respond(self, request_id: Any, result: Any = None) -> None:
        self.send({"id": request_id, "result": result})

    def respond_error(self, request_id: Any, code: int, message: str) -> None:
        self.send({"id": request_id, "error": {"code": code, "message": message}})

    def notify(self, method: str, params: dict[str, Any]) -> None:
        self.send({"method": method, "params": params})

    def log(self, level: int, message: str) -> None:
        self.notify("window/logMessage", {"type": level, "message": f"{NAME}: {message}"})

    def _read_loop(self) -> None:
        try:
            while True:
                try:
                    message = read_message(self.reader)
                except MalformedMessage as error:
                    # Answered by the main thread, which owns the output stream; the next frame can still be read.
                    self._inbox.put(error)
                    continue
                if message is None:
                    break
                self._inbox.put(message)
        except (OSError, ValueError):
            pass
        finally:
            self._inbox.put(_EOF)

    def run(self) -> int:
        """Serves until the client exits or closes the stream. Returns the process exit code."""
        threading.Thread(target=self._read_loop, name="reader", daemon=True).start()
        while self.exit_code is None:
            try:
                item = self._inbox.get_nowait()
            except queue.Empty:
                # Idle: publish what changed while messages were queued, once per document rather than once per edit.
                self.flush()
                item = self._inbox.get()
            if item is _EOF:
                return 0 if self.shutdown_requested else 1
            if isinstance(item, MalformedMessage):
                self.respond_error(None, item.code, str(item))
                continue
            self.dispatch(item)
        return self.exit_code

    def dispatch(self, message: dict[str, Any]) -> None:
        method = message.get("method")
        if not isinstance(method, str):
            return  # a response to a request this server never sends
        params = message.get("params")
        params = params if isinstance(params, dict) else {}
        if "id" in message:
            self.handle_request(message["id"], method, params)
        else:
            self.handle_notification(method, params)

    def handle_request(self, request_id: Any, method: str, params: dict[str, Any]) -> None:
        handler = self._requests.get(method)
        if handler is None:
            if method.startswith("$/"):
                self.respond(request_id, None)
            else:
                self.respond_error(request_id, METHOD_NOT_FOUND, f"method not supported: {method}")
            return
        if method != "initialize" and not self.initialized:
            self.respond_error(request_id, SERVER_NOT_INITIALIZED, "the server has not been initialized")
            return
        if self.shutdown_requested and method != "shutdown":
            self.respond_error(request_id, INVALID_REQUEST, "the server is shutting down")
            return
        try:
            result = handler(params)
        except Exception as error:  # a bug in one feature must not take the server down
            self.log(LOG_ERROR, f"{method} failed: {error!r}")
            result = (
                [] if method in ("textDocument/documentSymbol", "textDocument/foldingRange", "textDocument/completion") else None
            )
        self.respond(request_id, result)

    def handle_notification(self, method: str, params: dict[str, Any]) -> None:
        handler = self._notifications.get(method)
        if handler is None:
            return
        try:
            handler(params)
        except Exception as error:
            self.log(LOG_ERROR, f"{method} failed: {error!r}")

    # ------------------------------------------------------------------------------------------------------------------
    # Settings and analysis

    def apply_settings(self, raw: Any) -> None:
        self.settings = parse_settings(raw, lambda message: self.log(LOG_WARNING, message))
        self.schema = self._load_schema(self.settings.schema)
        self._config_id += 1

    def _load_schema(self, setting: str) -> Schema | None:
        return load_schema(setting, lambda message: self.log(LOG_WARNING, message))

    def analysis(self, document: Document) -> Analysis:
        key = (document.revision, self._config_id)
        cached = self._cache.get(document.uri)
        if cached is not None and cached[0] == key:
            return cached[1]
        settings = self.settings
        result = analyze(
            document.text,
            severities=settings.severities,
            scope=settings.scope,
            context_variables=settings.context_variables,
            schema=self.schema,
        )
        self._cache[document.uri] = (key, result)
        return result

    def publish(self, document: Document) -> None:
        self.notify(
            "textDocument/publishDiagnostics",
            {
                "uri": document.uri,
                "version": document.version,
                "diagnostics": to_diagnostics(document, self.analysis(document)),
            },
        )

    def flush(self) -> None:
        pending, self._dirty = list(self._dirty), {}
        for uri in pending:
            document = self.documents.get(uri)
            if document is None:
                continue
            try:
                self.publish(document)
            except Exception as error:  # a document the analysis cannot handle must not end the session for all the others
                self.log(LOG_ERROR, f"analysing {uri} failed: {error!r}")
                self.notify("textDocument/publishDiagnostics", {"uri": uri, "version": document.version, "diagnostics": []})

    # ------------------------------------------------------------------------------------------------------------------
    # Lifecycle

    def on_initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        self.apply_settings(params.get("initializationOptions"))
        self.initialized = True
        return {
            "serverInfo": {"name": NAME, "version": __version__},
            "capabilities": {
                "textDocumentSync": {"openClose": True, "change": 2},
                "documentSymbolProvider": True,
                "foldingRangeProvider": True,
                "hoverProvider": True,
                "completionProvider": {"triggerCharacters": ["$", ":", "/", "=", " "]},
            },
        }

    def on_shutdown(self, params: dict[str, Any]) -> None:
        self.shutdown_requested = True

    def on_exit(self, params: dict[str, Any]) -> None:
        self.exit_code = 0 if self.shutdown_requested else 1

    def on_did_change_configuration(self, params: dict[str, Any]) -> None:
        settings = params.get("settings")
        if not has_settings(settings):
            return  # "something changed" with nothing to read: keep the settings in force instead of resetting them
        self.apply_settings(settings)
        for uri in self.documents:
            self._dirty[uri] = None

    # ------------------------------------------------------------------------------------------------------------------
    # Text document sync

    def on_did_open(self, params: dict[str, Any]) -> None:
        item = params["textDocument"]
        document = Document(item["uri"], item.get("text", ""), item.get("version", 0), item.get("languageId", "routeros"))
        self.documents[document.uri] = document
        self._dirty[document.uri] = None

    def on_did_change(self, params: dict[str, Any]) -> None:
        identifier = params["textDocument"]
        document = self.documents.get(identifier["uri"])
        if document is None:
            return
        for change in params.get("contentChanges", []):
            document.apply_change(change)
        document.version = identifier.get("version", document.version)
        self._dirty[document.uri] = None

    def on_did_close(self, params: dict[str, Any]) -> None:
        uri = params["textDocument"]["uri"]
        self.documents.pop(uri, None)
        self._cache.pop(uri, None)
        self._dirty.pop(uri, None)
        self.notify("textDocument/publishDiagnostics", {"uri": uri, "diagnostics": []})

    # ------------------------------------------------------------------------------------------------------------------
    # Features

    def _document(self, params: dict[str, Any]) -> Document | None:
        return self.documents.get(params["textDocument"]["uri"])

    def on_document_symbol(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        document = self._document(params)
        return document_symbols(document, self.analysis(document).script) if document is not None else []

    def on_folding_range(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        document = self._document(params)
        return folding_ranges(document, self.analysis(document).script) if document is not None else []

    def on_hover(self, params: dict[str, Any]) -> dict[str, Any] | None:
        document = self._document(params)
        if document is None:
            return None
        return hover_at(document, self.analysis(document), document.offset_at(params["position"]))

    def on_completion(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        document = self._document(params)
        if document is None:
            return []
        return completions(document, self.analysis(document), self.schema, params["position"])
