# Echo Backup Coordinator

Automated backup coordinator for the ECHO OMEGA PRIME fleet -- Cloudflare Worker (D1 + KV + R2).
Manages D1 database backups, KV snapshots, R2 bucket inventory, fleet-wide cataloging, and
retention enforcement, with a real HTML operations dashboard.

## Crons

| Schedule | Job |
|---|---|
| Every 6 hours | Check `backup_schedules`, execute due backups |
| Daily 2am UTC | Nightly D1 backup of all known fleet databases |
| Weekly Sun 3am UTC | Full fleet inventory scan |
| Monthly 1st 4am UTC | Retention cleanup (age + count based) |

## Endpoints

| Access | Method | Path | Description |
|---|---|---|---|
| Public | GET | `/`, `/health` | Plain service info / health check |
| Authenticated | GET | `/dashboard` | HTML operations dashboard (jobs, fleet inventory, retention policies) |
| Authenticated | GET | `/stats`, `/backups`, `/backups/:id`, `/fleet`, `/fleet/:worker`, `/schedules`, `/retention` | Reads |
| Authenticated | POST | `/backup/trigger`, `/schedules`, `/retention`, `/restore/:backup_id` | Mutate / trigger |

`/restore/:backup_id` is a non-destructive verification step -- it checks the R2 object exists,
verifies its content hash, and reports readiness; it does not itself replay data into D1.

## Authentication

Every route other than `/` and `/health` requires `X-Echo-API-Key`, compared to
`env.ECHO_API_KEY` in constant time. See [SECURITY.md](SECURITY.md) for what changed in this
consolidation pass -- including the HTML dashboard, which existed fully built but was completely
unreachable until this pass moved it to its own route.

## Verify

```powershell
npm install
npm test
```

## Security

This service runs the fleet's automated backup, retention, and restore-verification path. See
[SECURITY.md](SECURITY.md) to report a vulnerability -- never as a public issue.

## License

See [LICENSE](LICENSE). Contributions: see [CONTRIBUTING.md](CONTRIBUTING.md).
