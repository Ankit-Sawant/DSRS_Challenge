from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "output" / "agent_usage.json"


def main() -> int:
    if not PATH.exists():
        print("No output/agent_usage.json yet. Run the live agent first.")
        return 0
    payload = json.loads(PATH.read_text(encoding="utf-8"))
    print(json.dumps(payload.get("totals", {}), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
