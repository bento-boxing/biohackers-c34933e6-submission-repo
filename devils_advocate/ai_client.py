"""Official Interactions SDK transport; every request consumes the call budget."""
import json
import time
from pydantic import BaseModel, ValidationError
from .ai_config import AISettings
from .models import AICall

class AIError(RuntimeError):
    pass

def safe_error(exc: Exception) -> tuple[str, bool]:
    code = getattr(exc, 'code', None) or getattr(exc, 'status_code', None)
    messages = {400: 'Request rejected; check model configuration and output schema.',
                401: 'Authentication failed.', 403: 'Model access denied; check permissions and key restrictions.',
                404: 'Configured model unavailable or inaccessible.', 429: 'Quota, billing or rate limit prevented reasoning.'}
    kind = type(exc).__name__
    diagnostic = {'TimeoutError': 'Gemini request timed out.', 'ReadTimeout': 'Gemini response timed out.',
                  'ConnectTimeout': 'Gemini connection timed out.', 'ConnectError': 'Gemini connection could not be established.',
                  'APIConnectionError': 'Gemini connection could not be established.',
                  'APITimeoutError': 'Gemini response timed out.'}.get(kind, 'Gemini request failed.')
    # Class names are local SDK metadata; exception text/body/URLs remain private.
    diagnostic += f' Error type: {kind}. Raw SDK details withheld.'
    message = messages.get(code, diagnostic) if isinstance(code, int) else diagnostic
    return message, isinstance(code, int) and code in [429, 500, 502, 503, 504]

class GeminiRunner:
    def __init__(self, settings: AISettings, on_progress=None, should_cancel=None):
        self.settings = settings
        self.calls: list[AICall] = []
        self.client = None
        self.on_progress = on_progress
        self.should_cancel = should_cancel

    def _progress(self):
        if self.on_progress:
            try:
                self.on_progress(self.calls)
            except Exception:
                pass  # A display callback must not change the scientific result.

    def generate(self, role: str, instruction: str, payload: dict, schema: type[BaseModel]):
        if not self.settings.model or not self.settings.api_key.get_secret_value():
            raise AIError('Gemini model or private key is not configured. No model substituted.')
        for attempt in range(self.settings.retries + 1):
            if self.should_cancel and self.should_cancel():
                raise AIError('Cancellation requested; no further model call made. An in-flight request may still be billed.')
            if len(self.calls) >= self.settings.max_calls:
                raise AIError('Paid-call budget exhausted; no additional model call made.')
            call = AICall(role=role, success=False)
            self.calls.append(call)
            self._progress()
            try:
                if self.client is None:
                    from google import genai
                    self.client = genai.Client(api_key=self.settings.api_key.get_secret_value(),
                        http_options={'timeout': self.settings.timeout_seconds * 1000, 'retry_options': {'attempts': 1}})
                response = self.client.interactions.create(model=self.settings.model,
                    system_instruction=instruction, input=json.dumps(payload, ensure_ascii=False),
                    store=False, automatic_continuation=False,
                    timeout=self.settings.timeout_seconds,
                    generation_config={'thinking_level': self.settings.thinking_level,
                                       'max_output_tokens': self.settings.max_output_tokens},
                    response_format=[{'type': 'text', 'mime_type': 'application/json',
                                      'schema': schema.model_json_schema()}])
                usage = getattr(response, 'usage', None)
                for field in ['total_input_tokens', 'total_output_tokens', 'total_thought_tokens', 'total_tokens', 'total_cached_tokens']:
                    value = getattr(usage, field, None)
                    if isinstance(value, int):
                        call.usage[field] = value
                if response.status != 'completed':
                    raise AIError('Gemini response incomplete; output was not accepted. Check output-token limit.')
                parsed = schema.model_validate_json(response.output_text)
                call.success = True
                return parsed
            except AIError as exc:
                call.error = str(exc)  # Only our own fixed diagnostics.
                raise
            except (ValidationError, json.JSONDecodeError):
                call.error = 'Gemini returned invalid structured output; response rejected.'
                raise AIError(call.error) from None
            except Exception as exc:
                call.error, retryable = safe_error(exc)
                if not retryable or attempt == self.settings.retries:
                    raise AIError(call.error) from None
                time.sleep(0.5)
            finally:
                self._progress()
        raise AIError('Gemini request did not complete.')

    def close(self):
        if self.client is not None:
            self.client.close()
