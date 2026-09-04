# Security

## Threat model

Wipecord handles a Discord user token, which is **full account access**: reading every DM, sending messages as you, and changing account settings. The design treats that token as the only asset worth protecting, and everything below follows from it.

### What the token is exposed to

| Surface | Handling |
|---|---|
| Disk | Never written. No config file, no keyring, no cache, no "remember me". |
| Network | Sent only to `https://discord.com`, only in the `Authorization` header. |
| Screen | The input is masked by default; revealing it is an explicit toggle. |
| Logs (window and saved file) | Passed through a redactor that replaces the token with `***REDACTED***`. |
| Exceptions | Redacted too — `requests` sometimes embeds headers or URLs in exception text, so redaction happens at the boundary rather than at remembered call sites. |
| Command-line arguments | Not accepted. Arguments land in shell history and the process list, where other users on the machine can read them. The headless mode reads `WIPECORD_TOKEN` or prompts with hidden input. |
| Crash reports / telemetry | None exist. |

The token lives in one `StringVar` and in the running job. Closing the app ends its lifetime.

### What Wipecord does not protect against

Stated plainly, because a security document that only lists strengths is marketing:

- **A compromised machine.** Malware with access to your session can read process memory, capture the screen, or log keystrokes. Nothing in a local tool defends against that.
- **Someone at your keyboard.** There is no application password. If the window is open and the token is filled in, whoever is sitting there can use it.
- **You pasting the token somewhere else.** Wipecord protects its own handling, not your clipboard.
- **A malicious fork.** Verify what you run. That is the point of the source being short.

If you believe your token has been exposed, change your Discord password — this invalidates all existing tokens.

## Terms of Service

Discord's Terms of Service prohibit automating a user account. Wipecord does this by design; there is no other way to delete your own direct messages programmatically, since bot tokens cannot access DM history and Discord's data-export flow does not delete anything.

The pacing keeps requests inside Discord's published rate limits. **It does not make the account safe from action taken over the terms themselves.** This risk cannot be engineered away, and the project does not claim otherwise.

## Explicit non-features

Wipecord complies with rate limits. It does not evade detection. That line is drawn deliberately, and these are on the wrong side of it:

- User-Agent spoofing or any impersonation of the official Discord client
- Proxy support, IP rotation, or request routing
- CAPTCHA solving or challenge evasion
- Browser fingerprint emulation
- Multi-account or account-farming features

Pull requests adding any of these will be declined. They would convert a personal data-deletion tool into an abuse tool, and they are the reason most projects in this space cannot be trusted.

## Data handling

- **Message content** is read into memory during a run and shown, truncated to one line, in the log.
- **The preview export** (`.json`) and **saved logs** contain message content. Both are written only when you explicitly choose a path, and `exports/` and `*.log` are in `.gitignore` so they cannot be committed by accident.
- **Nothing is transmitted anywhere.** There is no server component, no analytics endpoint, and no update check.

## Reporting a vulnerability

Open a GitHub issue for anything non-sensitive. For something that should not be public, use GitHub's private vulnerability reporting on this repository.

Please include the version, what you observed, and how to reproduce it.
