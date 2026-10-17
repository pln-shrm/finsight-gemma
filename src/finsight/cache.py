"""Content-hash cassette cache for backend calls.

Records model responses keyed by sha256 of:
(model, params, system_prompt, user_prompt, image_bytes_hashes, schema).
Enables deterministic, replayable, offline testing and live demos.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ReplayMiss(RuntimeError):
    """Raised when running in --replay mode and a cache miss occurs."""


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    writes: int = 0


class ResponseCache:
    """Filesystem-backed JSON response cache keyed by SHA-256 hash."""

    def __init__(self, cache_dir: Path | str = ".cache", replay: bool = False):
        self.cache_dir = Path(cache_dir)
        self.replay = replay
        self.stats = CacheStats()
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def compute_key(
        *,
        model: str,
        system: str,
        prompt: str,
        images: list[bytes] | None = None,
        schema: dict[str, Any] | None = None,
        temperature: float = 0.0,
        extra: dict[str, Any] | None = None,
    ) -> str:
        """Deterministically hash the full request payload."""
        hasher = hashlib.sha256()
        hasher.update(model.encode())
        hasher.update(b"\x00")
        hasher.update(system.encode())
        hasher.update(b"\x00")
        hasher.update(prompt.encode())
        hasher.update(b"\x00")
        hasher.update(f"{temperature:.4f}".encode())
        hasher.update(b"\x00")

        if schema:
            schema_bytes = json.dumps(schema, sort_keys=True).encode()
            hasher.update(schema_bytes)
        hasher.update(b"\x00")

        if images:
            for img in images:
                hasher.update(hashlib.sha256(img).digest())
        hasher.update(b"\x00")

        if extra:
            extra_bytes = json.dumps(extra, sort_keys=True).encode()
            hasher.update(extra_bytes)

        return hasher.hexdigest()

    def get(self, key: str) -> dict[str, Any] | None:
        """Fetch cached response for *key*, or None if miss."""
        file_path = self.cache_dir / f"{key}.json"
        if file_path.exists():
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                self.stats.hits += 1
                return data
            except (json.JSONDecodeError, OSError):
                # Corrupt cache entry — treat as cache miss
                pass

        self.stats.misses += 1
        if self.replay:
            raise ReplayMiss(
                f"Replay mode active but cache key not found: {key}. "
                f"Expected file at {file_path}. Run without --replay to record first."
            )
        return None

    def put(self, key: str, data: dict[str, Any]) -> Path:
        """Save *data* to cache under *key*. Returns written path."""
        file_path = self.cache_dir / f"{key}.json"
        file_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self.stats.writes += 1
        return file_path
