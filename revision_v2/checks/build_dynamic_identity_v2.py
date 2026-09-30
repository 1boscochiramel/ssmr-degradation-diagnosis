"""Version a lookup-only correction; never modify the frozen original checker."""
from pathlib import Path
import hashlib,json,datetime

here=Path(__file__).resolve().parent
old=here/'verify_dynamic_records.py'
assert hashlib.sha256(old.read_bytes()).hexdigest()=='2956f2bf140285b84d48c4b94fbd21461adbcf6ebe053a889a269edb81bd2a6b'
text=old.read_text()
text=text.replace("parents[meta['state_sha256']]=(ts,xs,sc)","parents[(meta['state_sha256'],json.dumps(sc,sort_keys=True))]=(ts,xs,sc)")
text=text.replace("parent=parents.get(meta['parent_state_sha256'])", "parent=parents.get((meta['parent_state_sha256'],json.dumps(meta['scenario'],sort_keys=True)))")
new=here/'verify_dynamic_records_v2.py'
new.write_text(text)
# A collision is legitimate: a sensor-only bias does not change physical state.
# Correct lookup must retain both identities without changing any state gate.
scenarios=[dict(hypothesis='H',theta10=1),dict(hypothesis='S',theta10=-.0001)]
parents={("same-state-hash",json.dumps(sc,sort_keys=True)):sc for sc in scenarios}
assert all(parents[("same-state-hash",json.dumps(sc,sort_keys=True))]==sc for sc in scenarios)
assert parents.get(("same-state-hash",json.dumps(dict(hypothesis='C'),sort_keys=True))) is None
out=dict(schema='ssmr.checker-identity-amendment.v1',created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
  original_sha256=hashlib.sha256(old.read_bytes()).hexdigest(),corrected_sha256=hashlib.sha256(new.read_bytes()).hexdigest(),
  changes=['Parent lookup key includes canonical scenario as well as physical state hash.'],
  preserved='Every numerical, exact-state and physical-integral acceptance gate is unchanged; original checker and failure output preserved.',
  reason='Healthy and sensor-only cases legitimately share bit-identical physical state arrays. The original dictionary overwrote their different scenario identities.',
  synthetic_collision_test_pass=True,scientific_tolerance_changes=False)
(here/'DYNAMIC_IDENTITY_AMENDMENT.json').write_text(json.dumps(out,indent=2))
print(json.dumps(out,indent=2))
