"""Start an isolated real Qdrant container, run tests, remove only that container."""

import os
import subprocess
import time
import uuid

import httpx


def main():
    name = "ai-office-test-" + uuid.uuid4().hex[:10]
    subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "-p",
            "127.0.0.1::6333",
            "-e",
            "QDRANT__TELEMETRY_DISABLED=true",
            "qdrant/qdrant:v1.16.2",
        ],
        check=True,
        capture_output=True,
    )
    try:
        address = subprocess.check_output(["docker", "port", name, "6333/tcp"], text=True).strip()
        url = "http://" + address
        for attempt in range(50):
            try:
                with httpx.Client(timeout=1, trust_env=False) as client:
                    client.get(url + "/readyz").raise_for_status()
                break
            except httpx.HTTPError:
                if attempt == 49:
                    raise
                time.sleep(0.2)
        env = {**os.environ, "AI_OFFICE_TEST_QDRANT_URL": url}
        subprocess.run(
            [
                "uv",
                "run",
                "--frozen",
                "pytest",
                "tests/integration",
                "-m",
                "integration",
                "-q",
                "--junitxml=.runtime/integration.xml",
            ],
            check=True,
            env=env,
        )
    finally:
        subprocess.run(["docker", "rm", "-f", name], check=True, capture_output=True)


if __name__ == "__main__":
    main()
