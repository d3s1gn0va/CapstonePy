from email.message import Message
import hashlib
import hmac
import http.client
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "raspberry_pi/robot_demo"))
from exhibit_http import MediaHTTPServer, RequestAuthenticator, canonical_request, valid_target
from exhibit_media import RecordManager


class MediaHTTPTests(unittest.TestCase):
    def setUp(self):
        self.client = str(uuid.uuid4())
        self.token = "ab" * 32
        self.key = hashlib.sha256(self.token.encode("ascii")).digest()
        self.credentials = SimpleNamespace(record={"client_id": self.client,
                                                    "token_hash": self.key.hex()})
        self.now = 1700000000
        self.monotonic = 0
        self.auth = RequestAuthenticator(self.credentials, clock=lambda: self.now,
                                         monotonic=lambda: self.monotonic)

    def headers(self, target="/records", method="GET", nonce=None, stamp=None, auth=None):
        auth = auth or self.auth
        stamp = str(self.now if stamp is None else stamp)
        nonce = nonce or str(uuid.uuid4())
        signature = hmac.new(self.key, canonical_request(auth.challenge, self.client,
                            stamp, nonce, method, target), hashlib.sha256).hexdigest()
        return {"X-CUVO-Client": self.client, "X-CUVO-Time": stamp,
                "X-CUVO-Nonce": nonce, "X-CUVO-Signature": signature}

    def test_canonical_format_and_single_use(self):
        # Shared Python/Swift fixture catches byte/hex-token interpretation errors.
        fixture = canonical_request("11111111-1111-4111-8111-111111111111",
                                    "22222222-2222-4222-8222-222222222222", "1700000000",
                                    "33333333-3333-4333-8333-333333333333", "GET", "/records")
        self.assertEqual(hmac.new(self.key, fixture, hashlib.sha256).hexdigest(),
                         "65569ac34ee82b9ff88361ea49d098cc64dce899e3a745d0b5293031cd7be6a9")
        headers = self.headers()
        expected = ("CUVO-MEDIA-V1\n" + self.auth.challenge + "\n" + self.client + "\n"
                    + str(self.now) + "\n" + headers["X-CUVO-Nonce"] + "\nGET\n/records")
        self.assertEqual(canonical_request(self.auth.challenge, self.client, str(self.now),
                         headers["X-CUVO-Nonce"], "GET", "/records"), expected.encode())
        self.assertTrue(self.auth.accepts("GET", "/records", headers))
        self.assertFalse(self.auth.accepts("GET", "/records", headers))
        self.assertNotIn(self.token, json.dumps(headers))

    def test_signature_binds_method_target_and_boot_challenge(self):
        record_path = "/records/" + str(uuid.uuid4()) + "/video"
        self.assertFalse(self.auth.accepts("GET", record_path, self.headers()))
        self.assertFalse(self.auth.accepts("POST", "/records", self.headers(method="POST")))
        other = RequestAuthenticator(self.credentials, clock=lambda: self.now)
        self.assertFalse(other.accepts("GET", "/records", self.headers()))
        self.assertTrue(self.auth.accepts("GET", record_path, self.headers(record_path)))

    def test_stale_future_malformed_and_duplicate_auth_headers_rejected(self):
        for stamp in (self.now - 31, self.now + 31, "01700000000", "nan", "-1"):
            self.assertFalse(self.auth.accepts("GET", "/records", self.headers(stamp=stamp)))
        for key in self.headers():
            headers = self.headers()
            headers[key] = "invalid"
            self.assertFalse(self.auth.accepts("GET", "/records", headers))
        headers = Message()
        for key, value in self.headers().items():
            headers[key] = value
        headers["X-CUVO-Client"] = self.client
        self.assertFalse(self.auth.accepts("GET", "/records", headers))

    def test_bad_signature_does_not_consume_nonce_and_registration_revokes_access(self):
        headers = self.headers()
        invalid = dict(headers, **{"X-CUVO-Signature": "0" * 64})
        self.assertFalse(self.auth.accepts("GET", "/records", invalid))
        self.assertTrue(self.auth.accepts("GET", "/records", headers))
        self.credentials.record = dict(self.credentials.record, client_id=str(uuid.uuid4()))
        self.assertFalse(self.auth.accepts("GET", "/records", self.headers()))
        self.credentials.record = None
        self.assertFalse(self.auth.accepts("GET", "/records", self.headers()))

    def test_nonce_cache_is_bounded_without_evicting_replay_protection(self):
        self.auth.max_nonces = 2
        first = self.headers()
        self.assertTrue(self.auth.accepts("GET", "/records", first))
        self.assertTrue(self.auth.accepts("GET", "/records", self.headers()))
        self.assertFalse(self.auth.accepts("GET", "/records", self.headers()))
        self.assertFalse(self.auth.accepts("GET", "/records", first))
        self.now += 61
        self.monotonic += 61
        self.assertTrue(self.auth.accepts("GET", "/records", self.headers()))
        self.assertEqual(len(self.auth._used), 1)

    def test_only_fixed_canonical_paths(self):
        record_id = str(uuid.uuid4())
        for path in ("/records", f"/records/{record_id}/video", f"/records/{record_id}/thumbnail"):
            self.assertTrue(valid_target(path))
        for path in ("/", "/records/", "/records?limit=1", "/records/../controller.json",
                     f"/records/{record_id.upper()}/video", f"/records/{record_id}/video?x=1",
                     f"/records/{record_id}/%2e%2e", f"/records/{record_id}/video/",
                     "http://localhost/records"):
            self.assertFalse(valid_target(path), path)

    def make_store(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        records = RecordManager(Path(temp.name) / "records")
        record_id = str(uuid.uuid4())
        folder = records.root / record_id
        folder.mkdir(parents=True)
        metadata = {"id": record_id, "run_id": str(uuid.uuid4()), "play_id": "dance",
                    "created_at": "2026-10-20T12:00:00+00:00", "duration_seconds": 2.5,
                    "video": "video.mp4", "thumbnail": "thumbnail.jpg",
                    "source": "robot", "state": "ready"}
        (folder / "video.mp4").write_bytes(b"fixture-video")
        (folder / "thumbnail.jpg").write_bytes(b"fixture-thumbnail")
        (folder / "metadata.json").write_text(json.dumps(metadata))
        return records, metadata

    def server(self, records):
        server = MediaHTTPServer(records, self.credentials, bind_host="127.0.0.1", port=0,
                                 base_url="http://127.0.0.1:0", clock=lambda: self.now,
                                 monotonic=lambda: self.monotonic)
        self.addCleanup(server.close)
        return server

    def test_explicit_configuration_no_socket_until_start(self):
        server = self.server(SimpleNamespace())
        self.assertIsNone(server._server)
        self.assertEqual(server.descriptor["auth"], "hmac-sha256-v1")
        self.assertEqual(server.descriptor["server_time"], self.now)
        self.now += 90
        self.assertEqual(server.descriptor["server_time"], self.now)
        for url in ("http://0.0.0.0:0", "http://host", "http://user:pass@host:0",
                    "http://host:0/path", "https://host:0", "http://host:0?q=x"):
            with self.assertRaises(ValueError):
                MediaHTTPServer(None, self.credentials, bind_host="127.0.0.1", port=0, base_url=url)

    def test_open_validated_media_rejects_symlinks_and_empty_files(self):
        records, metadata = self.make_store()
        server = self.server(records)
        stream, size = server._open_media(metadata["id"], "video")
        with stream:
            self.assertEqual(stream.read(), b"fixture-video")
        self.assertEqual(size, len(b"fixture-video"))
        path = records.root / metadata["id"] / "video.mp4"
        path.unlink()
        path.symlink_to(records.root / metadata["id"] / "thumbnail.jpg")
        with self.assertRaises(RuntimeError):
            server._open_media(metadata["id"], "video")
        path.unlink()
        path.touch()
        with self.assertRaises(RuntimeError):
            server._open_media(metadata["id"], "video")

    def test_loopback_http_requires_auth_and_serves_only_completed_records(self):
        # Loopback only: fake media files, no Pi, camera, or robot hardware.
        records, metadata = self.make_store()
        server = self.server(records)
        descriptor = server.start()
        self.assertNotIn(":0", descriptor["base_url"])

        def request(target, headers=None, method="GET"):
            connection = http.client.HTTPConnection("127.0.0.1", server._server.server_port, timeout=2)
            try:
                connection.request(method, target, headers=headers or {})
                response = connection.getresponse()
                return response.status, response.getheader("Content-Type"), response.read()
            finally:
                connection.close()

        self.assertEqual(request("/records")[0], 401)
        headers = self.headers(auth=server.auth)
        status, _, body = request("/records", headers)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"records": [metadata]})
        self.assertEqual(request("/records", headers)[0], 401)
        target = f"/records/{metadata['id']}/video"
        status, content_type, body = request(target, self.headers(target, auth=server.auth))
        self.assertEqual((status, content_type, body), (200, "video/mp4", b"fixture-video"))
        target = f"/records/{metadata['id']}/thumbnail"
        status, content_type, body = request(target, self.headers(target, auth=server.auth))
        self.assertEqual((status, content_type, body), (200, "image/jpeg", b"fixture-thumbnail"))
        self.assertEqual(request(target, dict(self.headers(target, auth=server.auth), Range="bytes=0-1"))[0], 400)
        self.assertEqual(request("/records?x=1")[0], 404)
        self.assertEqual(request("/records/../metadata.json")[0], 404)
        self.assertEqual(request("/records", method="POST")[0], 405)
        server.close()
        self.assertIsNone(server._server)


if __name__ == "__main__":
    unittest.main()
