from dataclasses import dataclass, field
from hashlib import sha256
import uuid


@dataclass(frozen=True)
class SourceRecord:
    project_id: uuid.UUID
    corpus: str
    canonical_identity: str
    license_id: str
    purpose: str
    content_hash: str
    id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass(frozen=True)
class RecordOccurrence:
    source_record_id: uuid.UUID
    import_id: uuid.UUID
    platform: str
    external_id: str
    raw_file_hash: str


def content_hash(data: bytes): return sha256(data).hexdigest()
