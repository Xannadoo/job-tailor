"""
Configuration for job-tailor.

Reads from environment variables (see .env.example) with sensible
local defaults, so it runs out of the box against a local LiteLLM
proxy without any setup beyond having the proxy running.
"""

import os

# LiteLLM proxy endpoint. LiteLLM exposes an OpenAI-compatible API,
# so we talk to it the same way regardless of the underlying model
# (qwen-coder:14b via Ollama, in this case).
LITELLM_BASE_URL = os.environ.get("LITELLM_BASE_URL", "http://localhost:4000")

# The model name as registered in your LiteLLM proxy config, not
# necessarily the raw Ollama model tag.
MODEL_NAME = os.environ.get("JOB_TAILOR_MODEL", "qwen-coder-14b")

# LiteLLM proxy key, if you've set one up (optional for a fully local
# setup with no auth, but the client requires *some* value).
API_KEY = os.environ.get("LITELLM_API_KEY", "sk-local-not-needed")

# Paths
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")

CAREER_MASTER_DOC_PATH = os.path.join(DATA_DIR, "career_master_doc.md")

# Generation settings. Kept conservative and deterministic-ish for a
# POC where reproducibility while iterating on prompts matters more
# than creative variety.
TEMPERATURE = float(os.environ.get("JOB_TAILOR_TEMPERATURE", "0.4"))
MAX_TOKENS = int(os.environ.get("JOB_TAILOR_MAX_TOKENS", "2000"))
