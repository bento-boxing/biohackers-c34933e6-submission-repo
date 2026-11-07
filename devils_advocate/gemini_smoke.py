"""One short, explicit Gemini connection check. Never prints credentials or SDK errors."""
import json
import os
from pathlib import Path

def main() -> int:
    from dotenv import load_dotenv
    from google import genai

    load_dotenv(Path(__file__).resolve().parents[1] / '.env', override=False)
    model = os.getenv('AI_MODEL', '').strip()
    key = os.getenv('GEMINI_API_KEY', '').strip()
    result = {'model': model, 'success': False}
    if not key or not model:
        result['error'] = 'Missing GEMINI_API_KEY or AI_MODEL configuration.'
        print(json.dumps(result))
        return 1
    if os.getenv('AI_PROVIDER', '').lower() != 'google':
        result['error'] = 'AI_PROVIDER must be google for this connection check.'
        print(json.dumps(result))
        return 1
    level = os.getenv('AI_THINKING_LEVEL', 'medium').lower()
    if level not in ['low', 'medium', 'high']:
        result['error'] = 'Unsupported thinking level; use low, medium or high.'
        print(json.dumps(result))
        return 1
    try:
        with genai.Client(api_key=key, http_options={'timeout': 30000, 'retry_options': {'attempts': 1}}) as client:
            response = client.interactions.create(model=model,
                input='Connection test only. Reply with exactly OK.', store=False,
                generation_config={'thinking_level': level, 'max_output_tokens': 512})
            result['success'] = response.status == 'completed' and response.output_text.strip() == 'OK'
            if not result['success']:
                result['error'] = 'Model did not return the expected completed test response.'
    except Exception as exc:
        # SDK errors may contain request URLs or credentials. Emit only a status
        # code and a fixed diagnostic; never stringify the exception or response.
        code = getattr(exc, 'code', None) or getattr(exc, 'status_code', None)
        safe_code = code if isinstance(code, int) else None
        result['error_code'] = safe_code
        result['error'] = {
            400: 'Request or API-key configuration rejected.',
            401: 'Authentication failed; check the private API key.',
            403: 'Permission denied; check model access and API-key restrictions.',
            404: 'Configured model unavailable through this API or inaccessible to this project.',
            429: 'Quota, billing or rate limit prevented the test.',
        }.get(safe_code, 'Connection or SDK error; no raw error details printed.')
    print(json.dumps(result))
    return 0 if result['success'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
