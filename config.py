"""
Application configuration via pydantic-settings.
All values loaded from environment / .env file.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # OpenAI
    openai_api_key: str

    # Vapi
    vapi_api_key: str
    vapi_phone_number_id: str
    vapi_assistant_id: str | None = None
    vapi_server_public_base_url: str | None = None

    # ElevenLabs
    elevenlabs_voice_id: str
    elevenlabs_voice_id_male: str | None = None
    elevenlabs_voice_id_female: str | None = None

    # App
    app_env: str = "development"
    log_level: str = "INFO"
    frontend_origin: str = "http://localhost:5173"
    rate_limit_per_minute: int = 10

    # Web search tool
    web_search_provider: str = "tavily"
    web_search_api_key: str | None = None
    web_search_timeout_seconds: float = 10.0


settings = Settings()
