"""Read-only progress snapshot for the frozen dynamic campaign."""
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import median

root = Path(__file__).resolve().parent
state = json.loads((root / 'dynamic_status.json').read_text(encoding='utf-8'))
protocol = json.loads((root / 'protocol.json').read_text(encoding='utf-8'))
covered = {f"{c['id']}_{activity}" for c in protocol['cases'] if c['category'] == 'covered_grid'
           for activity in ('passive', 'active')}
done = {k for k, v in state['tasks'].items() if v['status'] == 'complete'}
times = [v['wall_seconds'] for v in state['tasks'].values() if v['status'] == 'complete' and v['kind'] == 'truth']
out = {'campaign_status': state['status'], 'updated_utc': state.get('updated_utc'),
       'elapsed_minutes': (datetime.now(timezone.utc) - datetime.fromisoformat(state['started_utc'])).total_seconds() / 60,
       'counts': dict(Counter(v['kind'] + ':' + v['status'] for v in state['tasks'].values())),
       'covered_truths_completed': len(covered & done), 'covered_truths_expected': len(covered),
       'truths_expected': len(protocol['cases']) * 2,
       'branches_expected': sum(c['policy'] for c in protocol['cases']) * 2 * len(protocol['policy']['decision_times_min']) * protocol['policy']['command_points'],
       'median_completed_truth_seconds': median(times) if times else None,
       'running': [k for k, v in state['tasks'].items() if v['status'] == 'running'],
       'failures': [{'key': k, 'status': v['status'], 'error': v.get('error')} for k, v in state['tasks'].items() if 'failure' in v['status']]}
print(json.dumps(out, indent=2))
