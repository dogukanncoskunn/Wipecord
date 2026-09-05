# Wipecord — Security Audit

**Date:** 2026-09-05 · **Scope:** the whole repository, its full git history, the
runtime token handling, dependencies, and the packaged binary.

This audit answers two questions directly, then documents the wider checks.

---

## Q1 — Is any real Discord token in the repository? (No.)

The author used the app during development. This checks whether that token — or
any token — was ever committed.

**Method**

- Scanned the working tree for Discord token shapes (user/bot tokens
  `[MNO]\w{23,25}\.\w{6}\.\w{27,40}` and MFA tokens `mfa.\w{20,}`).
- Scanned **every commit and every blob in the full history** (`git log -p --all`),
  not just the current files — a token committed once and deleted later still
  lives in history and would leak the moment the repo goes public.
- Ran the workspace secret scanner (`ws secrets`).
- Confirmed no sensitive file types are tracked (`.env`, `*.log`, `exports/`,
  `dist/`, `.venv/`).

**Result: clean.**

- No real token in the working tree.
- No real token in any historical commit.
- The only token-shaped string in the repo is an obviously fake test placeholder,
  `mfa.aVeryLongLookingFakeTokenValueForTests1234567890`, hard-coded in the test
  files. It is not a real token and never was.
- `ws secrets`: *No secret patterns found in tracked files.*
- No `.env`, log, export, build, or venv files are tracked.

The author's token is **not** in this repository, in any form, in any commit.

---

## Q2 — When other people use it, is their token stored anywhere? (No.)

**The token lives only in memory, for the lifetime of the process.**

- In the GUI it is held in a single `StringVar` behind the masked field, and
  passed into the `Job` the worker thread runs. Nothing else references it.
- There is **no** keyring use, **no** config file, **no** cache, **no**
  "remember me", and **no** environment variable written. (Headless mode *reads*
  an optional `WIPECORD_TOKEN` env var or a hidden prompt; it never writes one.)
- Closing the app ends the token's lifetime. There is nothing to delete because
  nothing was saved.

**Every place the app writes to disk was checked; none writes the token:**

| Write site | What it writes | Token? |
|---|---|---|
| Save log (`app.py`) | the log text, **passed through the redactor** | scrubbed |
| Export preview (`app.py`) | `{channel, generated_at, messages[]}` | no token |
| Headless `--json` (`__main__.py`) | same preview shape | no token |
| (asset reads) | reads the bundled icon / wordmark | read-only |

**Redaction.** Everything that can reach a log line, a saved log file, or an
exception message goes through `Redactor`, which replaces the token with
`***REDACTED***`. This is applied at the boundary, because `requests` can embed
headers/URLs in exception text.

**Network egress.** The only host the code contacts is `https://discord.com`
(the API). The string `https://github.com` appears **only** inside the
User-Agent value (`Wipecord/0.1 (+https://github.com/...)`) — it is a label, not
a request. There is no telemetry, analytics, crash reporting, or update check.
All HTTP goes through one `requests.Session` in `client.py`; there is no
`urllib`, raw `socket`, or other transport.

A user's token is never written to disk and never sent anywhere but Discord.

---

## Dependencies

`pip-audit` against the runtime dependencies (`customtkinter`, `requests`,
`Pillow`): **No known vulnerabilities found.** (`pyinstaller` is a build-only
dependency and is not shipped in the app.)

Re-run: `python -m pip_audit`.

---

## Tests

150 tests pass. **None of them touch the network** — the HTTP client is
exercised through a fake session, so the suite cannot leak or transmit anything.
Tests specifically covering token safety:

- the token never appears in any emitted event or saved log (redaction),
- only the token owner's messages are ever selected or deleted,
- the token is not a command-line argument (it would land in shell history and
  the process list).

---

## The packaged binary (`dist/Wipecord.exe`)

The exe is built by `scripts/build-exe.ps1` (PyInstaller, one-file, no console,
icon embedded). It is **not committed** — it is a build artifact; the official
binary is published as a GitHub Release, and each release's hash should be
recorded with it.

Reference build hash (produced locally from this commit):

```
SHA256: ff1cfc049839cc96bf5f4f8786cfc5cda3727a273fbc3c61feb73dd41b700fc9
Size:   23,132,745 bytes
Built with PyInstaller 6.22.2
```

> The hash changes every rebuild (embedded timestamps), so it is meaningful only
> for one specific binary. Verify the hash of the exact file you distribute.

### VirusTotal

VirusTotal results cannot be generated from inside this repo automatically —
submitting requires an API key, and uploading the binary makes it **public** on
VirusTotal (acceptable for an open-source tool, but a deliberate choice). Run it
yourself with a free API key:

```powershell
$env:VT_API_KEY = "<your virustotal api key>"
powershell -ExecutionPolicy Bypass -File scripts\virustotal-scan.ps1
```

It uploads `dist\Wipecord.exe`, waits for the analysis, and writes
`security\virustotal-result.json` (plus a one-line summary) into this folder, so
the result lives in the repo alongside this audit.

**Expect possible false positives.** PyInstaller one-file executables are
routinely flagged by a handful of heuristic engines because the bootloader
self-extracts to a temp directory — the same pattern packers use. This is a
known trait of *all* PyInstaller binaries, not a sign of malware here: the full
source is in this repo and the exe is reproducible from it with
`scripts\build-exe.ps1`. If the flag count is problematic for distribution,
options are a one-folder build (`--onedir`, less heuristic pressure) or signing
the binary with a code-signing certificate.

---

## What this audit does **not** claim

Security is bounded (see `SECURITY.md` for the full threat model):

- It does not protect against a **compromised machine** (malware can read the
  token from process memory or the screen — no local tool can prevent that).
- It does not remove the **Discord Terms-of-Service risk** of automating a user
  account. That risk is inherent to the tool's purpose and cannot be engineered
  away; it is stated plainly in the app and the README.

---

## Conclusion

- **The author's token is not in the repository or its history.**
- **End users' tokens are never persisted** — memory only, never disk, never sent
  anywhere but Discord, redacted from every log and file.
- Dependencies are clean; the test suite is network-free; egress is Discord-only.
- The binary is reproducible from source; run the included VirusTotal script to
  record third-party scan results next to this file.
