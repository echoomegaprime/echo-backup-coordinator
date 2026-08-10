# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Security

- Replaced the raw `key === env.ECHO_API_KEY` comparison in `checkAuth` with a constant-time
  `timingSafeEqual`, closing a timing side-channel on the check guarding every mutating route
  (including retention deletes and restore verification) in the fleet's backup coordinator.

### Fixed

- **The HTML operations dashboard was completely unreachable.** The router's unauthenticated
  `path === '/'` branch always returns before the authenticated `handleDashboard` branch --
  guarded by the identical condition, later in the function -- could ever run. The fully-built
  dashboard (job table, fleet inventory, retention policies) had been dead code since it was
  written. Moved it to its own authenticated route, `GET /dashboard`; `/` keeps its original
  public plain-JSON contract unchanged.
- Bumped `wrangler` `^3.99.0` -> `^4.0.0` and `@cloudflare/workers-types` `^4.20250313.0` ->
  `^5.20260804.1` (the old pin conflicted with the newer wrangler's peer requirement and blocked
  `npm install` outright). `npm audit`: 0 vulnerabilities.

### Added

- `tests/auth.test.mjs`: 17 real tests, including end-to-end tests calling the exported
  `worker.fetch()` against real routes -- proving both the auth-timing fix and, specifically,
  that `/dashboard` now serves the real dashboard HTML while `/` still returns the plain JSON
  contract even when authenticated. Verified locally that the dashboard-routing test fails when
  the dead-code bug is reintroduced, then passes clean on restore.
- `package.json` `test` script (`tsc --noEmit && node --test tests/*.test.mjs`).
- `LICENSE`, `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`.
- Hosted CI (`.github/workflows/ci.yml`): runs `npm test` on every push and pull request.
- Issue templates (bug report, feature request) and a pull-request template.
- `.echo/{apps.json,certification.json,sdk.json}` for ECHO Certification Forge and GitHub App
  Suite enrollment; `sdk.json` is honestly empty -- no `echo.backup_coordinator.*` or similar
  capability is registered in `arcanum_sdk.sdk_capabilities` for this repo.
  `scripts/certforge_journey.py` has dedicated regression checks for both fixes above.
- This CHANGELOG (the repository previously had none).

## [Prior history]

- feat: add KV-based rate limiting with separate read/write thresholds.
- fix: add root route returning 200 JSON service info.
- chore: sync uncommitted changes / update config and hardening changes / sync deployed changes
  (auth hardening, D1 error handling, service bindings).
- feat: echo-backup-coordinator -- initial commit.
