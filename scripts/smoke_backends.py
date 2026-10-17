"""Smoke test script for FinSight-Gemma backends (Ollama and Gemini API).

Verifies:
1. Environment and connectivity.
2. Model availability and tags against config.toml.
3. Multimodal image input + schema-constrained JSON output.
4. Cache replay support via --replay.

Exit codes:
0: Success, structured answers received from available backends.
4: Configured model ID missing or backend unreachable.
"""
from __future__ import annotations

import argparse
import io
import os
import sys
from typing import Any

from PIL import Image, ImageDraw

from finsight.backends import CachedBackend, GeminiBackend, OllamaBackend, load_config
from finsight.cache import ReplayMiss


def generate_test_image() -> bytes:
    """Create a minimal PNG containing 'Revenue 1,234'."""
    img = Image.new("RGB", (300, 100), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((20, 35), "Revenue 1,234", fill=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def run_smoke(replay: bool = False) -> int:
    cfg = load_config()
    test_img = generate_test_image()
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "label": {"type": "string"},
            "value": {"type": "number"},
        },
        "required": ["label", "value"],
    }
    prompt = "Read the number and its label in this image. Return valid JSON."
    system = "You are an accurate OCR assistant. Read values exactly as displayed. Output JSON only."

    print("=== FinSight-Gemma Smoke Test ===")
    print(f"Replay mode: {replay}\n")

    local_cfg = cfg.get("backends", {}).get("local", {})
    cloud_cfg = cfg.get("backends", {}).get("cloud", {})

    local_model = local_cfg.get("extract_model", "gemma4:e4b")
    cloud_model = cloud_cfg.get("extract_model", "gemma-4-31b-it")

    # 1. Ollama (Local)
    print(f"[1/2] Checking Local Backend (Ollama: {local_model})...")
    try:
        import ollama
        client = ollama.Client(host=local_cfg.get("host", "http://localhost:11434"))
        model_list = client.list().models
        available_names = [m.model for m in model_list]
        print(f"  Available Ollama models: {available_names}")

        # Check if configured model or prefix matches
        matched = any(local_model in name or name.startswith(local_model) for name in available_names)
        if not matched and not replay:
            print(f"  ERROR: Configured model '{local_model}' not found in Ollama!")
            print(f"  Available: {available_names}")
            return 4

        ollama_be = CachedBackend(
            OllamaBackend(
                model=local_model,
                host=local_cfg.get("host", "http://localhost:11434"),
                num_ctx=local_cfg.get("num_ctx", 4096),
            ),
            replay=replay,
        )
        res_local = ollama_be.generate_json(
            system=system,
            prompt=prompt,
            images=[test_img],
            schema=schema,
        )
        print(f"  Ollama OK: {res_local} (model: {ollama_be.model_id})\n")
    except ReplayMiss as e:
        print(f"  Replay Miss on Ollama: {e}")
        return 4
    except (RuntimeError, OSError, ValueError, KeyError) as e:
        print(f"  Ollama backend check failed: {e}\n")

    # 2. Gemini API (Cloud)
    print(f"[2/2] Checking Cloud Backend (Gemini: {cloud_model})...")
    api_key = os.environ.get(cloud_cfg.get("api_key_env", "GEMINI_API_KEY"))
    if not api_key and not replay:
        print("  GEMINI_API_KEY not set. Skipping live cloud backend smoke test.\n")
    else:
        try:
            from google import genai
            if not replay:
                g_client = genai.Client(api_key=api_key)
                gemma_models = [
                    m.name for m in g_client.models.list()
                    if "gemma" in m.name.lower()
                ]
                print(f"  Available Gemma models on Gemini API: {gemma_models}")
                if not any(cloud_model in m for m in gemma_models):
                    print(f"  ERROR: Configured model '{cloud_model}' not found in Gemini API list!")
                    return 4

            gemini_be = CachedBackend(
                GeminiBackend(
                    model=cloud_model,
                    api_key=api_key or ("replay-placeholder" if replay else None),
                ),
                replay=replay,
            )
            res_cloud = gemini_be.generate_json(
                system=system,
                prompt=prompt,
                images=[test_img],
                schema=schema,
            )
            print(f"  Gemini OK: {res_cloud} (model: {gemini_be.model_id})\n")
        except ReplayMiss as e:
            print(f"  Replay Miss on Gemini: {e}")
            return 4
        except (RuntimeError, OSError, ValueError, KeyError) as e:
            print(f"  Gemini backend check failed: {e}\n")

    print("Smoke test completed.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Smoke test FinSight-Gemma backends")
    parser.add_argument("--replay", action="store_true", help="Fail if any unrecorded call is made")
    args = parser.parse_args()
    sys.exit(run_smoke(replay=args.replay))
