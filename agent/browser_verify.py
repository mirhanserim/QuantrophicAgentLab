from pathlib import Path
from functools import partial
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from threading import Thread
import re
import time

from playwright.sync_api import sync_playwright


ROOT = Path.home() / "MMSerimAgentLab"
WORKSPACE = (ROOT / "workspace").resolve()
ARTIFACTS = (ROOT / "agent" / "artifacts").resolve()
ARTIFACTS.mkdir(parents=True, exist_ok=True)

# Update this per milestone (kept alongside agent.py's
# MILESTONE_NUMBER for easy discovery when copying this file).
SCREENSHOT_NAME = "milestone5-browser.png"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


def start_server():
    handler = partial(
        QuietHandler,
        directory=str(WORKSPACE),
    )

    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        handler,
    )

    thread = Thread(
        target=server.serve_forever,
        daemon=True,
    )
    thread.start()

    return server, server.server_address[1]


def run_browser_verification(save_screenshot=True):
    results = []
    console_errors = []
    page_errors = []

    def check(condition, success, failure):
        results.append(
            (
                bool(condition),
                success if condition else failure,
            )
        )

    server, port = start_server()
    time.sleep(0.2)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            try:
                page = browser.new_page(
                    viewport={
                        "width": 1440,
                        "height": 900,
                    }
                )

                page.on(
                    "console",
                    lambda msg: (
                        console_errors.append(msg.text)
                        if msg.type == "error"
                        else None
                    ),
                )

                page.on(
                    "pageerror",
                    lambda exc: page_errors.append(str(exc)),
                )

                response = page.goto(
                    f"http://127.0.0.1:{port}/index.html",
                    wait_until="networkidle",
                    timeout=15000,
                )

                check(
                    response is not None and response.ok,
                    "Page loads successfully.",
                    "Page does not load.",
                )

                # Base shell
                check(
                    page.get_by_text(
                        "MMSerim CodeSpace",
                        exact=False,
                    ).count() > 0,
                    "MMSerim CodeSpace branding visible.",
                    "MMSerim CodeSpace branding missing.",
                )

                check(
                    page.get_by_text(
                        "File Explorer",
                        exact=True,
                    ).count() > 0,
                    "File Explorer visible.",
                    "File Explorer missing.",
                )

                for filename in [
                    "index.html",
                    "style.css",
                    "script.js",
                ]:
                    check(
                        page.locator(
                            f'[data-file="{filename}"]'
                        ).count() > 0,
                        f"{filename} exists.",
                        f"{filename} missing.",
                    )

                script_entry = page.locator(
                    '.file-item[data-file="script.js"]'
                )

                if script_entry.count():
                    script_entry.first.click()

                    selected = script_entry.first.evaluate(
                        "el => el.classList.contains('selected')"
                    )

                    check(
                        selected,
                        "Explorer selection works.",
                        "Explorer selection broken.",
                    )

                # Editor
                editor = page.locator(".code-editor")
                tabs = page.locator(".editor-tabs")
                content = page.locator(".editor-content")
                active = page.locator(".active-file")

                check(
                    editor.count() > 0
                    and editor.first.is_visible(),
                    "Code editor visible.",
                    "Code editor missing/hidden.",
                )

                check(
                    tabs.count() > 0
                    and tabs.first.is_visible(),
                    "Editor tabs visible.",
                    "Editor tabs missing/hidden.",
                )

                check(
                    content.count() > 0
                    and content.first.is_visible(),
                    "Editor content visible.",
                    "Editor content missing/hidden.",
                )

                content_text = ""
                if content.count():
                    content_text = content.first.inner_text().strip()

                check(
                    bool(content_text),
                    "Editor contains visible sample code.",
                    "Editor content empty.",
                )

                line_numbers = page.locator(".line-numbers")
                line_text = ""

                if line_numbers.count():
                    line_text = line_numbers.first.inner_text().strip()

                numbers = re.findall(r"\b\d+\b", line_text)

                check(
                    line_numbers.count() > 0
                    and line_numbers.first.is_visible()
                    and len(numbers) >= 3,
                    "Visible line numbers contain numbers.",
                    "Line numbers missing/empty.",
                )

                active_text = ""

                if active.count():
                    active_text = active.first.inner_text().strip()

                check(
                    active.count() > 0
                    and active.first.is_visible()
                    and any(
                        f in active_text
                        for f in [
                            "index.html",
                            "style.css",
                            "script.js",
                        ]
                    ),
                    "Active file indicator works.",
                    "Active file indicator invalid.",
                )

                style_tab = page.locator(
                    '.editor-tabs [data-file="style.css"]'
                )

                if style_tab.count() and active.count():
                    before = active.first.inner_text()

                    style_tab.first.click()
                    page.wait_for_timeout(120)

                    after = active.first.inner_text()

                    check(
                        before != after
                        and "style.css" in after,
                        "Editor tab updates active file.",
                        "Editor tab does not update active file.",
                    )

                # Status/counter regression
                status_button = page.locator("#statusButton")
                status_message = page.locator("#statusMessage")

                if (
                    status_button.count()
                    and status_message.count()
                ):
                    before = status_message.first.inner_text()

                    status_button.first.click()
                    page.wait_for_timeout(120)

                    after = status_message.first.inner_text()

                    check(
                        before != after,
                        "Status button works.",
                        "Status button broken.",
                    )

                increment = page.locator("#incrementButton")
                counter = page.locator("#counter")

                if increment.count() and counter.count():
                    before = counter.first.inner_text()

                    increment.first.click()
                    page.wait_for_timeout(120)

                    after = counter.first.inner_text()

                    check(
                        before != after,
                        "Legacy counter works.",
                        "Legacy counter broken.",
                    )

                # Preview panel regression
                preview = page.locator(".preview-panel")
                preview_header = page.locator(".preview-header")
                preview_controls = page.locator(".preview-controls")
                preview_content = page.locator(".preview-content")

                check(
                    preview.count() > 0
                    and preview.first.is_visible(),
                    "Preview panel visible.",
                    "Preview panel missing/hidden.",
                )

                check(
                    preview_header.count() > 0
                    and preview_header.first.is_visible(),
                    "Preview header visible.",
                    "Preview header missing/hidden.",
                )

                check(
                    preview_controls.count() > 0
                    and preview_controls.first.is_visible(),
                    "Preview controls visible.",
                    "Preview controls missing/hidden.",
                )

                check(
                    preview_content.count() > 0
                    and preview_content.first.is_visible(),
                    "Preview content visible.",
                    "Preview content missing/hidden.",
                )

                # Milestone 5 Terminal
                terminal = page.locator(".terminal-panel")
                terminal_header = page.locator(".terminal-header")
                terminal_output = page.locator(".terminal-output")
                terminal_prompt = page.locator(".terminal-prompt")

                check(
                    terminal.count() > 0
                    and terminal.first.is_visible(),
                    "Terminal panel visible.",
                    "Terminal panel missing/hidden.",
                )

                check(
                    terminal_header.count() > 0
                    and terminal_header.first.is_visible(),
                    "Terminal header visible.",
                    "Terminal header missing/hidden.",
                )

                check(
                    terminal_output.count() > 0
                    and terminal_output.first.is_visible(),
                    "Terminal output visible.",
                    "Terminal output missing/hidden.",
                )

                terminal_text = ""

                if terminal_output.count():
                    terminal_text = (
                        terminal_output.first
                        .inner_text()
                        .strip()
                    )

                check(
                    "$" in terminal_text
                    or ">" in terminal_text,
                    "Terminal contains command-like output.",
                    "Terminal lacks command/output text.",
                )

                check(
                    terminal_prompt.count() > 0
                    and terminal_prompt.first.is_visible(),
                    "Terminal prompt visible.",
                    "Terminal prompt missing/hidden.",
                )

                if terminal.count():
                    overflow_y = terminal.first.evaluate(
                        """
                        el => getComputedStyle(el).overflowY
                        """
                    )

                    check(
                        overflow_y in {
                            "auto",
                            "scroll",
                        },
                        "Terminal is scrollable.",
                        "Terminal should be vertically scrollable.",
                    )

                # Health
                check(
                    not page_errors,
                    "No uncaught JavaScript errors.",
                    (
                        "JavaScript errors: "
                        + " | ".join(page_errors)
                    ),
                )

                check(
                    not console_errors,
                    "No console errors.",
                    (
                        "Console errors: "
                        + " | ".join(console_errors)
                    ),
                )

                if save_screenshot:
                    page.screenshot(
                        path=str(
                            ARTIFACTS
                            / SCREENSHOT_NAME
                        ),
                        full_page=True,
                    )
            finally:
                browser.close()

    except Exception as exc:
        results.append(
            (
                False,
                f"Browser verifier crashed: {exc}",
            )
        )

    finally:
        server.shutdown()

    passed = sum(
        1 for ok, _ in results if ok
    )

    failed = sum(
        1 for ok, _ in results if not ok
    )

    report = "\n".join(
        f"{'PASS' if ok else 'FAIL'}: {message}"
        for ok, message in results
    )

    report += (
        f"\n\nRESULT: "
        f"{passed} passed / {failed} failed"
    )

    return {
        "passed": passed,
        "failed": failed,
        "report": report,
    }


if __name__ == "__main__":
    result = run_browser_verification()

    print()
    print("=" * 64)
    print("MMSerim Milestone 5 Browser Verifier")
    print("=" * 64)
    print()
    print(result["report"])
    print()

    if result["failed"]:
        print("BROWSER VERIFICATION FAILED")
        raise SystemExit(1)

    print("BROWSER VERIFICATION PASSED")
