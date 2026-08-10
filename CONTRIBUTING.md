# Contributing

Thank you for improving Echo Backup Coordinator. This is a public, proprietary infrastructure
project: contributions are welcome for review, but repository visibility does not grant a
general use or redistribution license.

## Development path

1. Open an issue describing the behavior being changed.
2. Create a focused branch from current `main`.
3. Add a failing test before changing `checkAuth`/`timingSafeEqual` or the `/dashboard` routing
   -- see SECURITY.md for why the dashboard was previously unreachable and how the fix is
   structured.
4. Validate before opening a pull request:

   ```powershell
   npm install
   npm test
   ```

5. Open a pull request using the repository template and include exact test output.

## Pull-request requirements

- No secrets (`ECHO_API_KEY`) are included.
- No stubs, placeholders, or self-asserted readiness -- this service is the fleet's only
  automated backup/retention/restore path.
- Any change to `checkAuth`, `timingSafeEqual`, or which routes require authentication is
  called out explicitly in the pull request description.
