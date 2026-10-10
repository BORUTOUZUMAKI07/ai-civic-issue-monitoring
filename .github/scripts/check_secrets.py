#!/usr/bin/env python3
"""Fail the build if a real-looking credential has been committed.

Why this exists: `backend/.env` and `prefect/.env` hold live Aiven / Atlas /
DagsHub credentials. They were never tracked (verified with
`git log --all -- backend/.env`) and both are gitignored, but nothing stopped
the *next* contributor from committing a copy -- `.env` was matched by
`**/.env`, while a file named `secrets.env` or `.env.backup` would have been
allowed straight through.

This scans the files git actually tracks, so it cannot be fooled by a path
being ignored, and it is pure stdlib so it runs before any install step.

Deliberate design choices:
  * `.env.example` / `*.example` are skipped -- they are placeholders by
    definition and must stay committable (see the negation rules in
    .gitignore).
  * URI passwords that are obvious placeholders (`changeme`, `your-*`, `xxx`,
    anything bracketed) are skipped, so the example files do not need to be
    special-cased beyond the path rule.
  * No 40-hex-token rule: git commit SHAs are 40 hex chars and would make the
    job useless.

Usage:
    python .github/scripts/check_secrets.py            # scan, exit 1 on hit
    python .github/scripts/check_secrets.py --staged   # scan index only
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Files that are never scanned: generated lockfiles and placeholder templates.
SKIP_SUFFIXES = (".lock", ".min.js", ".min.css", ".svg", ".png", ".jpg",
                 ".ico", ".woff", ".woff2", ".pdf", ".dvc")
SKIP_NAMES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml"}
SKIP_PARTS = (".env.example", ".example")

# Placeholder passwords we expect to see in tracked example files and docs.
PLACEHOLDER_PASSWORDS = {
    "changeme", "change-me", "password", "pass", "secret", "token",
    "xxx", "xxxx", "example", "placeholder", "admin", "user",
}

# Each pattern: (name, compiled regex, password-group, host-group-or-None).
# Host group matters: a credential on `localhost` is a CI service container or
# a local dev database, never an exfiltrated cloud URI, so it must not trip the
# scanner (that is what `.github/workflows/ci.yml`'s postgres service uses).
URI_PASSWORD = r"[^:\s/@]+:([^@\s/]{6,})@([^\s/?#]+)"
PATTERNS: list[tuple[str, re.Pattern[str], int | None, int | None]] = [
    (
        "private key block",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP |DSA )?PRIVATE KEY-----"),
        None,
        None,
    ),
    ("Aiven service token", re.compile(r"\bAVNS_[A-Za-z0-9]{10,}\b"), None, None),
    ("OpenAI-style API key", re.compile(r"\bsk-[A-Za-z0-9_\-]{24,}\b"), None, None),
    ("Groq API key", re.compile(r"\bgsk_[A-Za-z0-9]{20,}\b"), None, None),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"), None, None),
    ("GitHub fine-grained PAT", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"), None, None),
    ("DagsHub token inline", re.compile(r"DAGSHUB_TOKEN\s*[=:]\s*[A-Za-z0-9]{40}\b"), None, None),
    (
        "Postgres URI with credential",
        re.compile(r"\bpostgres(?:ql)?://" + URI_PASSWORD),
        1,
        2,
    ),
    (
        "MongoDB URI with credential",
        re.compile(r"\bmongodb(?:\+srv)?://" + URI_PASSWORD),
        1,
        2,
    ),
]

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]", "0.0.0.0"}

MAX_BYTES = 2_000_000  # skip generated blobs rather than reading them


def _placeholderish(password: str) -> bool:
    normalised = password.strip().strip("<>{}").lower()
    if normalised in PLACEHOLDER_PASSWORDS:
        return True
    markers = ("your", "changeme", "example", "xxx", "placeholder", "insert",
               "replace", "fake", "dummy", "<", ">", "****")
    return any(m in normalised for m in markers)


def _tracked_files(staged_only: bool) -> list[str]:
    cmd = ["git", "ls-files", "-z"]
    if staged_only:
        cmd.insert(2, "--cached")
    out = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, check=True)
    return [p for p in out.stdout.decode("utf-8", "replace").split("\0") if p]


def _skip(rel_path: str) -> bool:
    name = Path(rel_path).name
    if name in SKIP_NAMES:
        return True
    if rel_path.endswith(SKIP_SUFFIXES):
        return True
    return any(part in rel_path for part in SKIP_PARTS)


def scan(files: list[str]) -> list[str]:
    findings: list[str] = []
    for rel_path in files:
        if _skip(rel_path):
            continue
        absolute = REPO_ROOT / rel_path
        try:
            if absolute.stat().st_size > MAX_BYTES:
                continue
            raw = absolute.read_bytes()
        except OSError:
            continue
        if b"\0" in raw[:8192]:  # binary
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue

        for lineno, line in enumerate(text.splitlines(), 1):
            # Trailing comments in examples routinely explain the format.
            for name, pattern, group, host_group in PATTERNS:
                match = pattern.search(line)
                if not match:
                    continue
                if group is not None and _placeholderish(match.group(group)):
                    continue
                if host_group is not None:
                    host = match.group(host_group).rsplit("@", 1)[-1]
                    if host.lower() in LOCAL_HOSTS or host.lower().split(":")[0] in LOCAL_HOSTS:
                        continue
                findings.append(f"{rel_path}:{lineno}: [{name}] {line.strip()[:120]}")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staged", action="store_true",
                        help="scan only files staged for commit")
    args = parser.parse_args()

    files = _tracked_files(args.staged)
    findings = scan(files)

    if findings:
        print("::error::Credential-looking content found in tracked files.\n")
        print("Move the value into a gitignored `.env` (see `.env.example` for")
        print("the expected key names), commit only the placeholder, and rotate")
        print("the exposed credential if it was ever real.\n")
        for finding in findings:
            print(f"  {finding}")
        print(f"\n{len(findings)} finding(s) across {len(files)} tracked file(s).")
        return 1

    print(f"Clean: {len(files)} tracked file(s) scanned, no credentials found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
