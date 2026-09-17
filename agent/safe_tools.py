from pathlib import Path
import subprocess
import shutil
import tempfile


WORKSPACE = (
    Path.home()
    / "MMSerimAgentLab"
    / "workspace"
).resolve()


def safe_path(relative_path: str) -> Path:
    target = (WORKSPACE / relative_path).resolve()

    if not target.is_relative_to(WORKSPACE):
        raise PermissionError(
            "ACCESS DENIED: path is outside workspace."
        )

    return target


def list_files() -> str:
    files = []

    for path in WORKSPACE.rglob("*"):
        relative = path.relative_to(WORKSPACE)

        if ".git" in relative.parts:
            continue

        if path.is_file():
            files.append(str(relative))

    return "\n".join(sorted(files)) or "Workspace is empty."


def read_file(path: str) -> str:
    target = safe_path(path)

    if not target.exists():
        return f"File does not exist: {path}"

    if not target.is_file():
        return f"Not a file: {path}"

    return target.read_text(encoding="utf-8")


def write_file(path: str, content: str) -> str:
    target = safe_path(path)

    if target.exists():
        return (
            "WRITE BLOCKED: file already exists. "
            "Use replace_text, insert_before, insert_after "
            "or append_text instead."
        )

    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    target.write_text(
        content,
        encoding="utf-8",
    )

    return f"Successfully created: {path}"


def replace_text(path: str, old: str, new: str) -> str:
    target = safe_path(path)
    text = target.read_text(encoding="utf-8")

    count = text.count(old)

    if count == 0:
        return "PATCH FAILED: target text not found."

    if count > 1:
        return (
            f"PATCH REJECTED: target occurs {count} times. "
            "Use a more specific marker."
        )

    target.write_text(
        text.replace(old, new, 1),
        encoding="utf-8",
    )

    return f"PATCH APPLIED: replaced text in {path}"


def insert_before(path: str, marker: str, content: str) -> str:
    target = safe_path(path)
    text = target.read_text(encoding="utf-8")

    count = text.count(marker)

    if count == 0:
        return "PATCH FAILED: marker not found."

    if count > 1:
        return (
            f"PATCH REJECTED: marker occurs {count} times."
        )

    target.write_text(
        text.replace(
            marker,
            content + marker,
            1,
        ),
        encoding="utf-8",
    )

    return f"PATCH APPLIED: inserted before marker in {path}"


def insert_after(path: str, marker: str, content: str) -> str:
    target = safe_path(path)
    text = target.read_text(encoding="utf-8")

    count = text.count(marker)

    if count == 0:
        return "PATCH FAILED: marker not found."

    if count > 1:
        return (
            f"PATCH REJECTED: marker occurs {count} times."
        )

    target.write_text(
        text.replace(
            marker,
            marker + content,
            1,
        ),
        encoding="utf-8",
    )

    return f"PATCH APPLIED: inserted after marker in {path}"


def append_text(path: str, content: str) -> str:
    target = safe_path(path)

    with target.open(
        "a",
        encoding="utf-8",
    ) as f:
        f.write(content)

    return f"PATCH APPLIED: appended to {path}"


def snapshot_workspace():
    temp = Path(
        tempfile.mkdtemp(
            prefix="mmserim-agent-snapshot-"
        )
    )

    for path in WORKSPACE.rglob("*"):
        relative = path.relative_to(WORKSPACE)

        if ".git" in relative.parts:
            continue

        destination = temp / relative

        if path.is_dir():
            destination.mkdir(
                parents=True,
                exist_ok=True,
            )

        elif path.is_file():
            destination.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            shutil.copy2(
                path,
                destination,
            )

    return temp


def restore_snapshot(snapshot: Path):
    for path in WORKSPACE.iterdir():
        if path.name == ".git":
            continue

        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()

    for path in snapshot.rglob("*"):
        relative = path.relative_to(snapshot)
        destination = WORKSPACE / relative

        if path.is_dir():
            destination.mkdir(
                parents=True,
                exist_ok=True,
            )

        elif path.is_file():
            destination.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            shutil.copy2(
                path,
                destination,
            )


def _run_git(args, timeout=10):
    try:
        return subprocess.run(
            ["git", *args],
            cwd=WORKSPACE,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return None
    except subprocess.TimeoutExpired:
        return None


def git_status() -> str:
    result = _run_git(["status", "--short"])

    if result is None:
        return "GIT ERROR: git is not available or timed out."

    if result.returncode != 0:
        return "GIT ERROR:\n" + result.stderr

    return result.stdout or "Working tree clean."


def git_commit(message: str) -> str:
    _run_git(["add", "."])

    result = _run_git(["commit", "-m", message])

    if result is None:
        return "GIT ERROR: git is not available or timed out."

    return (
        result.stdout
        + "\n"
        + result.stderr
    ).strip()
