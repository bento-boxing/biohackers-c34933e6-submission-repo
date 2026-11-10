"""Official Anthropic SDK transport (Messages API); every request consumes the call budget."""
import json
import time
from pydantic import BaseModel, ValidationError
from .ai_config import AISettings
from .models import AICall

class AIError(RuntimeError):
    pass

def trim_to_schema(data, schema: dict, definitions: dict | None = None):
    """Structured outputs guarantee enums and object shapes but not string/list length caps.
    Cut over-long strings and lists to the schema's declared limits instead of rejecting the whole response."""
    definitions = definitions if definitions is not None else schema.get('$defs', {})
    while '$ref' in schema:
        schema = definitions.get(schema['$ref'].rsplit('/', 1)[-1], {})
    if isinstance(data, str) and isinstance(schema.get('maxLength'), int):
        return data[:schema['maxLength']]
    if isinstance(data, list):
        items = schema.get('items', {})
        if isinstance(schema.get('maxItems'), int):
            data = data[:schema['maxItems']]
        return [trim_to_schema(item, items, definitions) for item in data]
    if isinstance(data, dict):
        properties = schema.get('properties', {})
        return {key: trim_to_schema(value, properties.get(key, {}), definitions) for key, value in data.items()}
    return data

def safe_error(exc: Exception) -> tuple[str, bool]:
    code = getattr(exc, 'status_code', None) or getattr(exc, 'code', None)
    messages = {400: 'Request rejected; check model configuration and output schema.',
                401: 'Authentication failed.', 403: 'Model access denied; check permissions and key restrictions.',
                404: 'Configured model unavailable or inaccessible.', 429: 'Quota, billing or rate limit prevented reasoning.'}
    kind = type(exc).__name__
    diagnostic = {'TimeoutError': 'Claude request timed out.', 'ReadTimeout': 'Claude response timed out.',
                  'ConnectTimeout': 'Claude connection timed out.', 'ConnectError': 'Claude connection could not be established.',
                  'APIConnectionError': 'Claude connection could not be established.',
                  'APITimeoutError': 'Claude response timed out.'}.get(kind, 'Claude request failed.')
    # Class names are local SDK metadata; exception text/body/URLs remain private.
    diagnostic += f' Error type: {kind}. Raw SDK details withheld.'
    message = messages.get(code, diagnostic) if isinstance(code, int) else diagnostic
    return message, isinstance(code, int) and code in [429, 500, 502, 503, 504, 529]

# Models whose safety classifiers can decline a request and that accept the server-side fallback:
# on a decline the API re-runs the same request on a fallback model inside the same call.
FALLBACK_BETA = 'server-side-fallback-2026-07-01'
FALLBACK_MODELS = ('claude-opus-5', 'claude-sonnet-5-5', 'claude-fable-5-1', 'claude-fable-5-2')
USAGE_FIELDS = ['input_tokens', 'output_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens']

def request_options(settings: AISettings, schema: dict) -> dict:
    """Model, effort (thinking is adaptive and always on), the JSON schema the reply must satisfy, and refusal fallback."""
    options = {'model': settings.model, 'max_tokens': settings.max_output_tokens,
               'output_config': {'effort': settings.thinking_level, 'format': {'type': 'json_schema', 'schema': schema}}}
    if settings.model.startswith(FALLBACK_MODELS):
        options.update(betas=[FALLBACK_BETA], fallbacks='default')
    return options

def output_text(response) -> str:
    return ''.join(block.text for block in response.content if block.type == 'text')

class ClaudeRunner:
    DEADLINE_MARGIN_SECONDS = 5   # left for parsing, verification and the response itself
    MINIMUM_CALL_SECONDS = 15     # a shorter window cannot finish a thinking call; do not bill it

    def __init__(self, settings: AISettings, on_progress=None, should_cancel=None, deadline: float | None = None):
        self.settings = settings
        self.calls: list[AICall] = []
        self.client = None
        self.on_progress = on_progress
        self.should_cancel = should_cancel
        self.deadline = deadline  # time.monotonic() value after which the whole request is lost (Vercel kill)

    def _call_timeout(self) -> int:
        """Per-call timeout: the configured limit, or whatever the request deadline still allows."""
        if self.deadline is None:
            return self.settings.timeout_seconds
        remaining = self.deadline - time.monotonic() - self.DEADLINE_MARGIN_SECONDS
        if remaining < self.MINIMUM_CALL_SECONDS:
            raise AIError('Request deadline too close to finish another model call; no further call made.')
        return max(5, min(self.settings.timeout_seconds, int(remaining)))

    def _progress(self):
        if self.on_progress:
            try:
                self.on_progress(self.calls)
            except Exception:
                pass  # A display callback must not change the scientific result.

    def generate(self, role: str, instruction: str, payload: dict, schema: type[BaseModel]):
        if not self.settings.model or not self.settings.api_key.get_secret_value():
            raise AIError('Claude model or private key is not configured. No model substituted.')
        for attempt in range(self.settings.retries + 1):
            if self.should_cancel and self.should_cancel():
                raise AIError('Cancellation requested; no further model call made. An in-flight request may still be billed.')
            if len(self.calls) >= self.settings.max_calls:
                raise AIError('Paid-call budget exhausted; no additional model call made.')
            timeout = self._call_timeout()
            wire_payload = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
            started = time.monotonic()
            call = AICall(role=role, success=False, started_at=time.time(), payload_bytes=len(wire_payload.encode('utf-8')))
            self.calls.append(call)
            self._progress()
            try:
                import anthropic
                if self.client is None:
                    # max_retries=0: this loop owns retries so every attempt is counted against the call budget.
                    self.client = anthropic.Anthropic(api_key=self.settings.api_key.get_secret_value(),
                        timeout=self.settings.timeout_seconds, max_retries=0)
                response = self.client.beta.messages.create(
                    **request_options(self.settings, anthropic.transform_schema(schema)),
                    system=instruction, messages=[{'role': 'user', 'content': wire_payload}], timeout=timeout)
                usage = getattr(response, 'usage', None)
                for field in USAGE_FIELDS:
                    value = getattr(usage, field, None)
                    if isinstance(value, int):
                        call.usage[field] = value
                if response.stop_reason == 'refusal':
                    raise AIError('Claude declined this request; output was not accepted.')
                if response.stop_reason != 'end_turn':
                    raise AIError('Claude response incomplete; output was not accepted. Check output-token limit.')
                text = output_text(response)
                try:
                    parsed = schema.model_validate_json(text)
                except ValidationError:
                    parsed = schema.model_validate(trim_to_schema(json.loads(text), schema.model_json_schema()))
                call.success = True
                return parsed
            except AIError as exc:
                call.error = str(exc)  # Only our own fixed diagnostics.
                raise
            except (ValidationError, json.JSONDecodeError):
                call.error = 'Claude returned invalid structured output; response rejected.'
                if attempt == self.settings.retries:
                    raise AIError(call.error) from None
            except Exception as exc:
                call.error, retryable = safe_error(exc)
                if not retryable or attempt == self.settings.retries:
                    raise AIError(call.error) from None
                time.sleep(0.5)
            finally:
                call.duration_seconds = round(time.monotonic() - started, 6)
                self._progress()
        raise AIError('Claude request did not complete.')

    def close(self):
        if self.client is not None:
            self.client.close()
