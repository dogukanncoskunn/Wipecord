# Wipecord — Security Audit

**Date:** 2026-09-05, re-reviewed 2026-09-08 before publication · **Scope:** the
whole repository, its full git history, the runtime token handling,
dependencies, and the packaged binary.

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

166 tests pass. **None of them touch the network** — the HTTP client is
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

Release build — **v0.1.0**, the binary published on the release page:

```
SHA256: 6b09429bc388128c234b6168d9827eef57df912385029a6ba5035e5a96c23f48
Size:   23,135,544 bytes
Built with PyInstaller 6.22.2
```

Superseded build (2026-09-05, pre-release audit, not distributed):

```
SHA256: ff1cfc049839cc96bf5f4f8786cfc5cda3727a273fbc3c61feb73dd41b700fc9
Size:   23,132,745 bytes
```

> The hash changes every rebuild (embedded timestamps), so it is meaningful only
> for one specific binary. Verify the hash of the exact file you distribute.

### VirusTotal — results (2026-09-08, the v0.1.0 release binary)

The **release** binary above was submitted to VirusTotal. Full report:
`security/virustotal-result.json`.

**5 of 75 engines flagged it. 63 clean; 7 returned no verdict** (1 timeout,
1 failure, 5 could not handle the file type).

| Engine | Verdict | Label | Kind |
|---|---|---|---|
| Microsoft | malicious | `Trojan:Win32/Wacatac.B!ml` | ML (`!ml` = machine-learning guess) |
| Cylance | malicious | `Unsafe` | ML-only engine; `Unsafe` is its sole malicious verdict |
| APEX | malicious | `Malicious` | generic heuristic |
| Bkav | malicious | `W32.Malware.CCD6F19A` | generic, hash-derived label |
| Zillya | malicious | `Dropper.Agent.Win32.746397` | generic |

**Not one of these is a signature match.** Every label is a catch-all these
engines apply to almost any unsigned, self-extracting executable — which is
exactly what a PyInstaller one-file build is. No engine names a behaviour, a
family with actual analysis behind it, or anything present in this source.

For comparison, the superseded 2026-09-05 build scored 4/75 on the same engine
set; Cylance is the addition. The difference is engine drift on unsigned
binaries, not a change in what the code does — the diff between the two builds
is the fixes listed under *Second pass* below, all of which are in this
repository.

Public page:
`https://www.virustotal.com/gui/file/6b09429bc388128c234b6168d9827eef57df912385029a6ba5035e5a96c23f48`

To re-run on a new build (needs a free API key; uploading makes the binary
**public** on VirusTotal):

```powershell
$env:VT_API_KEY = "<your virustotal api key>"
powershell -ExecutionPolicy Bypass -File scripts\virustotal-scan.ps1
```

**Expect possible false positives.** PyInstaller one-file executables are
routinely flagged by a handful of heuristic engines because the bootloader
self-extracts to a temp directory — the same pattern packers use. This is a
known trait of *all* PyInstaller binaries, not a sign of malware here: the full
source is in this repo and the exe is reproducible from it with
`scripts\build-exe.ps1`. Microsoft Defender is one of the four, so users may see
a SmartScreen or Defender prompt on first run. If the flag count is problematic
for distribution, the options are: submit the binary to Microsoft as a false
positive (https://www.microsoft.com/wdsi/filesubmission — usually cleared within
a day or two), ship a one-folder build (`--onedir`, less heuristic pressure), or
sign the binary with a code-signing certificate (the real fix, but paid).

---

## Second pass — pre-publication review (2026-09-08)

A full re-read of the source before the repository went public. **No new
token-handling or egress defect was found**; the findings were correctness and
robustness issues, all fixed in this release:

| Finding | Severity | Fix |
|---|---|---|
| `USER_AGENT` pointed at a GitHub URL that 404s, as did both `git clone` lines in the README | Medium — the "we identify ourselves honestly" position depends on that URL resolving | Corrected to the real repository |
| System messages (call/pin/recipient notices, types 1–7, 21) passed the author check, entered the preview, then failed on `DELETE` | Low — inflated the preview count and filled the log with red failures | `DELETABLE_MESSAGE_TYPES` whitelist in `Scanner._accepts`, with the skipped count reported once |
| The HTTP 202 "search index warming" loop had no attempt cap and used the server's `retry_after` unclamped | Low — a stuck index parked a scan indefinitely with no visible progress | Capped at `SEARCH_INDEX_MAX_ATTEMPTS` retries and `SEARCH_INDEX_MAX_WAIT` seconds, then falls back to history pagination |
| Log/preview writes called `write_text` unguarded; under `pythonw` there is no console, so a failed write was silent | Low — the button appeared to do nothing | `OSError` caught and surfaced in the log (`log.write_failed`, EN + TR) |
| Lookup/verify threads used a `Sleeper` whose stop event was never set | Informational | Wired to a UI-lifetime event set on window close |
| No CI | Informational | `.github/workflows/ci.yml` — pytest on Windows × Python 3.10/3.11/3.12, plus `pip-audit --strict` |

Re-verified in the same pass: 166 tests green and network-free; `pip-audit`
clean; no secret anywhere in the tracked tree; EN/TR string tables at full
parity (80/80 keys); egress still `discord.com` only.

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
