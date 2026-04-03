"""
Configuration loaded from environment variables.
Uses Pydantic Settings for type-safe config.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from .env file or environment variables."""

    # Anthropic
    anthropic_api_key: str
    claude_model: str = "claude-sonnet-4-20250514"

    # GitHub
    github_token: str
    github_repo: str = ""

    # Agent settings
    max_files_per_review: int = 20
    max_diff_lines: int = 500
    review_confidence_threshold: str = "medium"  # low, medium, high

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Singleton — import this everywhere
settings = Settings()
