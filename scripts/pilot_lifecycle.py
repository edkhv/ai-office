"""Real Docker pilot recovery drill, using disposable projects and synthetic customer files."""

import argparse
import io
import json
import os
import secrets
import subprocess
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from docx import Document
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]


class Deployment:
    def __init__(self, project, port):
        self.project, self.port = project, port
        self.env = {**os.environ, "AI_OFFICE_PILOT_PORT": str(port)}
        self.prefix = [
            "docker",
            "compose",
            "-p",
            project,
            "-f",
            "compose.yaml",
            "-f",
            "compose.pilot.yaml",
        ]

    def run(self, *args, input=None, check=True):
        result = subprocess.run(
            [*self.prefix, *args],
            cwd=ROOT,
            env=self.env,
            input=input,
            capture_output=True,
        )
        if check and result.returncode:
            raise RuntimeError("Docker stage failed: " + args[0] + " (output withheld)")
        return result

    def helper(self):
        name = self.project + "-maintenance"
        self.run("run", "-d", "--no-deps", "--name", name, "app", "sleep", "3600")
        return name


def execute(container, *args, input=None, check=True):
    result = subprocess.run(
        ["docker", "exec", "-i", container, *args], input=input, capture_output=True
    )
    if check and result.returncode:
        raise RuntimeError("Maintenance command failed (output withheld)")
    return result


def private_file(container, filename, content):
    code = "import os,sys; f=os.open(sys.argv[1],os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600); s=os.fdopen(f,'wb'); s.write(sys.stdin.buffer.read()); s.close()"
    execute(container, "python", "-c", code, filename, input=content)


def api(client, method, path, **kwargs):
    response = client.request(method, "/api/v1" + path, **kwargs)
    if response.is_error:
        raise RuntimeError(
            f"HTTP verification failed: {method} {path} status {response.status_code}"
        )
    return response


def wait_run(client, run_id):
    for _ in range(120):
        run = api(client, "GET", "/runs/" + run_id).json()
        if run["state"] == "completed":
            return run
        if run["state"] in {"failed", "rejected", "needs_clarification"}:
            raise RuntimeError("Worker did not complete the verification workflow")
        time.sleep(0.5)
    raise RuntimeError("Worker verification timeout")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-build", action="store_true")
    parser.add_argument("--source-port", type=int, default=8094)
    parser.add_argument("--restore-port", type=int, default=8095)
    args = parser.parse_args()
    suffix = uuid.uuid4().hex[:10]
    source = Deployment("ai-office-lifecycle-" + suffix, args.source_port)
    target = Deployment("ai-office-recovery-" + suffix, args.restore_port)
    helpers, checks = [], []
    output = ROOT / ".runtime" / "pilot-lifecycle.json"
    output.parent.mkdir(exist_ok=True, mode=0o700)
    report = {
        "status": "failed",
        "data": "synthetic test files in isolated pilot workspaces",
        "checks": checks,
    }
    try:
        print("Building and starting isolated company deployment", flush=True)
        if not args.no_build:
            source.run("build", "app")
        source.run("up", "-d", "--no-build", "--wait", "--wait-timeout", "180")
        setup_token = (
            source.run("exec", "-T", "app", "python", "-m", "app.cli", "setup-token")
            .stdout.decode()
            .strip()
        )
        with httpx.Client(
            base_url=f"http://127.0.0.1:{args.source_port}", timeout=60, trust_env=False
        ) as client:
            assert api(client, "GET", "/setup/status").json() == {
                "needs_setup": True,
                "data_mode": "pilot",
            }
            setup = api(
                client,
                "POST",
                "/setup",
                json={
                    "token": setup_token,
                    "company_name": "SYNTHETIC recovery customer",
                    "owner_display_name": "Director",
                    "timezone": "Europe/Moscow",
                },
            ).json()
            owner_token = setup["credential"]
            client.headers["Authorization"] = "Bearer " + owner_token
            assert api(client, "GET", "/documents").json() == []
            assert api(client, "GET", "/tasks").json() == []
            employees = [
                api(
                    client,
                    "POST",
                    "/users",
                    json={"display_name": name, "role": "employee", "team_id": "procurement"},
                ).json()
                for name in ("Sales", "Operations")
            ]
            checks.append("clean company setup and two employees, no demo documents/tasks")
            word = Document()
            word.add_paragraph("SYNTHETIC TEST: Orchid steel delivery in three working days.")
            blob = io.BytesIO()
            word.save(blob)
            document = api(
                client,
                "POST",
                "/documents",
                files={
                    "file": (
                        "synthetic-request.docx",
                        blob.getvalue(),
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    )
                },
            ).json()
            catalog = api(
                client,
                "POST",
                "/catalogs",
                files={
                    "file": (
                        "synthetic-prices.csv",
                        (ROOT / "examples/catalogs/synthetic-demo.csv").read_bytes(),
                        "text/csv",
                    )
                },
            ).json()
            quote = api(
                client,
                "POST",
                "/quotes",
                json={
                    "title": "SYNTHETIC recovery quote",
                    "customer": "SYNTHETIC customer",
                    "catalog_version_id": catalog["id"],
                    "source_document_id": document["document_id"],
                    "source_document_version": 1,
                    "lines": [{"sku": "STEEL-01", "quantity": "3"}],
                    "task": {
                        "title": "Review test quote",
                        "team_id": "procurement",
                        "assignee_id": employees[0]["user"]["id"],
                        "due_at": (datetime.now(UTC) + timedelta(days=3)).isoformat(),
                        "acceptance_criteria": "Review saved quote calculation",
                    },
                },
            ).json()
            proposed = api(
                client,
                "POST",
                f"/quotes/{quote['id']}/propose",
                headers={"Idempotency-Key": "lifecycle-quote"},
                json={"version": 1},
            ).json()
            proposal = proposed["proposal"]
            api(
                client,
                "POST",
                f"/approvals/{proposal['id']}/decision",
                json={
                    "decision": "approve",
                    "version": 1,
                    "payload_hash": proposal["payload_hash"],
                },
            )
            wait_run(client, proposed["run"]["id"])
            pdf = api(
                client, "GET", f"/quotes/{quote['id']}/export", params={"format": "pdf"}
            ).content
            api(
                client,
                "POST",
                "/documents",
                files={"file": ("synthetic-approved.pdf", pdf, "application/pdf")},
            )
            tasks = api(client, "GET", "/tasks").json()
            assert len(tasks) == 1 and tasks[0]["assignee_id"] == employees[0]["user"]["id"]
            before_quote = api(client, "GET", f"/quotes/{quote['id']}").json()
            before_documents = api(client, "GET", "/documents").json()
            answer = api(
                client,
                "POST",
                "/knowledge/ask",
                json={"query": "Orchid steel delivery"},
                headers={"Idempotency-Key": "lifecycle-question"},
            ).json()
            wait_run(client, answer["run_id"])
            checks.append(
                "DOCX/PDF, catalog, approved quote, assigned task and durable document answer"
            )
            source_helper = source.helper()
            helpers.append(source_helper)
            password = secrets.token_urlsafe(36).encode()
            private_file(source_helper, "/tmp/passphrase", password)
            backup_args = (
                "python",
                "-m",
                "app.backup",
                "backup",
                "/tmp/company.aioffice",
                "--passphrase-file",
                "/tmp/passphrase",
            )
            denied = execute(source_helper, *backup_args, check=False)
            assert denied.returncode != 0 and b"in use" in denied.stderr
            checks.append("backup refused while app/worker hold shared leases")
            print("Backing up stopped company and restoring a fresh deployment", flush=True)
            source.run("stop", "app", "worker")
            backup_info = json.loads(execute(source_helper, *backup_args).stdout)
            archive = execute(
                source_helper,
                "python",
                "-c",
                "import sys;sys.stdout.buffer.write(open('/tmp/company.aioffice','rb').read())",
            ).stdout
            assert backup_info["encrypted"] and len(archive) == backup_info["bytes"]
            target.run("up", "-d", "--no-build", "qdrant")
            target_helper = target.helper()
            helpers.append(target_helper)
            private_file(target_helper, "/tmp/passphrase", password)
            private_file(target_helper, "/tmp/company.aioffice", archive)
            restored = json.loads(
                execute(
                    target_helper,
                    "python",
                    "-m",
                    "app.backup",
                    "restore",
                    "/tmp/company.aioffice",
                    "--passphrase-file",
                    "/tmp/passphrase",
                ).stdout
            )
            assert restored["previous_credentials_revoked"]
            recovery_token = (
                execute(
                    target_helper,
                    "python",
                    "-c",
                    "print(open('/data/recovery-owner.token').read().strip())",
                )
                .stdout.decode()
                .strip()
            )
            target.run(
                "up",
                "-d",
                "--no-build",
                "--no-deps",
                "--wait",
                "--wait-timeout",
                "120",
                "app",
                "worker",
            )
            checks.append(
                "authenticated encrypted backup restored into new database and real Qdrant"
            )
        with httpx.Client(
            base_url=f"http://127.0.0.1:{args.restore_port}", timeout=60, trust_env=False
        ) as client:
            assert (
                client.get(
                    "/api/v1/tasks", headers={"Authorization": "Bearer " + owner_token}
                ).status_code
                == 401
            )
            assert (
                client.get(
                    "/api/v1/tasks",
                    headers={"Authorization": "Bearer " + employees[0]["credential"]},
                ).status_code
                == 401
            )
            client.headers["Authorization"] = "Bearer " + recovery_token
            assert api(client, "GET", "/setup/status").json()["needs_setup"] is False
            assert len(api(client, "GET", "/users").json()) == 3
            assert api(client, "GET", "/documents").json() == before_documents
            assert api(client, "GET", "/tasks").json() == tasks
            assert api(client, "GET", f"/quotes/{quote['id']}").json() == before_quote
            original = api(
                client,
                "GET",
                f"/documents/{document['document_id']}/original",
                params={"version": 1},
            ).content
            assert original == blob.getvalue()
            exported = api(
                client, "GET", f"/quotes/{quote['id']}/export", params={"format": "pdf"}
            ).content
            assert [p.extract_text() for p in PdfReader(io.BytesIO(exported)).pages] == [
                p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages
            ]
            result = api(
                client, "POST", "/knowledge/search", json={"query": "Orchid steel delivery"}
            ).json()
            assert result["evidence"] and result["status"] == "found"
            answer = api(
                client,
                "POST",
                "/knowledge/ask",
                json={"query": "Orchid steel delivery"},
                headers={"Idempotency-Key": "recovery-question"},
            ).json()
            wait_run(client, answer["run_id"])
            api(
                client,
                "PATCH",
                "/tasks/" + tasks[0]["id"],
                json={"status": "in_progress", "result": "Recovery verified"},
            )
            checks.append(
                "old owner/employee tokens rejected; new recovery token and completed setup preserved"
            )
            checks.append(
                "users, document IDs/bytes, quote snapshot/PDF, task/assignee preserved; recovered search/worker work"
            )
        report.update(
            {
                "status": "passed",
                "backup_bytes": len(archive),
                "documents": len(before_documents),
                "users": 3,
                "tasks": 1,
            }
        )
    finally:
        output.write_text(json.dumps(report, indent=2) + "\n")
        for helper in helpers:
            subprocess.run(["docker", "rm", "-f", helper], capture_output=True)
        source.run("down", "--volumes", "--remove-orphans", check=False)
        target.run("down", "--volumes", "--remove-orphans", check=False)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
