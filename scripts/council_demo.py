"""Actual local demo council through the UI and persisted worker stages."""

import json
from datetime import UTC, datetime
from pathlib import Path

from playwright.sync_api import expect, sync_playwright
from smoke import BASE, demo_token


def main():
    errors, external = [], []
    out = Path("docs/assets")
    out.mkdir(exist_ok=True)
    with sync_playwright() as p:
        chrome = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
        browser = p.chromium.launch(
            headless=True, executable_path=str(chrome) if chrome.exists() else None
        )
        context = browser.new_context(viewport={"width": 1440, "height": 1050})

        def route(request):
            if request.request.url.startswith(BASE + "/"):
                request.continue_()
            else:
                external.append(request.request.url)
                request.abort()

        context.route("**/*", route)
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(BASE)
        page.locator("#token").fill(demo_token())
        page.locator("#login-form button").click()
        page.locator("#workspace").wait_for(state="visible")
        page.locator('nav a[data-page="council"]').click()
        page.locator("#council-question").fill(
            "Стоит ли участвовать в тендере на поставку материалов, учитывая бюджет и срок?"
        )
        page.locator('#council-form button[type="submit"]').click()
        page.locator("#council-result .status.completed").wait_for(timeout=60000)
        assert page.locator("#council-result details").count() == 5
        assert (
            "Demo: question" in page.locator("#council-result").inner_text()
            or "Демо:" in page.locator("#council-result").inner_text()
        )
        page.evaluate("window.scrollTo(0,0)")
        page.screenshot(path=str(out / "council-en.png"), full_page=True)
        page.locator("#lang").click()
        # Reopen the saved run to check history and Russian dynamic output.
        page.locator("#council-history button").first.click()
        page.locator("#council-result .status.completed").wait_for()
        expect(page.locator("#council-result")).to_contain_text("Нужно больше данных")
        assert "Демо:" in page.locator("#council-result").inner_text()
        page.evaluate("window.scrollTo(0,0)")
        page.screenshot(path=str(out / "council-ru.png"), full_page=True)
        page.reload()
        page.locator("#council-history button").first.click()
        page.locator("#council-result .status.completed").wait_for()
        assert page.locator("#council-result details").count() == 5
        page.locator("#council-auto").select_option("manual")
        for role in ("contracts", "finance", "critic"):
            page.locator(f'#council-roles input[value="{role}"]').check()
        page.locator("#council-question").fill("Какие риски стоит проверить в новом договоре?")
        page.locator('#council-form button[type="submit"]').click()
        page.locator("#council-result .status.completed").wait_for(timeout=60000)
        expect(page.locator("#council-result details")).to_have_count(3, timeout=60000)
        page.locator("#council-result .status.completed").wait_for(timeout=60000)
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.evaluate("window.scrollTo(0,0)")
        page.screenshot(path=str(out / "council-mobile.png"), full_page=True)
        browser.close()
    assert not errors, errors
    assert not external, external
    result = {
        "checked_at": datetime.now(UTC).isoformat(),
        "mode": "deterministic_demo",
        "browser_errors": errors,
        "external_requests": external,
        "screenshots": 3,
        "checks": [
            "automatic five-role council",
            "manual three-role council",
            "persisted history after reload",
            "demo labels and needs_data",
            "Russian UI",
            "mobile overflow",
        ],
    }
    Path("docs/validation/council-browser.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
