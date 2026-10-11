"""Tests for configuration parsing and default settings."""

from cedar_lane_ai.config import Settings


def test_default_settings() -> None:
    """Verify default configuration values."""
    cfg = Settings(
        _env_file=None,
        gemini_api_key="mock-key",
        use_mock_integrations=True,
    )
    assert cfg.gemini_model == "gemini-2.5-flash"
    assert cfg.gemini_api_key == "mock-key"
    assert cfg.use_mock_integrations is True
    assert cfg.port == 8000
    assert cfg.host == "0.0.0.0"
    assert cfg.google_calendar_id == "primary"
