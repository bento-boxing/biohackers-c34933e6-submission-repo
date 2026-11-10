"""One short, explicit Claude connection check. Never prints credentials or SDK errors."""
import json
import os
from pathlib import Path

def main() -> int:
    import anthropic
    from dotenv import load_dotenv
    from .ai_config import DEFAULT_MODEL

    load_dotenv(Path(__file__).resolve().parents[2] / '.env', override=False)
    model = os.getenv('AI_MODEL', '').strip() or DEFAULT_MODEL
    key = os.getenv('ANTHROPIC_API_KEY', '').strip()
    result = {'model': model, 'success': False}
    if not key:
        result['error'] = 'Missing ANTHROPIC_API_KEY configuration.'
        print(json.dumps(result))
        return 1
    level = os.getenv('AI_THINKING_LEVEL', 'medium').lower()
    if level not in ['low', 'medium', 'high']:
        result['error'] = 'Unsupported thinking level; use low, medium or high.'
        print(json.dumps(result))
        return 1
    try:
        with anthropic.Anthropic(api_key=key, timeout=30, max_retries=0) as client:
            response = client.messages.create(model=model, max_tokens=1024, output_config={'effort': level},
                messages=[{'role': 'user', 'content': 'Connection test only. Reply with exactly OK.'}])
            text = ''.join(block.text for block in response.content if block.type == 'text')
            result['success'] = response.stop_reason == 'end_turn' and text.strip() == 'OK'
            if not result['success']:
                result['error'] = 'Model did not return the expected completed test response.'
    except Exception as exc:
        # SDK errors may contain request URLs or credentials. Emit only a status
        # code and a fixed diagnostic; never stringify the exception or response.
        code = getattr(exc, 'status_code', None)
        safe_code = code if isinstance(code, int) else None
        result['error_code'] = safe_code
        result['error'] = {
            400: 'Request or model configuration rejected.',
            401: 'Authentication failed; check the private API key.',
            403: 'Permission denied; check model access and API-key restrictions.',
            404: 'Configured model unavailable through this API or inaccessible to this workspace.',
            429: 'Quota, billing or rate limit prevented the test.',
        }.get(safe_code, 'Connection or SDK error; no raw error details printed.')
    print(json.dumps(result))
    return 0 if result['success'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
