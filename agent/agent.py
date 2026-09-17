import json
import os
import shutil

from ollama import chat

from safe_tools import (
    list_files,
    read_file,
    replace_text,
    insert_before,
    insert_after,
    append_text,
    snapshot_workspace,
    restore_snapshot,
    git_status,
    git_commit,
)

from browser_verify import (
    run_browser_verification,
)


# ============================================================
# MILESTONE CONFIG
# The only section that should change between milestones.
# Copy this file for the next milestone and edit the values
# below (plus the matching checks in browser_verify.py)
# instead of rewriting the whole script.
# ============================================================
MILESTONE_NUMBER = 5
MILESTONE_GOAL = "Add a professional terminal panel."
MILESTONE_REQUIREMENTS = (
    "- terminal-panel\n"
    "- terminal-header\n"
    "- terminal-output\n"
    "- terminal-prompt\n"
    "- fake developer commands/output\n"
    "- vertically scrollable terminal area"
)
MILESTONE_PRESERVE = (
    "- File Explorer\n"
    "- Code Editor\n"
    "- Preview\n"
    "- editor tabs\n"
    "- active-file\n"
    "- line numbers\n"
    "- status\n"
    "- counter\n"
    "- existing JavaScript behavior"
)
COMMIT_MESSAGE = (
    f"Milestone {MILESTONE_NUMBER}: browser-verified terminal panel"
)
# ============================================================

MODEL = os.environ.get("MMSERIM_MODEL", "qwen3:8b")
MAX_STEPS = 60
MAX_IDENTICAL_PATCH_ATTEMPTS = 2


TOOLS = [
    list_files,
    read_file,
    replace_text,
    insert_before,
    insert_after,
    append_text,
]


SYSTEM_PROMPT = f"""
You are MMSerim Builder Milestone {MILESTONE_NUMBER} Repair Worker.

You are extending an EXISTING browser-verified IDE prototype.

Runtime controls:
- validation
- Chromium testing
- rollback
- Git
- completion

Your only job:
1. inspect files
2. read latest failures
3. make ONE SMALL PATCH
4. wait for runtime feedback

Never rewrite entire files.

Use only:
replace_text
insert_before
insert_after
append_text

marker must be EXACT literal file text,
not a CSS selector.

Preserve all Milestone {MILESTONE_NUMBER - 1} functionality.

Milestone {MILESTONE_NUMBER} goal:

{MILESTONE_GOAL}

Required:
{MILESTONE_REQUIREMENTS}

The terminal should look like part of an IDE.

Preserve:
{MILESTONE_PRESERVE}

Make ONE small patch per turn.
"""


def normalize_args(name, raw):
    args = dict(raw or {})

    if "path" not in args:
        for alias in [
            "filename",
            "file",
            "file_path",
            "filepath",
        ]:
            if alias in args:
                args["path"] = args.pop(alias)
                break

    if name == "replace_text":
        if "old" not in args:
            for alias in [
                "old_content",
                "target",
                "search",
                "find",
            ]:
                if alias in args:
                    args["old"] = args.pop(alias)
                    break

        if "new" not in args:
            for alias in [
                "new_content",
                "replacement",
                "content",
            ]:
                if alias in args:
                    args["new"] = args.pop(alias)
                    break

    if name in {
        "insert_before",
        "insert_after",
    }:
        if "marker" not in args:
            for alias in [
                "target",
                "anchor",
                "exact_text",
            ]:
                if alias in args:
                    args["marker"] = args.pop(alias)
                    break

        if (
            "marker" not in args
            and "selector" in args
        ):
            raise ValueError(
                "selector is invalid. "
                "Use exact literal file text."
            )

        if "content" not in args:
            for alias in [
                "text",
                "code",
                "new_content",
                "value",
            ]:
                if alias in args:
                    args["content"] = args.pop(alias)
                    break

    return args


def execute(name, raw):
    args = normalize_args(name, raw)

    if name == "list_files":
        return list_files()

    if name == "read_file":
        return read_file(args["path"])

    if name == "replace_text":
        return replace_text(
            args["path"],
            args["old"],
            args["new"],
        )

    if name == "insert_before":
        return insert_before(
            args["path"],
            args["marker"],
            args["content"],
        )

    if name == "insert_after":
        return insert_after(
            args["path"],
            args["marker"],
            args["content"],
        )

    if name == "append_text":
        return append_text(
            args["path"],
            args["content"],
        )

    return f"Unknown tool: {name}"


def commit_ok(output):
    lower = output.lower()

    return (
        "[main " in lower
        or "file changed" in lower
        or "files changed" in lower
        or "insertion" in lower
        or "deletion" in lower
    )


def signature(name, args):
    try:
        return (
            name
            + ":"
            + json.dumps(
                args,
                sort_keys=True,
                ensure_ascii=False,
            )
        )
    except Exception:
        return name + ":" + str(args)


def safe_chat(messages):
    try:
        return chat(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
        )
    except Exception as exc:
        print()
        print(
            f"OLLAMA ERROR: {type(exc).__name__}: {exc}"
        )
        print(
            "Is the Ollama server running and is "
            f"the model '{MODEL}' pulled?"
        )
        return None


def safe_browser_check():
    try:
        return run_browser_verification()
    except Exception as exc:
        return {
            "passed": 0,
            "failed": 1,
            "report": (
                "Browser verifier crashed: "
                f"{type(exc).__name__}: {exc}"
            ),
        }


def main():

    print(
        f"""
=========================================================
        MMSerim Milestone {MILESTONE_NUMBER} Autonomous Builder
        Browser-Gated Terminal Panel
=========================================================
"""
    )

    status = git_status()

    if status != "Working tree clean.":
        print("ABORTED: workspace must be clean.")
        print(status)
        return

    baseline = safe_browser_check()

    print()
    print("BASELINE")
    print("=" * 40)
    print(baseline["report"])

    if baseline["failed"] == 0:
        print(f"Milestone {MILESTONE_NUMBER} already passes.")
        return

    current = baseline

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": (
                f"Complete Milestone {MILESTONE_NUMBER}.\n\n"
                "Current browser report:\n"
                + current["report"]
                + "\n\nInspect files and make "
                "ONE small patch."
            ),
        },
    ]

    last_sig = None
    repeat_count = 0

    for step in range(1, MAX_STEPS + 1):

        print()
        print(
            f"----- milestone {MILESTONE_NUMBER} repair step {step} -----"
        )

        response = safe_chat(messages)

        if response is None:
            print("Aborting run after Ollama failure.")
            return

        messages.append(response.message)

        if response.message.content:
            print()
            print("AGENT:")
            print(response.message.content)

        calls = list(
            response.message.tool_calls
            or []
        )

        if not calls:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Do not explain. "
                        "Use ONE real patch tool."
                    ),
                }
            )
            continue

        patch_done = False

        for call in calls:

            name = call.function.name
            args = call.function.arguments

            print()
            print("TOOL CALL:")
            print(name)
            print(args)

            if (
                patch_done
                and name not in {
                    "read_file",
                    "list_files",
                }
            ):
                result = (
                    "SKIPPED: only one patch is applied "
                    "per step; a patch already succeeded "
                    "this turn."
                )

                print(result)

                messages.append(
                    {
                        "role": "tool",
                        "tool_name": name,
                        "content": result,
                    }
                )

                continue

            try:
                if name in {
                    "read_file",
                    "list_files",
                }:
                    result = execute(name, args)

                    print()
                    print("TOOL RESULT:")
                    print(result)

                    messages.append(
                        {
                            "role": "tool",
                            "tool_name": name,
                            "content": result,
                        }
                    )

                    continue

                sig = signature(name, args)

                if sig == last_sig:
                    repeat_count += 1
                else:
                    repeat_count = 0

                last_sig = sig

                if repeat_count >= MAX_IDENTICAL_PATCH_ATTEMPTS:
                    result = (
                        "PATCH BLOCKED: identical "
                        "patch repeated."
                    )

                    print(result)

                    messages.append(
                        {
                            "role": "tool",
                            "tool_name": name,
                            "content": result,
                        }
                    )

                    continue

                snapshot = snapshot_workspace()

                result = execute(name, args)

                patch_done = True

                print()
                print("PATCH RESULT:")
                print(result)

                if not result.startswith(
                    "PATCH APPLIED"
                ):
                    shutil.rmtree(
                        snapshot,
                        ignore_errors=True,
                    )

                    messages.append(
                        {
                            "role": "tool",
                            "tool_name": name,
                            "content": result,
                        }
                    )

                    continue

                print()
                print("Running Chromium verifier...")

                after = safe_browser_check()

                if after["failed"] > current["failed"]:

                    restore_snapshot(snapshot)

                    shutil.rmtree(
                        snapshot,
                        ignore_errors=True,
                    )

                    feedback = (
                        "PATCH REJECTED AND "
                        "AUTO-ROLLED BACK.\n"
                        f"Browser failures: "
                        f"{current['failed']} "
                        f"-> {after['failed']}."
                    )

                    print()
                    print(feedback)

                    messages.append(
                        {
                            "role": "tool",
                            "tool_name": name,
                            "content": feedback,
                        }
                    )

                    continue

                shutil.rmtree(
                    snapshot,
                    ignore_errors=True,
                )

                current = after

                print()
                print(current["report"])

                messages.append(
                    {
                        "role": "tool",
                        "tool_name": name,
                        "content": (
                            result
                            + "\n\n"
                            + current["report"]
                        ),
                    }
                )

                if current["failed"] == 0:

                    print()
                    print(
                        f"ALL MILESTONE {MILESTONE_NUMBER} "
                        "BROWSER TESTS PASSED."
                    )

                    commit = git_commit(COMMIT_MESSAGE)

                    print()
                    print("GIT COMMIT:")
                    print(commit)

                    if commit_ok(commit):
                        print()
                        print(
                            "================================="
                        )
                        print(
                            f"✅ MILESTONE {MILESTONE_NUMBER} FULLY VERIFIED"
                        )
                        print(
                            "✅ TERMINAL PANEL VERIFIED"
                        )
                        print(
                            "✅ PREVIOUS FEATURES PRESERVED"
                        )
                        print(
                            "✅ GIT COMMIT CREATED"
                        )
                        print(
                            "================================="
                        )
                        return

            except Exception as exc:
                result = (
                    f"TOOL ERROR: "
                    f"{type(exc).__name__}: "
                    f"{exc}"
                )

                print()
                print(result)

                messages.append(
                    {
                        "role": "tool",
                        "tool_name": name,
                        "content": result,
                    }
                )

        messages.append(
            {
                "role": "user",
                "content": (
                    "Continue fixing ONE remaining "
                    "browser failure.\n\n"
                    + current["report"]
                ),
            }
        )

    print()
    print(
        f"❌ Milestone {MILESTONE_NUMBER} repair limit reached."
    )


if __name__ == "__main__":
    main()
