from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "data" / "demo.db"
ACTIVE = ROOT / "data" / "impercontrol.db"

if not DEMO.exists():
    raise SystemExit("data/demo.db does not exist. Run scripts/create_demo_db.py first.")

for suffix in ("", "-wal", "-shm"):
    path = Path(str(ACTIVE) + suffix)
    if path.exists():
        path.unlink()

shutil.copy2(DEMO, ACTIVE)
print(f"Demo restored to: {ACTIVE}")
