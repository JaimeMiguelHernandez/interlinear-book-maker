#!/usr/bin/env python3
"""
Daily batch runner for the 50-chapter translate -> verify -> render pipeline.

Tracks completed chapters in data/interim/batch_state.json so it can be
re-run daily (e.g. via Task Scheduler) and pick up where it left off.
Stops for the day as soon as Claude reports its usage limit.
"""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = PROJECT_ROOT / "data" / "interim" / "batch_state.json"
WAIT_SECONDS = 300  # 5 minutes between chapters


def load_scopes() -> list[str]:
    book_path = PROJECT_ROOT / "data" / "interim" / "book.json"
    book = json.loads(book_path.read_text(encoding="utf-8"))
    all_scopes = []
    for teil in book["teile"]:
        for kap in teil["kapitel"]:
            all_scopes.append(f"T{teil['number']}.K{kap['number']:02d}")
    return [s for s in all_scopes if s != "T1.K01"]  # T1.K01 already published


def load_state() -> dict:
    if STATE_PATH.is_file():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"completed": []}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def run_stage(stage: str, scope: str, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["uv", "run", "interlinear-book-maker", stage, "--scope", scope],
        capture_output=True, text=True, env=env, cwd=str(PROJECT_ROOT), timeout=3600,
    )


def is_quota_error(stderr: str) -> bool:
    return "usage limit" in stderr.lower()


def main() -> int:
    if not shutil.which("claude"):
        print("ERROR: claude CLI not found on PATH", file=sys.stderr)
        return 1

    scopes = load_scopes()
    state = load_state()
    completed = set(state["completed"])
    remaining = [s for s in scopes if s not in completed]

    print(f"{len(completed)}/{len(scopes)} chapters already done. "
          f"{len(remaining)} remaining.")

    if not remaining:
        print("All chapters complete.")
        return 0

    env = os.environ.copy()
    failed = []

    for i, scope in enumerate(remaining, 1):
        print(f"[{i}/{len(remaining)}] {scope}", end="", flush=True)

        result = run_stage("translate", scope, env)
        if result.returncode != 0:
            if is_quota_error(result.stderr):
                print(" -> QUOTA EXHAUSTED, stopping for today", flush=True)
                save_state(state)
                return 2
            print(" -> TRANSLATE FAILED", flush=True)
            failed.append(scope)
            continue
        print(" T:OK", end="", flush=True)

        result = run_stage("verify", scope, env)
        if result.returncode != 0:
            print(" V:FAIL", flush=True)
            failed.append(scope)
            continue
        print(" V:OK", end="", flush=True)

        result = run_stage("render", scope, env)
        if result.returncode != 0:
            print(" R:FAIL", flush=True)
            failed.append(scope)
            continue
        print(" R:OK", flush=True)

        state["completed"].append(scope)
        save_state(state)

        if i < len(remaining):
            print(f"  (waiting {WAIT_SECONDS // 60}m)", flush=True)
            time.sleep(WAIT_SECONDS)

    print()
    print(f"Done for today: {len(state['completed'])}/{len(scopes)} total complete.")
    if failed:
        print(f"Failed (non-quota): {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
