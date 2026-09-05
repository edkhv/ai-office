"""Actual browser walkthrough and screenshots. All browser requests stay on localhost."""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright
from smoke import BASE, demo_token


def main():
    Path(".runtime").mkdir(exist_ok=True, mode=0o700)
    out = Path("docs/assets")
    out.mkdir(parents=True, exist_ok=True)
    external = []
    errors = []
    with sync_playwright() as p:
        chrome = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
        browser = p.chromium.launch(
            headless=True, executable_path=str(chrome) if chrome.exists() else None
        )
        context = browser.new_context(
            viewport={"width": 1440, "height": 1050}, device_scale_factor=1
        )

        def route(request_route):
            if not request_route.request.url.startswith(BASE + "/"):
                external.append(request_route.request.url)
                request_route.abort()
            else:
                request_route.continue_()

        context.route("**/*", route)
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(BASE)
        page.locator("#token").fill(demo_token())
        page.locator("#login-form button").click()
        page.locator("#workspace").wait_for(state="visible")
        page.locator("#today-metrics .metric").first.wait_for()
        page.screenshot(path=str(out / "today.png"), full_page=True)
        page.locator('nav a[data-page="chief"]').click()
        page.locator('#command-form button[type="submit"]').click()
        page.locator("#run-panel .button-row button").first.wait_for(timeout=30000)
        page.screenshot(path=str(out / "chief-of-staff.png"), full_page=True)
        page.locator("#run-panel .button-row button").first.click()
        page.locator("#run-panel .status.completed").wait_for(timeout=30000)
        page.locator('nav a[data-page="tasks"]').click()
        page.locator(".task-card").first.wait_for()
        page.locator(".task-card select").first.select_option("in_progress")
        page.locator(".task-card textarea").first.fill("Synthetic UI walkthrough: work started.")
        page.locator('.task-card button[type="submit"]').first.click()
        page.locator('nav a[data-page="knowledge"]').click()
        page.locator("#ask-form button").click()
        page.locator("#answer-result .evidence").first.wait_for(timeout=30000)
        page.locator("#answer-result .evidence button").first.click()
        page.locator("#detail").wait_for(state="visible")
        assert (
            "100 000" in page.locator("#detail-content").inner_text()
            or "procurement" in page.locator("#detail-content").inner_text().lower()
        )
        page.locator("#close-detail").click()
        page.screenshot(path=str(out / "knowledge.png"), full_page=True)
        page.locator('nav a[data-page="control"]').click()
        page.locator("#control-metrics .metric").first.wait_for()
        page.locator("#control-metrics .metric button").nth(3).click()
        page.locator("#detail").wait_for(state="visible")
        assert "1800000.00" in page.locator("#detail-content").inner_text()
        page.screenshot(path=str(out / "lineage.png"), full_page=True)
        page.locator("#close-detail").click()
        page.locator('nav a[data-page="system"]').click()
        page.locator("#system-status table").wait_for()
        page.screenshot(path=str(out / "system.png"), full_page=True)
        page.locator("#lang").click()
        page.locator('nav a[data-page="today"]').click()
        page.locator("#today-metrics .metric").first.wait_for()
        assert page.locator("html").get_attribute("lang") == "ru"
        page.screenshot(path=str(out / "today-ru.png"), full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        page.screenshot(path=str(out / "mobile.png"), full_page=True)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        browser.close()
    assert not external, external
    assert not errors, errors
    report = {
        "browser_errors": errors,
        "external_requests": external,
        "screenshots": 7,
        "workflow": "login, plan, approval, tasks, knowledge, source, lineage, system, RU, mobile",
    }
    Path(".runtime/browser.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
