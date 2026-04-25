# Security Policy

## Reporting a vulnerability

**Do not file a public issue for security problems.** GamesDownloader is a self-hosted application that exposes admin authentication, file scanners, and download tokens to the local network. A public exploit description can put existing self-hosted instances at risk before a fix lands.

Instead:

1. Open a [private security advisory](https://github.com/60plus/GamesDownloader/security/advisories/new) on GitHub. This creates a confidential thread visible only to maintainers.
2. Include:
   - A description of the vulnerability.
   - Steps to reproduce or proof-of-concept code.
   - The affected version (commit SHA or release tag).
   - Suggested mitigation if you have one.

You should get an acknowledgment within 72 hours.

## Scope

In scope:
- Authentication and session handling (cookies, JWT, SSO callbacks).
- Authorization scopes (admin, viewer, editor) on backend endpoints.
- File system access (path traversal, Zip Slip, symlink attacks).
- Plugin sandboxing (theme plugins compiled at startup, metadata plugins running in the app process).
- Scraper inputs (HTML / JSON parsing, SSRF on user-supplied URLs).
- Download tokens (one-time link bypass, expiry enforcement).
- ClamAV integration and virus-scanned uploads.

Out of scope:
- Issues that require local filesystem access on the host (the app trusts its own filesystem).
- Vulnerabilities in third-party services (GOG, IGDB, RAWG, ScreenScraper, SteamGridDB, etc.) - report those upstream.
- DoS scenarios that require valid admin credentials.
- ROM legality, copyright, or piracy concerns - this is not a security issue, see the README for the project's stance.

## Disclosure timeline

We aim to:
- Confirm or reject the report within 7 days.
- Ship a fix within 30 days for high or critical issues, or coordinate a longer window if the fix touches multiple components.
- Credit you publicly in the release notes once the fix is shipped (unless you prefer to stay anonymous).

## Supported versions

Only the latest release on `main` receives security updates. There is no LTS branch.
