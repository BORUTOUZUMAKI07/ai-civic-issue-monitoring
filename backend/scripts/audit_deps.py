"""Dependency audit gate.

Runs ``pip-audit`` against the active environment, passing a curated
allowlist of advisories that are either (a) not exploitable in how this
application actually uses the package, or (b) not yet fixable because the fixed
release has not landed on conda-forge (several of these arrive as conda
transitives of dvc / pre-commit / prefect / mlflow, and version floors in
pixi.toml cascade the whole conda solve into conflicts).

Anything NOT in IGNORED — a brand-new advisory, or a known advisory on a new
package or version — exits non-zero and fails CI. That is the point of the
gate: an allowlist *reviewed today* that demands a review again tomorrow.

How this list is meant to shrink:

* Every acceptable advisory names its fixed release in the comment. When that
  release reaches conda-forge, bump the enclosing package in pixi.toml and
  delete the ID.
* The python-jose entry is the one item with *no* fix: python-jose is
  unmaintained and CVE-2026-85394 has no patch. We are not exposed (see its
  comment), but the real resolution is migrating to PyJWT; that entry is the
  tracking bug to delete once the migration lands.
"""

from __future__ import annotations

import subprocess
import sys

# advisor id -> why it is acceptable *as of this lockfile*, and the fix.
# Adding anything here requires surviving review; removing something after its
# fix lands is the normal lifecycle.
IGNORED: dict[str, str] = {
    # ── gitpython 3.1.53 (conda transitive of dvc; fixed in 3.1.60) ─────────
    # Every one of these needs an *attacker-controlled repository* (forged
    # config / .gitmodules, hostile revisions or tag names). Our flows only
    # dvc-pull from remotes we own (DagsHub); nobody can write those files
    # without already having push access.
    "PYSEC-2026-3783": "gitpython: config-name injection via forged repo config; fix 3.1.58",
    "PYSEC-2026-3784": "gitpython: submodule name validation; fix 3.1.58",
    "PYSEC-2026-3785": "gitpython: merge_includes local-file disclosure; fix 3.1.59",
    "PYSEC-2026-3786": "gitpython: config re-serialization injection; fix 3.1.59",
    "PYSEC-2026-3787": "gitpython: --separate-git-dir path traversal; fix 3.1.59",
    "PYSEC-2026-3788": "gitpython: incomplete blame revision denylist; fix 3.1.59",
    "PYSEC-2026-3837": "gitpython: TagReference.create argument injection; fix 3.1.59",
    "PYSEC-2026-3838": "gitpython: same class as above, TagReference; fix 3.1.58",
    "PYSEC-2026-3840": "gitpython: revision-option injection; fix 3.1.58",
    "PYSEC-2026-3841": "gitpython: revision-option injection variant; fix 3.1.58",
    "PYSEC-2026-3843": "gitpython: config write path traversal; fix 3.1.58",
    "PYSEC-2026-3948": "gitpython: malformed config parse; fix 3.1.57",
    "PYSEC-2026-3949": "gitpython: malformed config parse variant; fix 3.1.57",
    "PYSEC-2026-3950": "gitpython: sparse-checkout path traversal; fix 3.1.56",
    "PYSEC-2026-3951": "gitpython: sparse-checkout path traversal variant; fix 3.1.55",
    "PYSEC-2026-3952": "gitpython: refspec handling; fix 3.1.54",
    "PYSEC-2026-3953": "gitpython: refspec handling variant; fix 3.1.54",
    "PYSEC-2026-3982": "gitpython: submodule fetch path traversal; fix 3.1.60",
    "PYSEC-2026-3984": "gitpython: submodule fetch path traversal variant; fix 3.1.60",
    "PYSEC-2026-3995": "gitpython: revision guard bypass; fix 3.1.54",
    # ── urllib3 2.7.0 (conda; fixed in 2.8.0) ────────────────────────────────
    "PYSEC-2026-4175": "urllib3: streaming chunked-decode abort; needs hostile server",
    "PYSEC-2026-4176": "urllib3: streaming chunked-decode abort variant",
    "PYSEC-2026-4177": "urllib3: TLS config cross-contamination for HTTPS proxies",
    # ── virtualenv ───────────────────────────────────────────────────────────
    # Now pinned to >=21.14.12 in pixi.toml (conda via pre-commit), which closes
    # the 21.7.0 advisories (PYSEC-2026-4011/4012/4013/4014) and the newer
    # CVE-2026-113722/113725/113726/113732/113776, so their entries were
    # removed once the floor landed.
    # ── aiohttp ──────────────────────────────────────────────────────────────
    # The 2026-11 advisories (CVE-2026-111065/111066/111748/111749/111750 and
    # the earlier CVE-2026-111063/111064, GHSA-2g87-pp6c-29x5, PYSEC-2026-3545)
    # are all closed by the 3.14.5 floor in pixi.toml, so their allowlist
    # entries were removed once the fix landed.
    # ── asyncssh 2.23.0 (conda via prefect; fixed 2.23.1/2.24.0) ─────────────
    "PYSEC-2026-3808": "asyncssh: malicious-SCP-server file write; SCP CLI never used",
    "PYSEC-2026-4026": "asyncssh: max-packet-size wedge; SSH client never used",
    # ── cryptography 49.0.0 (conda; fixed 50.0.0) ────────────────────────────
    "PYSEC-2026-3552": "cryptography: pkcs7_decrypt_* padding oracle; no pkcs7/S-MIME path exists",
    # ── diskcache 5.6.3 (conda via prefect; no fix published) ────────────────
    "PYSEC-2026-2447": "diskcache: pickle deserialization requires write access to the cache dir",
    # ── ecdsa 0.19.2 (pypi via python-jose; no newer fix) ────────────────────
    # Minerva timing attack on P-256 via ecdsa.SigningKey.sign_digest().
    # python-jose here uses the `cryptography` backend, so this code path is
    # never exercised. (Nexus carries the identical allowlist entry.)
    "PYSEC-2026-1325": "ecdsa: Minerva timing; jose's cryptography backend is used, ecdsa never invoked",
    # ── h2 4.3.0 (conda http2 stack; fixed 4.4.1) ────────────────────────────
    "PYSEC-2026-3628": "h2: HTTP/2 framing; app serves HTTP/1.1 only",
    # ── hydra-core 1.3.2 (ML toolchain transitive; fixed 1.3.6) ──────────────
    "PYSEC-2026-3850": "hydra-core: ML toolchain; not imported at runtime",
    "CVE-2026-106441": "hydra-core: ML toolchain; not imported at runtime",
    # ── multidict 6.7.1 (conda via aiohttp; no conda build of 6.9.1 yet) ─────
    "CVE-2026-104874": "multidict: aiohttp dependency; not imported by the app",
    # ── python-jose 3.5.0 (direct dependency; NO FIX PUBLISHED) ──────────────
    # CVE-2026-85394: HMAC init accepts a DER-encoded asymmetric key, so an
    # attacker who holds the service's *public* key can forge HS256 tokens.
    # Every encode/decode here uses the server-side symmetric SECRET_KEY
    # (HS256, algorithms=[HS256]) — no key ever comes from the token or the
    # request, so the confusion is unreachable. python-jose is unmaintained;
    # migrate to PyJWT and delete this entry.
    "CVE-2026-85394": "python-jose: alg confusion needs attacker-supplied public key; HS256 + fixed SECRET_KEY only",
    # -- brotli/filelock/gitpython/setuptools (transitive, fix available) ---
    "PYSEC-2026-4322": "brotli: fixed in 1.2.1; transitive, no direct call path",
    "GHSA-9v8h-qqgm-4m35": "brotli: fixed in 1.2.1",
    "CVE-2026-112940": "filelock: fixed in 4.2.1; dev tooling transitive",
    "CVE-2026-112913": "filelock: fixed in 4.2.1; dev tooling transitive",
    "CVE-2026-112907": "filelock: fixed in 4.2.1; dev tooling transitive",
    "CVE-2026-114145": "gitpython: fixed in 3.2.1; needs attacker repo, dvc pull only from owned remotes",
    "GHSA-xmj3-9gf7-h52w": "setuptools: fixed in 84.1.0; build tooling",
}


def main() -> int:
    cmd = [sys.executable, "-m", "pip_audit"]
    print("=== Applied allowlist (advisory -> reason) ===")
    for vid in sorted(IGNORED):
        print(f"  --ignore-vuln {vid}: {IGNORED[vid]}")
    for vid in sorted(IGNORED):
        cmd += ["--ignore-vuln", vid]
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
