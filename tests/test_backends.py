"""Unit tests for backends and caching."""
from __future__ import annotations

from pathlib import Path

import pytest

from finsight.backends import (
    Backend,
    CachedBackend,
    ExtractionError,
    StubBackend,
    choose_backend,
)
from finsight.cache import ReplayMiss, ResponseCache


def test_stub_backend_records_calls_and_returns_responses():
    stub = StubBackend(
        responses=[
            {"revenue": 1000},
            {"revenue": 1200},
        ]
    )
    assert isinstance(stub, Backend)

    resp1 = stub.generate_json(
        system="sys prompt",
        prompt="extract revenue",
        schema={"type": "object"},
    )
    assert resp1 == {"revenue": 1000}
    assert len(stub.calls) == 1
    assert stub.calls[0]["system"] == "sys prompt"
    assert stub.calls[0]["prompt"] == "extract revenue"

    resp2 = stub.generate_json(
        system="sys prompt",
        prompt="extract revenue 2",
        schema={"type": "object"},
    )
    assert resp2 == {"revenue": 1200}
    assert len(stub.calls) == 2


def test_cached_backend_hits_cache_on_second_call(tmp_path: Path):
    stub = StubBackend(responses=[{"val": 42}])
    cache = ResponseCache(cache_dir=tmp_path / "cache")
    cached_be = CachedBackend(stub, cache=cache)

    res1 = cached_be.generate_json(
        system="sys",
        prompt="p1",
        schema={"type": "object"},
    )
    assert res1 == {"val": 42}
    assert len(stub.calls) == 1
    assert cache.stats.writes == 1
    assert cache.stats.hits == 0

    # Second identical call must NOT touch the underlying backend
    res2 = cached_be.generate_json(
        system="sys",
        prompt="p1",
        schema={"type": "object"},
    )
    assert res2 == {"val": 42}
    assert len(stub.calls) == 1
    assert cache.stats.hits == 1


def test_replay_mode_raises_on_cache_miss(tmp_path: Path):
    stub = StubBackend(responses=[{"val": 100}])
    cache = ResponseCache(cache_dir=tmp_path / "cache", replay=True)
    cached_be = CachedBackend(stub, cache=cache)

    with pytest.raises(ReplayMiss, match="Replay mode active but cache key not found"):
        cached_be.generate_json(
            system="sys",
            prompt="unrecorded_query",
            schema={"type": "object"},
        )
    # The underlying backend was never contacted
    assert len(stub.calls) == 0


def test_confidential_routing_never_returns_cloud(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake_key_123")

    # 1. confidential=True with auto routing -> must choose local
    be_auto = choose_backend(confidential=True)
    assert "ollama" in be_auto.name.lower() or be_auto.model_id.startswith("gemma4")
    assert "gemini" not in be_auto.name.lower()

    # 2. confidential=True with cloud requested -> must reject with ValueError
    with pytest.raises(ValueError, match="Confidential mode strictly forbids cloud"):
        choose_backend(confidential=True, backend_override="cloud")


def test_explicit_cloud_routing(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test_key")
    be = choose_backend(confidential=False, backend_override="cloud")
    assert "gemini" in be.name.lower()


def test_extraction_error_on_exception():
    stub = StubBackend(responses=[ExtractionError("Failed to parse JSON")])
    with pytest.raises(ExtractionError, match="Failed to parse JSON"):
        stub.generate_json(system="", prompt="", schema={})
