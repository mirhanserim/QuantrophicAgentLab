"""Chromium verifier driven by declarative checks from a milestone file.

Each check has a stable ``id`` so the agent loop can tell exactly which
previously-passing behaviour a patch broke (not just whether the total
failure count went up).

Supported check types (see milestones/*.json):
  visible        selector is present and visible
  text_any       selector's text contains any of ``any``
  css_in         computed ``property`` of selector is one of ``values``
  click_class    clicking ``click`` gives it ``class``
  click_changes  clicking ``click`` changes the text of ``watch``
  click_text     clicking ``click`` makes ``watch`` contain ``contains``
  min_numbers    selector's text holds at least ``min`` numbers
"""

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
import re

from playwright.sync_api import sync_playwright

from config import ARTIFACTS, WORKSPACE


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


def start_server(root: Path):
    handler = partial(QuietHandler, directory=str(root))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


def _text(page, selector):
    loc = page.locator(selector)
    return loc.first.inner_text().strip() if loc.count() else ""


def _visible(page, selector):
    loc = page.locator(selector)
    return loc.count() > 0 and loc.first.is_visible()


def run_check(page, check):
    kind = check["type"]
    sel = check.get("selector")

    if kind == "visible":
        return _visible(page, sel)

    if kind == "text_any":
        text = _text(page, sel)
        return any(token in text for token in check["any"])

    if kind == "css_in":
        if not page.locator(sel).count():
            return False
        value = page.locator(sel).first.evaluate(
            "(el, p) => getComputedStyle(el).getPropertyValue(p)",
            check["property"],
        )
        return value in check["values"]

    if kind == "min_numbers":
        return (
            _visible(page, sel)
            and len(re.findall(r"\b\d+\b", _text(page, sel))) >= check["min"]
        )

    if kind == "click_class":
        loc = page.locator(check["click"])
        if not loc.count():
            return False
        loc.first.click()
        page.wait_for_timeout(120)
        return loc.first.evaluate(
            "(el, c) => el.classList.contains(c)", check["class"]
        )

    if kind in {"click_changes", "click_text"}:
        loc = page.locator(check["click"])
        if not loc.count() or not page.locator(check["watch"]).count():
            return False
        before = _text(page, check["watch"])
        loc.first.click()
        page.wait_for_timeout(120)
        after = _text(page, check["watch"])
        if kind == "click_changes":
            return before != after
        return before != after and check["contains"] in after

    raise ValueError(f"Unknown check type: {kind}")


def run_browser_verification(milestone, save_screenshot=True, workspace=WORKSPACE):
    """Return {"passed", "failed", "results": {id: bool}, "report": str}."""
    results = []  # (id, ok, message)
    console_errors, page_errors = [], []
    checks = milestone.get("regression_checks", []) + milestone.get("checks", [])

    server, port = start_server(workspace)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": 1440, "height": 900})
                page.on("console", lambda m: m.type == "error" and console_errors.append(m.text))
                page.on("pageerror", lambda e: page_errors.append(str(e)))

                response = page.goto(
                    f"http://127.0.0.1:{port}/{milestone.get('entry', 'index.html')}",
                    wait_until="networkidle",
                    timeout=15000,
                )
                results.append(("page-loads", bool(response and response.ok), "Page loads"))

                for check in checks:
                    try:
                        ok = bool(run_check(page, check))
                        msg = check["label"]
                    except Exception as exc:  # a broken page must not crash the run
                        ok, msg = False, f"{check['label']} (error: {type(exc).__name__}: {exc})"
                    results.append((check["id"], ok, msg))

                results.append((
                    "no-js-errors", not page_errors,
                    "No uncaught JavaScript errors" + ("" if not page_errors else ": " + " | ".join(page_errors)),
                ))
                results.append((
                    "no-console-errors", not console_errors,
                    "No console errors" + ("" if not console_errors else ": " + " | ".join(console_errors)),
                ))

                if save_screenshot:
                    ARTIFACTS.mkdir(parents=True, exist_ok=True)
                    page.screenshot(
                        path=str(ARTIFACTS / f"{milestone['slug']}-browser.png"),
                        full_page=True,
                    )
            finally:
                browser.close()
    except Exception as exc:
        results.append(("verifier", False, f"Browser verifier crashed: {type(exc).__name__}: {exc}"))
    finally:
        server.shutdown()

    passed = sum(1 for _, ok, _ in results if ok)
    failed = len(results) - passed
    report = "\n".join(f"{'PASS' if ok else 'FAIL'}: {msg}" for _, ok, msg in results)
    report += f"\n\nRESULT: {passed} passed / {failed} failed"
    return {
        "passed": passed,
        "failed": failed,
        "results": {cid: ok for cid, ok, _ in results},
        "report": report,
    }


def regressions(before, after):
    """IDs that passed in ``before`` but fail in ``after``."""
    return sorted(
        cid for cid, ok in before["results"].items()
        if ok and not after["results"].get(cid, False)
    )


if __name__ == "__main__":
    import sys
    from config import load_milestone

    ms = load_milestone(sys.argv[1] if len(sys.argv) > 1 else None)
    result = run_browser_verification(ms)
    print(f"\n{ms['title']}\n" + "=" * 64 + "\n")
    print(result["report"])
    raise SystemExit(1 if result["failed"] else 0)
