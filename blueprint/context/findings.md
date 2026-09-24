# Findings

> **Generated file.** The findings ledger: review findings raised by `/audit`
> against the work in progress, each with a durable ID, severity (P0-P3), and
> status. `/implement` marks repaired findings `fixed`, a later `/audit` pass
> moves them to `closed`, and `/complete` refuses to merge while any P0 or P1
> finding is `open` or `fixed`, then archives resolved findings with the work
> and resets this file.

### F-03 [P3] unverified - Zone-aware dates would be stored differently in TIMESTAMP columns

**File:** postgres_etl/flat_transform.py:60
**Found:** 2026-09-24 by /audit (scope: current; lens: quality)
**Why it matters:** Parsing is now one rule, but storage still differs for a
source date that carries a zone offset: `app_standings.streak_history` converts
it to UTC, while the older `TIMESTAMP` (without time zone) columns such as
`etl_flat_standings_calendar_streaks.start_at` receive the aware value and
PostgreSQL converts it through the session time zone. No source date has an
offset today (all streak and round dates are zone-less), so nothing differs yet.
**Suggested fix:** Only if an offset ever appears: normalize aware values to UTC
before binding them to `TIMESTAMP` columns (or move those columns to
`TIMESTAMPTZ` together with the app). None needed now; no current requirement is
lost by leaving it.
**Resolution:**

### F-07 [P3] open - A Neon password with an unencoded `@` passes the URL check and part of it can reach the log

**File:** pipeline.py:204
**Found:** 2026-09-24 by /audit independent (scope: current; lens: security)
**Why it matters:** `looks_like_postgres_url` and `redactor` read the URL with
`urllib.parse.urlsplit`, which splits the user info at the *last* `@`, while
libpq splits at the *first* `@`. For a hand-built URL whose password contains a
raw `@` (for example `user:abc@def@host/db`, which should be written `abc%40def`),
the check accepts it, libpq takes `abc` as the password and `def@host` as the
host name, and the connection error `could not translate host name
"def@host" to address` carries the password's tail. The redactor hides the
whole password and the text before the first `@`, but not that tail, so it can
reach the console, the refresh log and the summary. Confirmed locally with a
fake value: `psycopg2.extensions.parse_dsn` returns the host with the password
tail, and `redactor` leaves it in a libpq-format host error (the live connect
error itself was not produced; no network was used). Neon's generated passwords
and copied connection strings are alphanumeric and encoded, so this needs a
hand-edited URL; low likelihood, local-only impact (`logs/` is git-ignored).
**Suggested fix:** In `looks_like_postgres_url`, also require exactly one `@`
in the authority (`parts.netloc.count("@") == 1`) so such a URL is refused with
the existing "malformed" message (which could mention percent-encoding `@` as
`%40`); add that case to
`test_malformed_neon_url_is_refused_before_publish_and_never_shown`. No current
requirement is lost.
**Resolution:**
