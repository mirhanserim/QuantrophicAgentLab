from pathlib import Path
import subprocess
import shutil
import tempfile


from config import WORKSPACE


def safe_path(relative_path: str) -> Path:
    if not relative_path or not str(relative_path).strip():
        raise ValueError("path is required.")

    target = (WORKSPACE / relative_path).resolve()

    if not target.is_relative_to(WORKSPACE):
        raise PermissionError(
            "ACCESS DENIED: path is outside workspace."
        )

    if ".git" in target.relative_to(WORKSPACE).parts:
        raise PermissionError(
            "ACCESS DENIED: .git is off-limits."
        )

    return target


def list_files() -> str:
    """List every file in the workspace (relative paths)."""
    files = []

    for path in WORKSPACE.rglob("*"):
        relative = path.relative_to(WORKSPACE)

        if ".git" in relative.parts:
            continue

        if path.is_file():
            files.append(str(relative))

    return "\n".join(sorted(files)) or "Workspace is empty."


def read_file(path: str) -> str:
    """Read a workspace file.

    Args:
        path: file path relative to the workspace, e.g. "index.html"
    """
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


def _load_for_patch(path: str, marker: str, what: str):
    if not marker:
        raise ValueError(f"{what} must be non-empty exact file text.")

    target = safe_path(path)

    if not target.is_file():
        raise FileNotFoundError(f"File does not exist: {path}")

    return target, target.read_text(encoding="utf-8")


def replace_text(path: str, old: str, new: str) -> str:
    """Replace ONE exact, unique occurrence of text in a file.

    Args:
        path: file path relative to the workspace
        old: exact literal text currently in the file (must occur once)
        new: replacement text
    """
    if old == new:
        return "PATCH REJECTED: old and new are identical."

    target, text = _load_for_patch(path, old, "old")

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
    """Insert content before ONE exact, unique marker in a file.

    Args:
        path: file path relative to the workspace
        marker: exact literal text currently in the file (not a CSS selector)
        content: text to insert
    """
    if not content:
        return "PATCH REJECTED: content is empty."

    target, text = _load_for_patch(path, marker, "marker")

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
    """Insert content after ONE exact, unique marker in a file.

    Args:
        path: file path relative to the workspace
        marker: exact literal text currently in the file (not a CSS selector)
        content: text to insert
    """
    if not content:
        return "PATCH REJECTED: content is empty."

    target, text = _load_for_patch(path, marker, "marker")

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
    """Append content to the end of an existing file.

    Args:
        path: file path relative to the workspace
        content: text to append
    """
    if not content:
        return "PATCH REJECTED: content is empty."

    target = safe_path(path)

    if not target.is_file():
        return f"PATCH FAILED: file does not exist: {path}"

    with target.open(
        "a",
        encoding="utf-8",
    ) as f:
        f.write(content)

    return f"PATCH APPLIED: appended to {path}"


def snapshot_workspace():
    temp = Path(
        tempfile.mkdtemp(
            prefix="quantrophic-agent-snapshot-"
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
    # Scoped to the workspace: it is a subtree of the parent repo, so an
    # unscoped status would also report unrelated changes under agent/.
    result = _run_git(["status", "--short", "--", "."])

    if result is None:
        return "GIT ERROR: git is not available or timed out."

    if result.returncode != 0:
        return "GIT ERROR:\n" + result.stderr

    return result.stdout or "Working tree clean."


def git_commit(message: str) -> str:
    _run_git(["add", "--", "."])

    # Commit only workspace paths, even if something else is staged.
    result = _run_git(["commit", "-m", message, "--", "."])

    if result is None:
        return "GIT ERROR: git is not available or timed out."

    return (
        result.stdout
        + "\n"
        + result.stderr
    ).strip()
