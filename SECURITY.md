# Security policy

Echo Backup Coordinator is a Cloudflare Worker (D1 + KV + R2) that runs the fleet's automated
backup, retention, and restore-verification path for D1 databases, KV snapshots, and R2 objects.
Every route other than `/` and `/health` requires `X-Echo-API-Key`, compared to
`env.ECHO_API_KEY` in constant time. There is a single shared credential -- no separate
read/write/admin tier.

## Fixed in this consolidation pass

1. **Timing side-channel in the credential check.** `checkAuth` compared the submitted key with
   `key === env.ECHO_API_KEY`. Replaced with a constant-time `timingSafeEqual`.
2. **The HTML dashboard was completely unreachable (functional defect, not a security one, but
   worth fixing under the same pass).** The router's early, unauthenticated
   `if (path === '/' && method === 'GET')` branch always returns before the authenticated
   `handleDashboard` branch (guarded by the identical `path === '/'` condition) could ever run --
   the dashboard was 100% dead code since the day it was written. Moved the dashboard to its own
   authenticated route, `GET /dashboard`, and left `/` as the public plain-JSON service-info
   response it always was.

## Supported version

Security fixes target the current `main` branch and the currently deployed Worker release.
Historical commits are retained for evidence and are not patched in place.

## Report a vulnerability

Do not open a public issue for a suspected vulnerability. Send a private report to
`security@echo-op.com` with:

- affected endpoint and exact revision;
- reproduction steps and expected impact (this service can trigger backups, restores, and
  retention deletes across the fleet's D1/KV/R2 storage -- treat any auth-boundary issue as
  high severity);
- safe contact details for follow-up.

Never include a live `ECHO_API_KEY` in a report.
