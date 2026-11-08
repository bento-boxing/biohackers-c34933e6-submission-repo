"""Explicit root dotenv loading, with secret-free public configuration."""
import os
from pathlib import Path
from typing import Literal
from dotenv import load_dotenv
from pydantic import BaseModel, Field, SecretStr

class AISettings(BaseModel):
    enabled: bool = False
    provider: Literal['google'] = 'google'
    model: str = ''
    api_key: SecretStr = Field(default=SecretStr(''), exclude=True)
    thinking_level: Literal['low', 'medium', 'high'] = 'medium'
    max_calls: int = Field(default=5, ge=3, le=10)
    max_publications: int = Field(default=4, ge=1, le=10)
    max_trials: int = Field(default=6, ge=1, le=20)
    excerpt_chars: int = Field(default=2400, ge=500, le=4000)
    max_output_tokens: int = Field(default=8192, ge=512, le=16384)
    timeout_seconds: int = Field(default=120, ge=5, le=120)
    retries: int = Field(default=1, ge=0, le=1)

def load_ai_settings(env_file: Path | None = None) -> AISettings:
    load_dotenv(env_file or Path(__file__).resolve().parents[2] / '.env', override=False)
    return AISettings(enabled=os.getenv('AI_ENABLED', 'false').lower() == 'true',
        provider=os.getenv('AI_PROVIDER', 'google'), model=os.getenv('AI_MODEL', '').strip(),
        api_key=SecretStr(os.getenv('GEMINI_API_KEY', '')),
        thinking_level=os.getenv('AI_THINKING_LEVEL', 'medium').lower(),
        **{field: os.environ[env] for field, env in {
            'max_calls': 'AI_MAX_CALLS', 'max_publications': 'AI_MAX_PUBLICATIONS',
            'max_trials': 'AI_MAX_TRIALS', 'excerpt_chars': 'AI_EXCERPT_CHARS',
            'max_output_tokens': 'AI_MAX_OUTPUT_TOKENS', 'timeout_seconds': 'AI_TIMEOUT_SECONDS',
            'retries': 'AI_RETRIES'}.items() if env in os.environ})
