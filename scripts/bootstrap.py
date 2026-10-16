#!/usr/bin/env python3
"""Build an offline demo and initialize durable SQLite snapshot storage."""
from pathlib import Path
import json
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from worldline.storage import Store
subprocess.run([sys.executable,str(ROOT/'scripts/replay.py')],check=True,cwd=ROOT)
snapshot=json.loads((ROOT/'dist/data/demo.json').read_text())
db=Store(ROOT/'data/worldline.sqlite')
checksum=db.save_snapshot(snapshot)
print(json.dumps({'database':'data/worldline.sqlite','snapshot_checksum':checksum,'mode':snapshot['mode']}))
