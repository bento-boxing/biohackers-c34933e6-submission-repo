"""Small state boundary so invalidation is shared and testable."""
REPORT_VERSION = 2  # Presence-aware stop reasons require a fresh report.

def invalidate_results(state, request_key: tuple, *, force: bool = False) -> None:
    if force or state.get('request_key') != request_key:
        for key in ['result', 'experiment', 'researcher_decision', 'decision_rationale', 'researcher_approved']:
            state.pop(key, None)
    state['request_key'] = request_key
