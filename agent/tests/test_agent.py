"""Offline tests: safe tools + the full agent loop driven by a scripted fake model.

    cd agent && .venv/bin/python -m unittest discover tests -v
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

AGENT_DIR = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="quantrophic-test-"))
WS = TMP / "workspace"
shutil.copytree(AGENT_DIR.parent / "workspace", WS)
os.environ["QUANTROPHIC_WORKSPACE"] = str(WS)
sys.path.insert(0, str(AGENT_DIR))

import agent  # noqa: E402
import browser_verify  # noqa: E402
import config  # noqa: E402
import safe_tools  # noqa: E402

config.RUNS = TMP / "runs"
browser_verify.ARTIFACTS = TMP / "artifacts"  # keep test screenshots out of the repo


def git(*args):
    subprocess.run(["git", *args], cwd=WS, check=True, capture_output=True)


git("init", "-q")
git("-c", "user.email=t@t", "-c", "user.name=t", "add", ".")
git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "base")

TERMINAL = (
    '<section class="terminal-panel" style="height:120px;overflow-y:auto">'
    '<div class="terminal-header">Terminal</div>'
    '<pre class="terminal-output">$ npm run dev\n> ready on :5173</pre>'
    '<div class="terminal-prompt">$ _</div></section>\n    '
)


def reply(tool, **args):
    call = SimpleNamespace(function=SimpleNamespace(name=tool, arguments=args))
    return SimpleNamespace(message={"role": "assistant", "content": "", "tool_calls": [call]})


def as_obj(resp):
    msg = resp.message
    return SimpleNamespace(message=SimpleNamespace(
        role="assistant", content=msg["content"], tool_calls=msg["tool_calls"]))


class SafeToolsTest(unittest.TestCase):
    def test_path_escape_blocked(self):
        with self.assertRaises(PermissionError):
            safe_tools.read_file("../agent/agent.py")
        with self.assertRaises(PermissionError):
            safe_tools.read_file(".git/config")

    def test_empty_marker_rejected(self):
        with self.assertRaises(ValueError):
            safe_tools.insert_after("index.html", "", "x")

    def test_ambiguous_marker_rejected(self):
        self.assertIn("REJECTED", safe_tools.insert_after("index.html", "<div", "x"))

    def test_alias_normalisation(self):
        self.assertEqual(
            agent.normalize_args("replace_text", {"file": "a", "search": "b", "replacement": "c"}),
            {"path": "a", "old": "b", "new": "c"},
        )


class AgentLoopTest(unittest.TestCase):
    def test_rollback_then_success(self):
        script = [
            reply("read_file", path="index.html"),
            # regression: deletes the preview panel -> must be rolled back
            reply("replace_text", path="index.html",
                  old='<div class="preview-panel">', new='<div class="gone">'),
            # the real fix
            reply("insert_before", path="index.html",
                  marker='<footer class="status-bar">', content=TERMINAL),
        ]
        with mock.patch.object(agent, "safe_chat", side_effect=lambda *a: as_obj(script.pop(0))):
            code = agent.run(config.load_milestone("m05_terminal.json"), "fake", max_steps=5, commit=True)

        self.assertEqual(code, 0)
        html = (WS / "index.html").read_text()
        self.assertIn('class="preview-panel"', html)   # regression was undone
        self.assertIn("terminal-panel", html)
        log = subprocess.run(["git", "log", "--oneline"], cwd=WS, capture_output=True, text=True).stdout
        self.assertIn("Milestone 5", log)


if __name__ == "__main__":
    unittest.main()
