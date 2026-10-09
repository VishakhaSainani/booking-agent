"""Pytest configuration and global fixtures.

Ensures test safety: sets dummy API keys and forces mock integrations during tests
to prevent unauthorized external API requests.
"""

import os

import pytest

# Ensure safe testing environment
os.environ["GEMINI_API_KEY"] = "mock-gemini-key-for-testing"
os.environ["USE_MOCK_INTEGRATIONS"] = "true"


@pytest.fixture(autouse=True)
def safe_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Enforce mock settings for all unit tests."""
    monkeypatch.setenv("GEMINI_API_KEY", "mock-gemini-key-for-testing")
    monkeypatch.setenv("USE_MOCK_INTEGRATIONS", "true")
