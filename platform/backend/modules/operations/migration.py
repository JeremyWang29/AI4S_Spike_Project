"""Read-only legacy migration inventory; it never carries legacy PASS state forward."""
import hashlib, sqlite3
from pathlib import Path

def inventory_legacy(database_path):
    path = Path(database_path).resolve()
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        tables = [r[0] for r in connection.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'")]
        counts = {
            name: connection.execute(f'SELECT COUNT(*) FROM "{name.replace(chr(34), chr(34) * 2)}"').fetchone()[0]
            for name in tables
        }
    finally: connection.close()
    after = hashlib.sha256(path.read_bytes()).hexdigest()
    if before != after: raise RuntimeError("legacy database fingerprint changed")
    return {"source": str(path), "fingerprint_before": before, "fingerprint_after": after,
            "counts": counts, "status_policy": "RE_EVALUATE_ALL", "id_map": {}}
