"""Model backend adapters: Ollama (local) and Gemini API (cloud), plus cache wrapper.

Strict adherence to:
- Protocol-driven design (Backend)
- Schema-constrained JSON outputs
- Multimodal image inputs (bytes)
- Content-hash caching with replay mode
- Confidential routing: confidential=True NEVER routes to cloud
- Automatic re-ask on malformed JSON before raising ExtractionError
"""
from __future__ import annotations

import json
import os
import tomllib
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import ollama
from google import genai
from google.genai import types

from .cache import ResponseCache


class ExtractionError(Exception):
    """Raised when a backend fails to produce schema-valid JSON output."""


@runtime_checkable
class Backend(Protocol):
    name: str
    model_id: str

    def generate_json(
        self,
        *,
        system: str,
        prompt: str,
        images: list[bytes] | None = None,
        schema: dict[str, Any] | None = None,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        """Generate a JSON response conforming to *schema*."""
        ...


class StubBackend:
    """Deterministic in-memory backend for unit tests."""

    def __init__(
        self,
        name: str = "stub",
        model_id: str = "stub-model",
        responses: list[dict[str, Any] | Exception] | None = None,
    ):
        self.name = name
        self.model_id = model_id
        self.responses: list[dict[str, Any] | Exception] = list(responses or [])
        self.calls: list[dict[str, Any]] = []

    def generate_json(
        self,
        *,
        system: str,
        prompt: str,
        images: list[bytes] | None = None,
        schema: dict[str, Any] | None = None,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        self.calls.append({
            "system": system,
            "prompt": prompt,
            "images": images or [],
            "schema": schema,
            "temperature": temperature,
        })
        if not self.responses:
            return {}
        resp = self.responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp


class CachedBackend:
    """Wraps any Backend with content-hash caching and replay support."""

    def __init__(
        self,
        backend: Backend,
        cache: ResponseCache | None = None,
        cache_dir: Path | str = ".cache",
        replay: bool = False,
    ):
        self.backend = backend
        self.cache = cache or ResponseCache(cache_dir=cache_dir, replay=replay)
        self.name = f"cached({backend.name})"
        self.model_id = backend.model_id

    def generate_json(
        self,
        *,
        system: str,
        prompt: str,
        images: list[bytes] | None = None,
        schema: dict[str, Any] | None = None,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        key = self.cache.compute_key(
            model=self.model_id,
            system=system,
            prompt=prompt,
            images=images,
            schema=schema,
            temperature=temperature,
        )
        cached = self.cache.get(key)
        if cached is not None:
            return cached

        data = self.backend.generate_json(
            system=system,
            prompt=prompt,
            images=images,
            schema=schema,
            temperature=temperature,
        )
        self.cache.put(key, data)
        return data


class OllamaBackend:
    """Local inference via Ollama."""

    def __init__(
        self,
        model: str = "gemma4:e4b",
        host: str = "http://localhost:11434",
        num_ctx: int = 4096,
        client: ollama.Client | None = None,
    ):
        self.name = "ollama"
        self.model_id = model
        self.host = host
        self.num_ctx = num_ctx
        self.client = client or ollama.Client(host=host)

    def generate_json(
        self,
        *,
        system: str,
        prompt: str,
        images: list[bytes] | None = None,
        schema: dict[str, Any] | None = None,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        options = {"num_ctx": self.num_ctx, "temperature": temperature}

        def _call(user_msg: str) -> str:
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            user_payload: dict[str, Any] = {"role": "user", "content": user_msg}
            if images:
                user_payload["images"] = images
            messages.append(user_payload)

            res = self.client.chat(
                model=self.model_id,
                messages=messages,
                format=schema or "json",
                options=options,
            )
            return res.message.content or ""

        raw = _call(prompt)
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            # One automatic retry with strict formatting instruction
            retry_msg = f"{prompt}\n\nCRITICAL: Return ONLY valid raw JSON conforming strictly to schema."
            raw_retry = _call(retry_msg)
            try:
                return json.loads(raw_retry)
            except (json.JSONDecodeError, TypeError) as err:
                raise ExtractionError(
                    f"Ollama ({self.model_id}) produced invalid JSON after retry: {raw_retry[:200]}"
                ) from err


class GeminiBackend:
    """Cloud inference via Google GenAI SDK (Gemini API)."""

    def __init__(
        self,
        model: str = "gemma-4-31b-it",
        api_key: str | None = None,
        temperature: float = 0.0,
        client: genai.Client | None = None,
    ):
        self.name = "gemini"
        self.model_id = model
        self.temperature = temperature
        resolved_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not resolved_key and client is None:
            raise ExtractionError("GEMINI_API_KEY environment variable is not set")
        self.client = client or genai.Client(api_key=resolved_key)

    def generate_json(
        self,
        *,
        system: str,
        prompt: str,
        images: list[bytes] | None = None,
        schema: dict[str, Any] | None = None,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
            system_instruction=system if system else None,
            temperature=temperature,
        )

        def _call(user_text: str) -> str:
            contents: list[Any] = [user_text]
            if images:
                for img in images:
                    contents.append(types.Part.from_bytes(data=img, mime_type="image/png"))
            res = self.client.models.generate_content(
                model=self.model_id,
                contents=contents,
                config=config,
            )
            return res.text or "{}"

        raw = _call(prompt)
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            # One automatic retry with strict formatting instruction
            retry_text = f"{prompt}\n\nCRITICAL: Output was not valid JSON. Return ONLY valid JSON."
            raw_retry = _call(retry_text)
            try:
                return json.loads(raw_retry)
            except (json.JSONDecodeError, TypeError) as err:
                raise ExtractionError(
                    f"Gemini ({self.model_id}) produced invalid JSON after retry: {raw_retry[:200]}"
                ) from err


def load_config(config_path: Path | str | None = None) -> dict[str, Any]:
    """Load config.toml or return empty dict if missing."""
    path = Path(config_path) if config_path else Path("config.toml")
    if path.exists():
        return tomllib.loads(path.read_text(encoding="utf-8"))
    return {}


def choose_backend(
    cfg: dict[str, Any] | None = None,
    *,
    confidential: bool = False,
    backend_override: str | None = None,
    replay: bool = False,
    cache_dir: Path | str = ".cache",
) -> Backend:
    """Route to backend per configuration and security rules.

    Hard rule: confidential=True NEVER returns a cloud backend.
    """
    if cfg is None:
        cfg = load_config()

    local_cfg = cfg.get("backends", {}).get("local", {})
    cloud_cfg = cfg.get("backends", {}).get("cloud", {})
    routing_cfg = cfg.get("routing", {})

    target = (backend_override or routing_cfg.get("default", "auto")).lower()

    if confidential:
        if target == "cloud":
            raise ValueError("Confidential mode strictly forbids cloud backend routing.")
        target = "local"

    if target == "cloud":
        backend: Backend = GeminiBackend(
            model=cloud_cfg.get("extract_model", "gemma-4-31b-it"),
            api_key=os.environ.get(cloud_cfg.get("api_key_env", "GEMINI_API_KEY")),
            temperature=cloud_cfg.get("temperature", 0.0),
        )
    elif target == "local":
        backend = OllamaBackend(
            model=local_cfg.get("extract_model", "gemma4:e4b"),
            host=local_cfg.get("host", "http://localhost:11434"),
            num_ctx=local_cfg.get("num_ctx", 4096),
        )
    elif target == "auto":
        api_key = os.environ.get(cloud_cfg.get("api_key_env", "GEMINI_API_KEY"))
        if api_key and not confidential:
            backend = GeminiBackend(
                model=cloud_cfg.get("extract_model", "gemma-4-31b-it"),
                api_key=api_key,
                temperature=cloud_cfg.get("temperature", 0.0),
            )
        else:
            backend = OllamaBackend(
                model=local_cfg.get("extract_model", "gemma4:e4b"),
                host=local_cfg.get("host", "http://localhost:11434"),
                num_ctx=local_cfg.get("num_ctx", 4096),
            )
    else:
        raise ValueError(f"Unknown backend target: {target}")

    return CachedBackend(backend, cache_dir=cache_dir, replay=replay)
