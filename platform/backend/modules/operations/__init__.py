from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json

@dataclass
class Journal:
    entries: list = field(default_factory=list)
    def append(self, kind, payload, remote_receipt=None):
        previous = self.entries[-1]["hash"] if self.entries else "0" * 64
        record = {"kind": kind, "payload": payload, "previous_hash": previous, "remote_receipt": remote_receipt}
        record["hash"] = sha256(json.dumps(record, sort_keys=True).encode()).hexdigest(); self.entries.append(record); return record
    def verify(self):
        previous = "0" * 64
        for entry in self.entries:
            raw = {k: entry[k] for k in ("kind", "payload", "previous_hash", "remote_receipt")}
            if entry["previous_hash"] != previous or sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest() != entry["hash"]: return False
            previous = entry["hash"]
        return True

@dataclass
class Deletion:
    requested_at: datetime
    license_expires_at: datetime | None = None
    remote_journaled: bool = False
    @property
    def content_accessible(self): return False
    @property
    def purge_at(self):
        thirty = self.requested_at + timedelta(days=30)
        return min(thirty, self.license_expires_at) if self.license_expires_at else thirty
    @property
    def accepted(self): return self.remote_journaled
