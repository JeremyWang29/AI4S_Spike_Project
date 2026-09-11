from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import json
import uuid

from config.errors import BusinessError


def utcnow(): return datetime.now(timezone.utc)
def fingerprint(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class VersionRef:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    version: int = 1
    fingerprint: str = ""


@dataclass(frozen=True)
class Blocker:
    code: str
    message: str
    owner: str
    recovery: str


def require_revision(actual, expected):
    if actual != expected:
        raise BusinessError("REVISION_CONFLICT", "对象已被更新", status=409, owner="requester",
                            recovery="刷新后基于最新版本重试", details={"actual": actual, "expected": expected})


def require_idempotency(store, key, payload):
    digest = fingerprint(payload)
    if key in store and store[key] != digest:
        raise BusinessError("IDEMPOTENCY_CONFLICT", "同一幂等键对应不同请求", status=409,
                            recovery="使用新幂等键重试")
    store[key] = digest
    return digest
