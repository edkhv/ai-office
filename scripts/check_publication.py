"""Repository-specific publication gate. Supplement with Gitleaks; not a full secret scanner."""

import re
import subprocess
from pathlib import Path


def main():
    files = subprocess.check_output(["git", "ls-files", "-z"]).decode().split("\0")
    bad = []
    patterns = [
        rb"gh[pousr]_[A-Za-z0-9]{30,}",
        rb"github_pat_[A-Za-z0-9_]{40,}",
        rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
        rb"\bAKIA[A-Z0-9]{16}\b",
        rb"\bsk-[A-Za-z0-9]{32,}",
    ]
    for name in filter(None, files):
        path = Path(name)
        if (
            any(p in {".runtime", ".venv", "data", "uploads", "logs", "models"} for p in path.parts)
            or name.endswith((".db", ".sqlite", ".token"))
            or (path.name.startswith(".env") and path.name != ".env.example")
        ):
            bad.append(name + ": forbidden local data")
        content = path.read_bytes()
        if len(content) > 5 * 1024 * 1024:
            bad.append(name + ": exceeds 5 MiB publication limit")
        if any(re.search(pattern, content) for pattern in patterns):
            bad.append(name + ": secret-like signature")
    if bad:
        print("\n".join(bad))
        raise SystemExit(1)
    print(
        f"Publication gate: {len(list(filter(None, files)))} tracked files checked; no forbidden paths or matched secret signatures."
    )


if __name__ == "__main__":
    main()
