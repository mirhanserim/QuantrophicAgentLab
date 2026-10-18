"""Quantrophic Agent Lab — browser-gated autonomous builder.

A local LLM (via Ollama) extends a small web app one milestone at a time.
The model may only make small, exact-text patches; the runtime owns
everything else: Chromium verification, regression-aware rollback, git.

    python agent.py                              # latest milestone
    python agent.py --milestone m05_terminal.json
    python agent.py --verify-only                # just run the browser checks
"""

import argparse
import json
import shutil
import sys
import time
from datetime import datetime

import config
from browser_verify import regressions, run_browser_verification
from safe_tools import (
    append_text,
    git_commit,
    git_status,
    insert_after,
    insert_before,
    list_files,
    read_file,
    replace_text,
    restore_snapshot,
    snapshot_workspace,
)

READ_TOOLS = {"list_files": list_files, "read_file": read_file}
PATCH_TOOLS = {
    "replace_text": replace_text,
    "insert_before": insert_before,
    "insert_after": insert_after,
    "append_text": append_text,
}
TOOLS = [*READ_TOOLS.values(), *PATCH_TOOLS.values()]

# Argument names small models commonly invent, mapped to the real ones.
ALIASES = {
    "path": ["filename", "file", "file_path", "filepath"],
    "old": ["old_content", "target", "search", "find"],
    "new": ["new_content", "replacement", "content"],
    "marker": ["target", "anchor", "exact_text"],
    "content": ["text", "code", "new_content", "value"],
}
PARAMS = {
    "list_files": [],
    "read_file": ["path"],
    "replace_text": ["path", "old", "new"],
    "insert_before": ["path", "marker", "content"],
    "insert_after": ["path", "marker", "content"],
    "append_text": ["path", "content"],
}


def system_prompt(ms):
    bullets = lambda items: "\n".join(f"- {i}" for i in items) or "- (nothing yet)"
    return f"""You are the Quantrophic Builder repair worker for: {ms['title']}.

You are extending an EXISTING, browser-verified web app in the workspace.
The runtime owns validation, Chromium testing, rollback, git and completion.

Your loop:
1. inspect files (list_files, read_file)
2. read the latest browser report
3. make ONE SMALL PATCH (replace_text, insert_before, insert_after, append_text)
4. wait for runtime feedback

Rules:
- Never rewrite whole files.
- `old` / `marker` must be EXACT literal text that occurs once in the file, not a CSS selector.
- A patch that breaks any previously passing check is rolled back automatically.

Goal: {ms['goal']}

Required:
{bullets(ms.get('requirements', []))}

Preserve:
{bullets(ms.get('preserve', []))}
"""


def normalize_args(name, raw):
    if isinstance(raw, str):
        raw = json.loads(raw or "{}")
    args = dict(raw or {})
    for key in PARAMS.get(name, []):
        if key not in args:
            for alias in ALIASES[key]:
                if alias in args:
                    args[key] = args.pop(alias)
                    break
    if "marker" in PARAMS.get(name, []) and "marker" not in args and "selector" in args:
        raise ValueError("selector is invalid. Use exact literal file text as marker.")
    missing = [k for k in PARAMS.get(name, []) if k not in args]
    if missing:
        raise ValueError(f"missing argument(s) for {name}: {', '.join(missing)}")
    return {k: args[k] for k in PARAMS.get(name, [])}


def clip(text, limit=config.MAX_TOOL_OUTPUT):
    text = str(text)
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...[truncated {len(text) - limit} chars; read a smaller region]"


def signature(name, args):
    return name + ":" + json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)


def trimmed(messages):
    """System prompt + task + a recent window, so long runs fit in the context."""
    head, tail = messages[:2], messages[2:]
    if len(tail) <= config.KEEP_RECENT_MESSAGES:
        return messages
    tail = tail[-config.KEEP_RECENT_MESSAGES:]
    while tail and _role(tail[0]) == "tool":  # never start on an orphan tool result
        tail = tail[1:]
    return head + tail


def _role(message):
    return message["role"] if isinstance(message, dict) else getattr(message, "role", None)


def safe_chat(messages, model):
    from ollama import chat

    try:
        return chat(
            model=model,
            messages=trimmed(messages),
            tools=TOOLS,
            options={"num_ctx": config.NUM_CTX},
        )
    except Exception as exc:
        print(f"\nOLLAMA ERROR: {type(exc).__name__}: {exc}")
        print(f"Is `ollama serve` running and is '{model}' pulled? (ollama pull {model})")
        return None


def commit_ok(output):
    lower = output.lower()
    return any(t in lower for t in ("[main ", "file changed", "files changed", "insertion", "deletion"))


class RunLog:
    """JSON log of every step, written to artifacts/runs/ for later review."""

    def __init__(self, ms, model):
        config.RUNS.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.path = config.RUNS / f"{ms['slug']}-{stamp}.json"
        self.data = {"milestone": ms["slug"], "model": model, "started": stamp, "steps": [], "outcome": None}

    def step(self, **entry):
        self.data["steps"].append(entry)
        self.save()

    def finish(self, outcome, **extra):
        self.data.update(outcome=outcome, **extra)
        self.save()
        print(f"\nRun log: {self.path}")

    def save(self):
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")


def apply_patch(name, args, current, ms):
    """Apply one patch, verify it in Chromium, roll back on regression.

    Returns (feedback_for_model, new_current, accepted).
    """
    snapshot = snapshot_workspace()
    try:
        result = PATCH_TOOLS[name](**args)
        print(f"PATCH RESULT: {result}")
        if not result.startswith("PATCH APPLIED"):
            return result, current, False

        print("Running Chromium verifier...")
        after = run_browser_verification(ms)
        broken = regressions(current, after)

        if broken or after["failed"] > current["failed"]:
            restore_snapshot(snapshot)
            feedback = (
                "PATCH REJECTED AND AUTO-ROLLED BACK.\n"
                f"Failures: {current['failed']} -> {after['failed']}."
                + (f"\nBroke previously passing checks: {', '.join(broken)}" if broken else "")
                + "\n\n" + after["report"]
            )
            print(feedback.split("\n\n")[0])
            return feedback, current, False

        print(after["report"])
        return result + "\n\n" + after["report"], after, True
    finally:
        shutil.rmtree(snapshot, ignore_errors=True)


def run(ms, model, max_steps, commit=True):
    print("=" * 60)
    print(f"  Quantrophic Autonomous Builder — {ms['title']}")
    print(f"  model: {model}   workspace: {config.WORKSPACE}")
    print("=" * 60)

    status = git_status()
    if status != "Working tree clean.":
        print("ABORTED: workspace must be clean (commit or stash first).")
        print(status)
        return 2

    current = run_browser_verification(ms)
    print("\nBASELINE\n" + "=" * 40 + "\n" + current["report"])
    if current["failed"] == 0:
        print(f"\n{ms['title']} already passes.")
        return 0

    log = RunLog(ms, model)
    log.step(kind="baseline", passed=current["passed"], failed=current["failed"])
    messages = [
        {"role": "system", "content": system_prompt(ms)},
        {"role": "user", "content": (
            f"Complete {ms['title']}.\n\nCurrent browser report:\n{current['report']}"
            "\n\nInspect files and make ONE small patch."
        )},
    ]
    last_sig, repeat_count = None, 0
    started = time.time()

    for step in range(1, max_steps + 1):
        print(f"\n----- repair step {step}/{max_steps} -----")
        response = safe_chat(messages, model)
        if response is None:
            log.finish("ollama-error", step=step)
            return 3

        messages.append(response.message)
        if response.message.content:
            print("\nAGENT:\n" + response.message.content.strip())

        calls = list(response.message.tool_calls or [])
        if not calls:
            messages.append({"role": "user", "content": "Do not explain. Use ONE real tool call."})
            continue

        patch_done = False
        for call in calls:
            name = call.function.name
            print(f"\nTOOL CALL: {name} {call.function.arguments}")
            try:
                if name not in READ_TOOLS and name not in PATCH_TOOLS:
                    raise ValueError(f"Unknown tool: {name}. Available: {', '.join(PARAMS)}")
                args = normalize_args(name, call.function.arguments)

                if name in READ_TOOLS:
                    result = clip(READ_TOOLS[name](**args))
                elif patch_done:
                    result = "SKIPPED: only one patch is applied per step."
                else:
                    sig = signature(name, args)
                    repeat_count = repeat_count + 1 if sig == last_sig else 0
                    last_sig = sig
                    if repeat_count >= config.MAX_IDENTICAL_PATCH_ATTEMPTS:
                        result = "PATCH BLOCKED: identical patch repeated. Try a different approach."
                    else:
                        patch_done = True
                        result, current, accepted = apply_patch(name, args, current, ms)
                        log.step(kind="patch", step=step, tool=name, args=args, accepted=accepted,
                                 passed=current["passed"], failed=current["failed"])
            except Exception as exc:
                result = f"TOOL ERROR: {type(exc).__name__}: {exc}"
                print(result)

            messages.append({"role": "tool", "tool_name": name, "content": clip(result)})

            if current["failed"] == 0:
                print(f"\nALL CHECKS PASSED for {ms['title']}.")
                outcome = {"steps": step, "seconds": round(time.time() - started)}
                if commit:
                    out = git_commit(ms.get("commit_message", f"{ms['title']}: browser-verified"))
                    print("\nGIT COMMIT:\n" + out)
                    outcome["committed"] = commit_ok(out)
                log.finish("passed", **outcome)
                print(f"\n✅ {ms['title']} verified in {step} steps")
                return 0

        messages.append({"role": "user", "content": (
            "Continue fixing ONE remaining browser failure.\n\n" + current["report"]
        )})

    print(f"\n❌ Repair limit reached ({max_steps} steps).")
    log.finish("step-limit", failed=current["failed"])
    return 1


def main(argv=None):
    parser = argparse.ArgumentParser(description="Quantrophic browser-gated autonomous builder")
    parser.add_argument("--milestone", "-m", help="milestone JSON (default: latest in milestones/)")
    parser.add_argument("--model", default=config.MODEL, help=f"Ollama model (default: {config.MODEL})")
    parser.add_argument("--max-steps", type=int, default=config.MAX_STEPS)
    parser.add_argument("--no-commit", action="store_true", help="do not git-commit on success")
    parser.add_argument("--verify-only", action="store_true", help="run the browser checks and exit")
    opts = parser.parse_args(argv)

    ms = config.load_milestone(opts.milestone)
    if opts.verify_only:
        result = run_browser_verification(ms)
        print(f"{ms['title']}\n" + "=" * 40 + "\n" + result["report"])
        return 1 if result["failed"] else 0
    return run(ms, opts.model, opts.max_steps, commit=not opts.no_commit)


if __name__ == "__main__":
    sys.exit(main())
