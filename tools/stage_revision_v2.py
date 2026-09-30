"""Stage the major-revision-v2 evidence (30 Sep - 1 Oct 2026) into revision_v2/ of this repository.

Copies an allowlist from the local working tree; excludes raw state arrays, per-batch trajectories,
copyrighted paper PDFs/texts and publisher responses, caches. Writes revision_v2/STAGING_MANIFEST.json
with a SHA-256 per copied file and the list of excluded top-level items so the omission is explicit.
Run:  python tools/stage_revision_v2.py
"""
import os, shutil, hashlib, json, fnmatch
from pathlib import Path

SRC = Path(r"C:\Users\Admin\Desktop\WHEC\reviews\ssmr_external_20260930\major_revision_v2")
DST = Path(__file__).resolve().parents[1] / "revision_v2"

EXCLUDE_DIRS = {"dynamic_branches", "dynamic_truth", "dynamic_forensic_results", "dynamic_smoke_results",
                "dynamic_portability_smoke_source", "sources", "reference", "__pycache__", "batches", "banks",
                "branches", "literature", "internal_fulltext", "qa", ".research"}
EXCLUDE_GLOBS = ["board.jsonl", "*.npz", "*.npy", "*.mat", "*.pyc", "*.log", "*.response", "*.html", "*.png", "*.pdf.bak"]
KEEP_ANYWAY = {  # files inside excluded dirs that are safe and useful
    "amendment_feed_only_20260930/literature/prior_work_trace.txt",
    "amendment_feed_only_20260930/literature/fulltext_access_manifest.json",
    "amendment_equal_ethanol_20260930/note/tradeoff.png",
}

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def wanted(rel: Path):
    s = rel.as_posix()
    if s in KEEP_ANYWAY: return True
    if any(part in EXCLUDE_DIRS for part in rel.parts[:-1]): return False
    return not any(fnmatch.fnmatch(rel.name, g) for g in EXCLUDE_GLOBS)

if DST.exists(): shutil.rmtree(DST)
copied, excluded_top = {}, sorted(d for d in os.listdir(SRC) if d in EXCLUDE_DIRS or d.startswith("dynamic_"))
for root, dirs, files in os.walk(SRC):
    for f in files:
        p = Path(root) / f; rel = p.relative_to(SRC)
        if not wanted(rel): continue
        out = DST / rel; out.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(p, out)
        copied[rel.as_posix()] = {"sha256": sha(out), "bytes": out.stat().st_size}
total = sum(v["bytes"] for v in copied.values())
manifest = {"source_tree": str(SRC), "files": copied, "n_files": len(copied), "total_bytes": total,
            "excluded_top_level_items": excluded_top,
            "excluded_patterns": {"dirs": sorted(EXCLUDE_DIRS), "globs": EXCLUDE_GLOBS},
            "note": "Raw per-episode state arrays (dynamic_branches, dynamic_truth, results/batches, amendment */branches) are "
                    "retained on the author's machine only; every table in the note is rebuilt from the CSV/JSON files staged here. "
                    "Third-party paper PDFs and texts are not redistributed."}
(DST / "STAGING_MANIFEST.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
print(f"{len(copied)} files, {total/1e6:.1f} MB -> {DST}")
big = sorted(copied.items(), key=lambda kv: -kv[1]["bytes"])[:8]
for k, v in big: print(f"  {v['bytes']/1e6:6.1f} MB  {k}")
