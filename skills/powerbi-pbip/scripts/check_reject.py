"""A field bound to a role the visual type does not own must abort the build.

Run from anywhere:  python3 scripts/check_reject.py
"""
import json
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
GEN = ROOT / "scripts" / "pbipgen.py"

spec = json.loads((ROOT / "examples" / "finance" / "spec.json").read_text(encoding="utf-8"))
spec["csv"] = str(ROOT / "examples" / "finance" / "data" / "fin.csv")
spec["visuals"] = [{"name": "bad", "type": "card", "category": "Fin[年份]"}]

with tempfile.TemporaryDirectory() as d:
    spec["out"] = str(pathlib.Path(d) / "build")
    f = pathlib.Path(d) / "bad.json"
    f.write_text(json.dumps(spec), encoding="utf-8")
    r = subprocess.run([sys.executable, str(GEN), str(f)], capture_output=True, text=True)
    if r.returncode == 0:
        raise SystemExit("expected a non-zero exit: 'card' has no Category role")
    print(r.stderr.strip().splitlines()[-1])
