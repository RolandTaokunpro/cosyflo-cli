"""CLI-side append-only, hash-chained audit log (D3, SR4).

JSONL, one line per mutation: UTC timestamp, command, params, operator,
status, prev_hash + hash (tamper-evident chain). Reads never append.
The Bearer token must never appear here — entries only carry command args.
"""
import hashlib
import json
import os

GENESIS = ""


def _line_hash(prev_hash, record):
    canonical = json.dumps(record, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256((prev_hash + canonical).encode()).hexdigest()


class AuditLog:
    def __init__(self, path):
        self.path = os.path.expanduser(path)

    def _last_hash(self):
        if not os.path.exists(self.path):
            return GENESIS
        last = GENESIS
        with open(self.path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    last = json.loads(line).get("hash", GENESIS)
                except ValueError:
                    continue
        return last

    def append(self, entry):
        """Append one mutation record; returns the stored line (with prev_hash/hash)."""
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        prev_hash = self._last_hash()
        record = dict(entry)
        record["prev_hash"] = prev_hash
        record["hash"] = _line_hash(prev_hash, record)
        with open(self.path, "a") as f:
            f.write(json.dumps(record, sort_keys=True) + "\n")
        return record

    def read(self):
        if not os.path.exists(self.path):
            return []
        with open(self.path) as f:
            return [json.loads(line) for line in f if line.strip()]