"""Private, device-bound controller registration; no bearer secret is stored on Pi."""

import hashlib
import hmac
import json
import os
from pathlib import Path
import stat
import uuid


def valid_token(token):
    return isinstance(token, str) and len(token) == 64 and all(c in "0123456789abcdef" for c in token)


class CredentialStore:
    def __init__(self, path):
        self.path = Path(path)
        self.record = None
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._private(self.path.parent, directory=True)
        if self.path.exists() or self.path.is_symlink():
            self._private(self.path)
            fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd) as file:
                record = json.load(file)
            if (set(record) != {"version", "client_id", "device", "token_hash"}
                    or type(record["version"]) is not int or record["version"] != 1
                    or str(uuid.UUID(record["client_id"])) != record["client_id"]
                    or not isinstance(record["device"], str) or not record["device"].startswith("/org/bluez/")
                    or not valid_token(record["token_hash"])):
                raise ValueError("Invalid private controller registration")
            self.record = record

    @staticmethod
    def _private(path, directory=False):
        info = path.lstat()
        kind = stat.S_ISDIR if directory else stat.S_ISREG
        expected = 0o700 if directory else 0o600
        if not kind(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != expected:
            raise ValueError("Controller registration must be private and owned by this user")

    def register(self, device, client_id, token):
        if not valid_token(token) or not device.startswith("/org/bluez/"):
            raise ValueError("Invalid controller credential")
        record = dict(version=1, client_id=client_id, device=device,
                      token_hash=hashlib.sha256(token.encode("ascii")).hexdigest())
        temp = self.path.with_name(self.path.name + ".tmp")
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(fd, "w") as file:
                json.dump(record, file, separators=(",", ":"))
                file.flush()
                os.fsync(file.fileno())
            os.replace(temp, self.path)
            self.record = record
        finally:
            temp.unlink(missing_ok=True)

    def accepts(self, device, client_id, token):
        record = self.record
        if not record or not valid_token(token):
            return False
        digest = hashlib.sha256(token.encode("ascii")).hexdigest()
        return (device == record["device"] and client_id == record["client_id"]
                and hmac.compare_digest(digest, record["token_hash"]))
