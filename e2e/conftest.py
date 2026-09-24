"""The browser for the end-to-end test.

KROMI_E2E_URL: the running app (default http://127.0.0.1:8080, the Docker setup).
KROMI_E2E_CHROMIUM: optional path of a Chromium to use instead of Playwright's.
A failing test leaves a screenshot in e2e/artifacts/.
"""
from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Page, sync_playwright

ARTIFACTS = Path(__file__).resolve().parent / "artifacts"


@pytest.fixture(scope="session")
def base_url() -> str:
    return os.environ.get("KROMI_E2E_URL", "http://127.0.0.1:8080").rstrip("/")


@pytest.fixture(scope="session")
def browser() -> Iterator[Browser]:
    with sync_playwright() as p:
        executable = os.environ.get("KROMI_E2E_CHROMIUM") or None
        b = p.chromium.launch(executable_path=executable)
        yield b
        b.close()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when == "call" and report.failed:
        page = item.funcargs.get("page")
        if page is not None:
            ARTIFACTS.mkdir(exist_ok=True)
            page.screenshot(path=str(ARTIFACTS / f"{item.name}.png"), full_page=True)


@pytest.fixture
def page(browser: Browser) -> Iterator[Page]:
    context = browser.new_context(viewport={"width": 1400, "height": 1000}, accept_downloads=True)
    pg = context.new_page()
    pg.set_default_timeout(30_000)
    yield pg
    context.close()
