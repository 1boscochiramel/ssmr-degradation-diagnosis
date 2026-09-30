"""Map recorded source root to the supplied artifact root without rewriting data."""
from pathlib import Path,PurePosixPath
import json

def make_resolver(artifact_root):
 root=Path(artifact_root).resolve()
 metadata=sorted((root/'dynamic_truth').glob('*/metadata.json'))
 if not metadata:raise ValueError('No dynamic metadata to establish recorded source root')
 meta=json.loads(metadata[0].read_text())
 engines=[str(p).replace('\\','/') for p in meta['source_hashes'] if str(p).replace('\\','/').endswith('/dynamics.py')]
 if len(engines)!=1:raise ValueError('Ambiguous recorded engine source root')
 recorded_root=engines[0][:-len('/dynamics.py')]
 def resolve(recorded):return resolve_from_root(root,recorded_root,recorded)
 return resolve

def resolve_from_root(root,recorded_root,recorded):
 normalized=str(recorded).replace('\\','/')
 if not normalized.startswith(recorded_root+'/'):raise ValueError('Source outside explicitly recorded artifact root')
 relative=PurePosixPath(normalized[len(recorded_root)+1:])
 if relative.is_absolute() or '..' in relative.parts or any(':' in x for x in relative.parts):raise ValueError('Unsafe relative source path')
 target=Path(root).resolve().joinpath(*relative.parts).resolve()
 if not target.is_relative_to(Path(root).resolve()):raise ValueError('Source escapes supplied artifact root')
 return target

if __name__=='__main__':
 root=Path(__file__).resolve().parent.parent
 assert resolve_from_root(root,'C:/old/artifact','C:\\old\\artifact\\reference\\model.py')==root/'reference/model.py'
 for malformed in ['C:/else/model.py','C:/old/artifact/../secret','C:/old/artifact/C:/secret']:
  try:resolve_from_root(root,'C:/old/artifact',malformed)
  except ValueError:pass
  else:raise AssertionError('Accepted invalid path: '+malformed)
 print('PASS: source root relocation and three rejection fixtures')
