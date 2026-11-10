"""Explicit root dotenv loading, with secret-free public configuration."""
import os
from pathlib import Path
from typing import Literal
from dotenv import load_dotenv
from pydantic import BaseModel, Field, SecretStr

DEFAULT_MODEL = 'claude-opus-5-5'

class AISettings(BaseModel):
    enabled: bool = False
    provider: Literal['anthropic'] = 'anthropic'
    model: str = DEFAULT_MODEL
    api_key: SecretStr = Field(default=SecretStr(''), exclude=True)
    thinking_level: Literal['low', 'medium', 'high'] = Field(default='medium', description='Sent as output_config.effort; thinking itself is adaptive.')
    max_calls: int = Field(default=7, ge=3, le=10)
    max_publications: int = Field(default=4, ge=1, le=10)
    max_trials: int = Field(default=6, ge=1, le=20)
    excerpt_chars: int = Field(default=2400, ge=500, le=4000)
    max_output_tokens: int = Field(default=16000, ge=512, le=32000, description='max_tokens per call; adaptive thinking is counted inside it.')
    timeout_seconds: int = Field(default=120, ge=5, le=120)
    retries: int = Field(default=1, ge=0, le=1)
    planning_call: bool = Field(default=False, description='Allow one extra Claude evidence-planning call (search terms only) when deterministic follow-up leaves needs open.')

def load_ai_settings(env_file: Path | None = None) -> AISettings:
    load_dotenv(env_file or Path(__file__).resolve().parents[2] / '.env', override=False)
    return AISettings(enabled=os.getenv('AI_ENABLED', 'false').lower() == 'true',
        model=os.getenv('AI_MODEL', '').strip() or DEFAULT_MODEL,
        api_key=SecretStr(os.getenv('ANTHROPIC_API_KEY', '')),
        thinking_level=os.getenv('AI_THINKING_LEVEL', 'medium').lower(),
        planning_call=os.getenv('AI_PLANNING_CALL', 'false').lower() == 'true',
        **{field: os.environ[env] for field, env in {
            'max_calls': 'AI_MAX_CALLS', 'max_publications': 'AI_MAX_PUBLICATIONS',
            'max_trials': 'AI_MAX_TRIALS', 'excerpt_chars': 'AI_EXCERPT_CHARS',
            'max_output_tokens': 'AI_MAX_OUTPUT_TOKENS', 'timeout_seconds': 'AI_TIMEOUT_SECONDS',
            'retries': 'AI_RETRIES'}.items() if env in os.environ})
