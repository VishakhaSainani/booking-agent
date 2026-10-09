"""Tests for configuration parsing and default settings."""

from cedar_lane_ai.config import Settings


def test_default_settings() -> None:
    """Verify default configuration values."""
    cfg = Settings(
        openai_api_key="mock-key",
        use_mock_integrations=True,
    )
    assert cfg.openai_model == "gpt-4o-mini"
    assert cfg.use_mock_integrations is True
    assert cfg.port == 8000
    assert cfg.host == "0.0.0.0"
    assert cfg.google_calendar_id == "primary"
