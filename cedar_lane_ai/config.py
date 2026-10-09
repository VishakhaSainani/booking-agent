"""Configuration management for Cedar Lane Auto Detailing AI Receptionist.

Uses Pydantic Settings to automatically parse and validate environment variables
from `.env` or system environment.
"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings and runtime configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM Settings (Google Gemini)
    gemini_api_key: str = Field(
        default="",
        description="Google Gemini API key for LLM tool calling",
    )
    gemini_model: str = Field(
        default="gemini-2.5-flash",
        description="Gemini model name",
    )

    # Google Integrations
    use_mock_integrations: bool = Field(
        default=True,
        description="Whether to use in-memory mock adapters for Calendar & Sheets",
    )
    google_service_account_file: Path = Field(
        default=Path("credentials.json"),
        description="Path to Google Cloud Service Account JSON credentials file",
    )
    google_calendar_id: str = Field(
        default="primary",
        description="Google Calendar ID for Cedar Lane appointments",
    )
    google_sheets_spreadsheet_id: str = Field(
        default="",
        description="Google Sheets spreadsheet ID for customer directory and logs",
    )

    # Server Settings
    port: int = Field(default=8000, description="Web server port")
    host: str = Field(default="0.0.0.0", description="Web server host")
    debug: bool = Field(default=True, description="Enable debug mode")

    # Vapi Settings (Phase 2)
    vapi_api_key: str = Field(default="", description="Vapi API key for voice webhook")
    vapi_phone_number_id: str = Field(default="", description="Vapi phone number ID")


# Global singleton instance for settings
settings = Settings()
