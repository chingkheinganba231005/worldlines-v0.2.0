#!/usr/bin/env python3
"""Export a reproducible standalone source package without credentials or runtime data."""
from pathlib import Path
import json
import shutil
import zipfile
ROOT=Path(__file__).resolve().parents[1]
output=ROOT/'dist/downloads/WORLDLINE_v0.1_Source.zip'
output.parent.mkdir(parents=True,exist_ok=True)
public_docs=ROOT/'dist/docs'
public_docs.mkdir(exist_ok=True)
for name in ['architecture_decision.md','mathematics.md','data_sources_and_rights.md','validation.md']:
    shutil.copyfile(ROOT/'docs'/name,public_docs/name)
for name in ['results.md','real_sample_results.md','protocol.md']:
    shutil.copyfile(ROOT/'research'/name,public_docs/name)
skip_dirs={'.git','.openai','.venv','node_modules','__pycache__','.pytest_cache','.mypy_cache','downloads'}
count=0
with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
    for path in sorted(ROOT.rglob('*')):
        rel=path.relative_to(ROOT)
        if not path.is_file() or any(part in skip_dirs or part.endswith('.egg-info') for part in rel.parts): continue
        if rel.parts[:2]==('data','raw') or path.name=='.env' or '.sqlite' in path.name or path.suffix in {'.tmp','.gz'}:continue
        info=zipfile.ZipInfo(str(Path('worldline-observer')/rel),date_time=(2026,10,14,0,0,0))
        info.compress_type=zipfile.ZIP_DEFLATED
        info.external_attr=0o644<<16
        archive.writestr(info,path.read_bytes())
        count+=1
print(json.dumps({'source_zip':str(output),'files':count,'bytes':output.stat().st_size}))
