"""Paths, runtime settings and milestone loading.

Everything that used to be edited by hand between milestones now lives in
``milestones/*.json``; this module only resolves paths and env overrides.
"""

from pathlib import Path
import json
import os

AGENT_DIR = Path(__file__).resolve().parent
ROOT = AGENT_DIR.parent
WORKSPACE = Path(os.environ.get("QUANTROPHIC_WORKSPACE", ROOT / "workspace")).resolve()
ARTIFACTS = (AGENT_DIR / "artifacts").resolve()
RUNS = ARTIFACTS / "runs"
MILESTONES = AGENT_DIR / "milestones"

MODEL = os.environ.get("QUANTROPHIC_MODEL", "qwen3:8b")
# Ollama defaults to a small context window; the loop sends whole files.
NUM_CTX = int(os.environ.get("QUANTROPHIC_NUM_CTX", "16384"))
MAX_STEPS = int(os.environ.get("QUANTROPHIC_MAX_STEPS", "60"))
MAX_IDENTICAL_PATCH_ATTEMPTS = 2
MAX_TOOL_OUTPUT = 12000      # chars of a tool result sent back to the model
KEEP_RECENT_MESSAGES = 24    # history window after the system + task messages


def latest_milestone() -> Path:
    files = sorted(MILESTONES.glob("m*.json"))
    if not files:
        raise FileNotFoundError(f"No milestone files in {MILESTONES}")
    return files[-1]


def load_milestone(path=None) -> dict:
    """Load a milestone file; regression checks of earlier milestones are inherited."""
    path = Path(path) if path else latest_milestone()
    if not path.is_absolute() and not path.exists():
        path = MILESTONES / path
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("slug", path.stem)

    seen = {c["id"] for c in data.get("checks", [])}
    inherited = []
    for prev in sorted(MILESTONES.glob("m*.json")):
        if prev.name >= path.name:
            break
        for check in json.loads(prev.read_text(encoding="utf-8")).get("checks", []):
            if check["id"] not in seen:
                seen.add(check["id"])
                inherited.append(check)
    data["regression_checks"] = inherited
    return data
