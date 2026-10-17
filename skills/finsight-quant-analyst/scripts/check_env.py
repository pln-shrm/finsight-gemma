#!/usr/bin/env python3
"""Verify the environment before running the FinSight workflow. Exit 0 if ready."""
import importlib.util
import os
import shutil
import sys

ok = True
if sys.version_info < (3, 11):
    print("FAIL python>=3.11 required"); ok = False
if importlib.util.find_spec("finsight") is None:
    print("FAIL finsight not installed: run `pip install -e .` from the repo root"); ok = False
else:
    print("OK   finsight package importable")
local = shutil.which("ollama") is not None
cloud = bool(os.environ.get("GEMINI_API_KEY"))
print(f"{'OK  ' if local else 'WARN'} ollama binary {'found' if local else 'not found'}")
print(f"{'OK  ' if cloud else 'WARN'} GEMINI_API_KEY {'set' if cloud else 'not set'}")
if not (local or cloud):
    print("FAIL need Ollama or GEMINI_API_KEY for extraction (math commands still work)"); ok = False
sys.exit(0 if ok else 1)
