"""Real-browser company pilot walkthrough. Uses only explicitly synthetic test input."""

import json
import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

BASE = os.environ.get("AI_OFFICE_PILOT_BASE", "http://127.0.0.1:8092")
PROJECT = os.environ.get("AI_OFFICE_PILOT_PROJECT", "ai-office-pilot-validation")
COMPOSE = ["docker", "compose", "-p", PROJECT, "-f", "compose.yaml", "-f", "compose.pilot.yaml"]


def main():
    out = Path(".runtime/pilot-browser")
    out.mkdir(parents=True, exist_ok=True, mode=0o700)
    screenshots = Path("docs/assets")
    screenshots.mkdir(parents=True, exist_ok=True)
    token = subprocess.run(
        COMPOSE + ["exec", "-T", "app", "python", "-m", "app.cli", "setup-token"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    checks, errors, external = [], [], []
    with sync_playwright() as playwright:
        chrome = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
        browser = playwright.chromium.launch(
            headless=True, executable_path=str(chrome) if chrome.exists() else None
        )
        context = browser.new_context(
            viewport={"width": 1440, "height": 1050}, timezone_id="Europe/Moscow"
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
        page.locator("#setup-view").wait_for(state="visible")
        page.locator("#setup-token").fill(token)
        page.locator("#company-name").fill("Synthetic Pilot Company")
        page.locator("#owner-name").fill("Pilot Owner")
        with page.expect_response(
            lambda response: (
                response.url.endswith("/api/v1/setup") and response.request.method == "POST"
            )
        ) as setup:
            page.locator("#setup-form button").click()
        assert setup.value.status == 201
        owner_credential = setup.value.json()["credential"]
        owner_id = setup.value.json()["user"]["id"]
        page.locator("#setup-login").click()
        page.locator("#workspace").wait_for(state="visible")
        expect(page.locator("#company-label")).to_have_text("Synthetic Pilot Company")
        expect(page.locator("#today-metrics")).to_contain_text("unavailable")
        assert "Northline" not in page.locator("body").inner_text()
        assert page.locator("#command").input_value() == ""
        assert page.locator("#setup-credential").input_value() == ""
        page.screenshot(path=str(screenshots / "pilot-workspace.png"), full_page=True)
        checks.append(
            "Private one-time setup; company branding; empty financial facts; no demo instruction"
        )
        page.locator('nav a[data-page="users"]').click()
        users = []
        for name, team in (("Pilot Buyer", "procurement"), ("Pilot Operator", "operations")):
            page.locator("#user-name").fill(name)
            page.locator("#user-team").select_option(team)
            with page.expect_response(
                lambda response: (
                    response.url.endswith("/api/v1/users") and response.request.method == "POST"
                )
            ) as created:
                page.locator("#user-create-form button").click()
            assert created.value.status == 201
            users.append(created.value.json())
            expect(page.locator("#user-credential")).to_have_value(users[-1]["credential"])
            page.locator("#user-dismiss").click()
            expect(page.locator("#user-credential")).to_have_value("")
        expect(page.locator(".user-row")).to_have_count(3)
        page.screenshot(path=str(screenshots / "pilot-users.png"), full_page=True)
        # Public and employee clients cannot administer accounts.
        assert (
            context.request.get(
                BASE + "/api/v1/users",
                headers={"Authorization": "Bearer " + users[0]["credential"]},
            ).status
            == 403
        )
        operator = users[1]
        operator_row = page.locator('.user-row[data-user-id="' + operator["user"]["id"] + '"]')
        operator_row.locator("select").nth(2).select_option("false")
        with page.expect_response(
            lambda response: (
                response.url.endswith("/api/v1/users/" + operator["user"]["id"])
                and response.request.method == "PATCH"
            )
        ) as disabled:
            operator_row.locator('button[type="submit"]').click()
        assert disabled.value.status == 200
        assert (
            context.request.get(
                BASE + "/api/v1/auth/me",
                headers={"Authorization": "Bearer " + operator["credential"]},
            ).status
            == 401
        )
        checks.append(
            "Two named employees; owner-only management; disabling immediately revokes credential"
        )
        page.locator('nav a[data-page="knowledge"]').click()
        page.locator("#file").set_input_files(Path("examples/customer-demo/synthetic-request.docx"))
        with page.expect_response(
            lambda response: (
                response.url.endswith("/api/v1/documents") and response.request.method == "POST"
            )
        ) as uploaded:
            page.locator("#upload-form button").click()
        assert uploaded.value.status == 200
        page.locator('nav a[data-page="quotes"]').click()
        page.locator("#catalog-file").set_input_files(
            Path("examples/customer-demo/synthetic-catalog.csv")
        )
        with page.expect_response(
            lambda response: (
                response.url.endswith("/api/v1/catalogs") and response.request.method == "POST"
            )
        ) as catalog:
            page.locator("#catalog-form button[type=submit]").click()
        assert catalog.value.status == 200
        version = catalog.value.json()["id"]
        page.wait_for_function(
            "id => document.querySelector('#quote-catalog').value === id", arg=version
        )
        page.locator("#quote-request").fill("STEEL-01 × 3; BOLT-01 × 10")
        page.locator("#quote-request-form button[type=submit]").click()
        page.locator("#quote-suggestion .status.completed").wait_for(timeout=45000)
        expect(page.locator(".quote-sku")).to_have_count(2)
        page.locator("#quote-title").fill("Synthetic pilot proposal")
        page.locator("#quote-customer").fill("Synthetic customer")
        page.locator("#quote-assignee").select_option(users[0]["user"]["id"])
        expect(page.locator("#quote-assignee option:checked")).to_contain_text("Pilot Buyer")
        page.locator("#quote-due").fill(
            (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%dT12:00")
        )
        page.locator("#save-quote").click()
        page.locator("#quote-result .quote-total").wait_for()
        page.locator("#quote-result button").filter(has_text="Request approval").click()
        page.locator('#quote-result button[data-decision="approve"]').wait_for()
        page.locator('#quote-result button[data-decision="approve"]').click()
        page.locator("#quote-result .success").wait_for(timeout=45000)
        page.locator('nav a[data-page="tasks"]').click()
        page.locator(".task-card").first.wait_for()
        expect(page.locator(".task-card").first).to_contain_text("Pilot Buyer")
        page.screenshot(path=str(screenshots / "pilot-tasks.png"), full_page=True)
        page.locator('nav a[data-page="today"]').click()
        page.locator("#refresh-briefing").click()
        expect(page.locator("#briefing-result")).to_contain_text("Pilot Buyer")
        checks.append(
            "Own imported document and catalog; checked quote approval; named overdue task and briefing"
        )
        # Keep recovery identifiers private for local follow-up; never include tokens in reports/screenshots.
        private = out / "credentials.json"
        fd = os.open(private, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump({"owner_id": owner_id, "owner_credential": owner_credential}, stream)
        context.close()
        browser.close()
    report = {
        "synthetic_test_data": True,
        "base": BASE,
        "checks": checks,
        "browser_errors": errors,
        "external_requests": external,
        "passed": not errors and not external,
    }
    (Path(".runtime") / "pilot-browser.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    assert report["passed"], report
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
