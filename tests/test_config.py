"""Tests for configuration parsing and default settings."""

from cedar_lane_ai.config import Settings


def test_default_settings() -> None:
    """Verify default configuration values."""
    cfg = Settings(
        _env_file=None,
        groq_api_key="",
        gemini_api_key="mock-key",
        use_mock_integrations=True,
    )
    assert cfg.gemini_model == "gemini-2.5-flash"
    assert cfg.gemini_api_key == "mock-key"
    assert cfg.groq_model == "openai/gpt-oss-120b"
    assert cfg.groq_api_key == ""
    assert cfg.llm_provider == "groq"
    assert cfg.use_mock_integrations is True
    assert cfg.port == 8000
    assert cfg.host == "0.0.0.0"
    assert cfg.google_calendar_id == "primary"


def test_groq_settings_alias() -> None:
    """Verify Groq API key parsing from alias."""
    cfg = Settings(
        _env_file=None,
        groq="mock-groq-key",
        groq_model="openai/gpt-oss-120b",
    )
    assert cfg.groq_api_key == "mock-groq-key"
    assert cfg.groq_model == "openai/gpt-oss-120b"
