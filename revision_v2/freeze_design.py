"""Freeze pre-evaluation design, source identities and diagnostic implementation."""
from pathlib import Path
import json, hashlib, datetime
ROOT=Path(__file__).resolve().parent

def main():
    out=ROOT/'PROTOCOL_FREEZE.json'
    if out.exists(): raise RuntimeError('Design already frozen; preserve original and version any amendments.')
    assert not (ROOT/'results').exists(), 'Do not freeze after result generation'
    names=['protocol.json','make_protocol.py','revision_model.py','dynamics.py','SOURCE_MANIFEST.json']
    assert (ROOT/'checks/MATH_FREEZE.json').exists(), 'Independent math checks must be frozen first'
    names+=['checks/MATH_FREEZE.json']
    hashes={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in names}
    data={'schema':'ssmr.design-freeze.v2','frozen_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'files':hashes,'chronology':'Before any core/stress dynamic campaign or stochastic calibration/evaluation; engineering-only synthetic/healthy smokes and analytic checks precede this freeze.',
          'source_status':'Reference model/maps already checked in prior audit; no claim of new preregistration for historical results.'}
    out.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(data,indent=2))

if __name__=='__main__':main()
