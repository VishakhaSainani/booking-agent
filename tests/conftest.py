"""Pytest configuration and global fixtures.

Ensures test safety: sets dummy API keys and forces mock integrations during tests
to prevent unauthorized external API requests.
"""

import os

import pytest

# Ensure safe testing environment before config import
os.environ["GEMINI_API_KEY"] = "mock-gemini-key-for-testing"
os.environ["GROQ_API_KEY"] = "mock-groq-key-for-testing"
os.environ["groq"] = "mock-groq-key-for-testing"
os.environ["USE_MOCK_INTEGRATIONS"] = "true"

from cedar_lane_ai.config import settings  # noqa: E402

settings.gemini_api_key = "mock-gemini-key-for-testing"
settings.groq_api_key = "mock-groq-key-for-testing"


@pytest.fixture(autouse=True)
def safe_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Enforce mock settings for all unit tests."""
    monkeypatch.setenv("GEMINI_API_KEY", "mock-gemini-key-for-testing")
    monkeypatch.setenv("GROQ_API_KEY", "mock-groq-key-for-testing")
    monkeypatch.setenv("groq", "mock-groq-key-for-testing")
    monkeypatch.setenv("USE_MOCK_INTEGRATIONS", "true")
    settings.gemini_api_key = "mock-gemini-key-for-testing"
    settings.groq_api_key = "mock-groq-key-for-testing"
