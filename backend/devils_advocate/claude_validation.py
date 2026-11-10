"""Explicit paid end-to-end live test. Offline tests never invoke this module."""
from pathlib import Path
import json
from datetime import datetime, timezone
from .ai_reasoning import challenge_target
from .experiment_designer import propose_experiment

def main():
    def progress(calls):
        print(json.dumps({'role': calls[-1].role, 'completed': sum(c.success for c in calls), 'attempted': len(calls)}), flush=True)
    result = challenge_target({'disease_name': "Alzheimer's disease", 'target_symbol': 'BACE1'}, on_progress=progress)
    report = {'tested_at_utc': datetime.now(timezone.utc).isoformat(),
              'data_mode': result.mode, 'resolved_target_id': result.resolved_target_id,
              'compounds': len(result.compounds), 'trials': len(result.trials),
              'publications': len(result.publications), 'retrieval_errors': result.retrieval_errors,
              'ai': result.ai.model_dump(mode='json'),
              'selected_experiment': propose_experiment(result).model_dump(mode='json')}
    output = Path(__file__).parent / 'validation' / 'claude_report.json'
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    history_path = output.with_name('claude_validation_history.json')
    history = json.loads(history_path.read_text(encoding='utf-8')) if history_path.exists() else []
    history.append({'tested_at_utc': report['tested_at_utc'], 'model': result.ai.model,
                    'status': result.ai.status, 'calls_attempted': len(result.ai.calls),
                    'calls_completed': sum(c.success for c in result.ai.calls), 'warnings': result.ai.warnings})
    history_path.write_text(json.dumps(history, indent=2), encoding='utf-8')
    print(json.dumps({'model': result.ai.model, 'status': result.ai.status,
                      'calls_completed': sum(c.success for c in result.ai.calls),
                      'calls_attempted': len(result.ai.calls), 'rounds': len(result.ai.rounds),
                      'accepted_claims': len(result.ai.accepted_claims), 'warnings': result.ai.warnings}))
    if result.ai.status != 'completed':
        raise SystemExit(1)

if __name__ == '__main__':
    main()
