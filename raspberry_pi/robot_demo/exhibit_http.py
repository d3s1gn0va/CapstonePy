"""Optional authenticated, read-only access to completed local recordings.

The operator supplies an advertised URL and binding address; there is no network
discovery or implicit listener. HMAC authenticates requests but does not encrypt
video, so this HTTP endpoint belongs on a trusted exhibition LAN. The app must
download a file before playback (Range and query requests are not supported).
Importing the module does not bind a socket or access robot hardware.
"""

from collections import OrderedDict
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import stat
import threading
import time
from urllib.parse import urlsplit, urlunsplit
import uuid


_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_MEDIA_PATH = re.compile(r"/records/(" + _UUID + r")/(video|thumbnail)\Z")
_SIGNATURE = re.compile(r"[0-9a-f]{64}\Z")
_METADATA_KEYS = {"id", "run_id", "play_id", "created_at", "duration_seconds",
                  "video", "thumbnail", "source", "state"}
MAX_MEDIA_BYTES = 256 * 1024 * 1024


def canonical_request(challenge, client_id, timestamp, nonce, method, target):
    """Exact UTF-8 input signed by the iPhone (no trailing newline)."""
    return "\n".join(("CUVO-MEDIA-V1", challenge, client_id, timestamp,
                      nonce, method, target)).encode("utf-8")


def valid_target(target):
    return isinstance(target, str) and (target == "/records" or bool(_MEDIA_PATH.fullmatch(target)))


class RequestAuthenticator:
    """Controller registration + bounded, single-use request authentication."""

    def __init__(self, credentials, challenge=None, clock=time.time,
                 monotonic=time.monotonic, max_nonces=1024):
        self.credentials = credentials
        self.challenge = challenge or str(uuid.uuid4())
        if str(uuid.UUID(self.challenge)) != self.challenge:
            raise ValueError("Challenge must be a canonical UUID")
        if type(max_nonces) is not int or not 1 <= max_nonces <= 1024:
            raise ValueError("Invalid nonce capacity")
        self.clock, self.monotonic = clock, monotonic
        self.max_nonces = max_nonces
        self._used = OrderedDict()
        self._lock = threading.Lock()

    @staticmethod
    def _header(headers, key):
        # Duplicate authentication fields must not have parser-dependent meaning.
        if hasattr(headers, "get_all"):
            values = headers.get_all(key, [])
            return values[0] if len(values) == 1 else None
        return headers.get(key)

    def accepts(self, method, target, headers):
        if method != "GET" or not valid_target(target):
            return False
        client, stamp, nonce, signature = (
            self._header(headers, name) for name in
            ("X-CUVO-Client", "X-CUVO-Time", "X-CUVO-Nonce", "X-CUVO-Signature"))
        if not all(isinstance(value, str) for value in (client, stamp, nonce, signature)):
            return False
        if (not re.fullmatch(_UUID, client) or not re.fullmatch(_UUID, nonce)
                or not re.fullmatch(r"[0-9]{1,12}", stamp)
                or str(int(stamp)) != stamp or not _SIGNATURE.fullmatch(signature)
                or abs(self.clock() - int(stamp)) > 30):
            return False
        # CredentialStore.register replaces this dictionary atomically. Re-read
        # it for every request, so registering a different phone revokes access.
        record = self.credentials.record
        if not isinstance(record, dict) or record.get("client_id") != client:
            return False
        token_hash = record.get("token_hash")
        if not isinstance(token_hash, str) or not _SIGNATURE.fullmatch(token_hash):
            return False
        expected = hmac.new(bytes.fromhex(token_hash), canonical_request(
            self.challenge, client, stamp, nonce, method, target), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            return False
        with self._lock:
            now = self.monotonic()
            while self._used and next(iter(self._used.values())) <= now - 60:
                self._used.popitem(last=False)
            key = (client, nonce)
            if key in self._used or len(self._used) >= self.max_nonces:
                return False
            self._used[key] = now
        return True


class _BoundedHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False
    request_queue_size = 8

    def __init__(self, *args, **kwargs):
        self._slots = threading.BoundedSemaphore(8)
        super().__init__(*args, **kwargs)

    def process_request(self, request, client_address):
        if not self._slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()

    def handle_error(self, request, client_address):
        # Do not leak request targets or filesystem paths into service logs.
        pass


class MediaHTTPServer:
    """Explicit lifecycle for an optional same-LAN recording endpoint."""

    def __init__(self, records, credentials, *, bind_host, port, base_url,
                 clock=time.time, monotonic=time.monotonic, challenge=None):
        if not isinstance(bind_host, str) or not bind_host.strip():
            raise ValueError("Explicit bind_host required")
        if type(port) is not int or not 0 <= port <= 65535:
            raise ValueError("Invalid port")
        url = urlsplit(base_url)
        if (url.scheme != "http" or not url.hostname or url.username or url.password
                or url.path not in ("", "/") or url.query or url.fragment
                or url.hostname in ("0.0.0.0", "::") or len(base_url) > 256):
            raise ValueError("Use an explicit http://host:port base URL")
        # Requiring an explicit port avoids accidental advertisement of port 80.
        if url.port != port:
            raise ValueError("Advertised port must match the listener port")
        self.records = records
        self.bind_host, self.port = bind_host, port
        self.base_url = urlunsplit((url.scheme, url.netloc, "", "", ""))
        self.auth = RequestAuthenticator(credentials, challenge, clock, monotonic)
        self._server = self._thread = None

    @property
    def descriptor(self):
        return {"base_url": self.base_url, "challenge": self.auth.challenge,
                "auth": "hmac-sha256-v1", "server_time": int(self.auth.clock())}

    def start(self):
        if self._server:
            return self.descriptor
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"
            server_version = "CUVOMedia/1"
            sys_version = ""

            def setup(self):
                super().setup()
                self.connection.settimeout(10)

            def log_message(self, *args):
                pass

            def reply(self, status, payload):
                body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if not valid_target(self.path):
                    self.reply(404, {"error": "not_found"})
                    return
                if self.headers.get("Range") is not None:
                    self.reply(400, {"error": "range_not_supported"})
                    return
                if not owner.auth.accepts("GET", self.path, self.headers):
                    self.reply(401, {"error": "unauthorized"})
                    return
                if self.path == "/records":
                    try:
                        records = [{key: item[key] for key in _METADATA_KEYS}
                                   for item in owner.records.list_records()[:100]]
                        self.reply(200, {"records": records})
                    except (OSError, ValueError, RuntimeError, KeyError):
                        self.reply(503, {"error": "records_unavailable"})
                    return
                record_id, kind = _MEDIA_PATH.fullmatch(self.path).groups()
                try:
                    stream, size = owner._open_media(record_id, kind)
                except (OSError, ValueError, RuntimeError):
                    self.reply(404, {"error": "not_found"})
                    return
                with stream:
                    self.send_response(200)
                    self.send_header("Content-Type", "video/mp4" if kind == "video" else "image/jpeg")
                    self.send_header("Content-Length", str(size))
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.end_headers()
                    remaining = size
                    while remaining:
                        chunk = stream.read(min(65536, remaining))
                        if not chunk:
                            return
                        self.wfile.write(chunk)
                        remaining -= len(chunk)

            def do_POST(self):
                self.reply(405, {"error": "read_only"})

            do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = do_POST

        server = _BoundedHTTPServer((self.bind_host, self.port), Handler)
        self._server = server
        if self.port == 0:
            url = urlsplit(self.base_url)
            host = f"[{url.hostname}]" if ":" in url.hostname else url.hostname
            self.base_url = f"http://{host}:{server.server_port}"
        self._thread = threading.Thread(target=server.serve_forever,
                                        kwargs={"poll_interval": 0.1}, daemon=True,
                                        name="cuvo-record-http")
        self._thread.start()
        return self.descriptor

    def _open_media(self, record_id, kind):
        # Validate the completed manifest first, then use directory-relative
        # NOFOLLOW opens so replacement symlinks cannot escape the private store.
        self.records.resolve_file(record_id, kind)
        filename = {"video": "video.mp4", "thumbnail": "thumbnail.jpg"}[kind]
        root_fd = os.open(Path(self.records.root), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            record_fd = os.open(record_id, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
            try:
                fd = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=record_fd)
            finally:
                os.close(record_fd)
        finally:
            os.close(root_fd)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_MEDIA_BYTES:
                raise ValueError("Invalid media file")
            return os.fdopen(fd, "rb"), info.st_size
        except BaseException:
            os.close(fd)
            raise

    def close(self):
        server, thread = self._server, self._thread
        self._server = self._thread = None
        if server:
            server.shutdown()
            server.server_close()
        if thread:
            thread.join(timeout=2)

