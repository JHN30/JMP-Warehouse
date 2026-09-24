# Fix: Refuse raw at sign in Neon URL password

**Type:** Fix
**Status:** verified
**Branch:** fix/refuse-raw-at-in-neon-url-password
**Fixes:** F-07

## The problem

`pipeline.py` checks the Neon URL with `looks_like_postgres_url` before
publishing, but the check reads the URL with `urllib.parse.urlsplit`, which
splits the user info at the **last** `@`. libpq, which actually connects, splits
at the **first** `@`. So a hand-edited URL whose password contains a raw `@`
(for example `postgresql://user:abc@def@host/db`, which should be written
`abc%40def`) passes the check. libpq then takes `abc` as the password and
`def@host` as the host name. Its connection error ("could not translate host
name "def@host" ...") carries the password's tail, which the redactor does not
hide, so it can reach the console, the refresh log and the summary.

Neon's own URLs are alphanumeric and encoded, so this needs a hand-edited URL.
The impact is local (`logs/` is git-ignored), but it breaks the feature 10
contract that the Neon URL never appears in output.

## The fix

- In `looks_like_postgres_url`, also require exactly one `@` in the whole URL
  (`url.count("@") == 1`; counting only `urlsplit`'s authority misses a raw `@`
  followed by `/`, `?` or `#`). Such a URL is then refused before
  publishing with the existing "malformed" path: publish is not run, the value is
  never shown, and the publish stays pending.
- Extend the malformed-URL message to say a password containing `@` must be
  written as `%40` (the message still never shows the URL).
- Must not break: valid Neon URLs (including percent-encoded passwords such as
  `abc%40def`) are still accepted, and all other refresh behaviour stays the same.
  No new dependency or configuration.

## Build steps

- [x] 1. **Refuse a raw @ in the password.** Update `looks_like_postgres_url`
  and the malformed-URL message in `pipeline.py`. Tests: add
  `postgresql://owner:abc@def@example.neon.tech/db` (and the variants with `/`,
  `?` or `#` after the raw `@`) to
  `test_malformed_neon_url_is_refused_before_publish_and_never_shown` (refused,
  publish not run, neither password part in the log, console or next step), and
  assert that the percent-encoded form `owner:abc%40def@...` is still accepted.
  Done when: the three test commands in `AGENTS.md` pass.

## Verify

- The three test commands in `AGENTS.md` pass, including the new cases.
- `python pipeline.py --help` still works.
- This touches credential handling, so the configured `when-sensitive` gate is
  expected to select an independent review before `/complete`; that review
  re-examines F-07 and can close it.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":2640,"specSha256":"5fd87bcb51c26a55fe43a054ea39b0f1d2336e9846583d1751b1ada9ec27d210","branch":"refs/heads/fix/refuse-raw-at-in-neon-url-password","head":"4a6e80b50027e827af82d68a380c39ca72bb05db","baseRef":"refs/heads/main","baseCommit":"fc335271fda11ad35e04f9a98c366b31daef8a7a","sourceTree":"52d44189298156a470a8cd16286587ba104565fb","absentOptional":[]} -->

## Findings

### refuse-raw-at-in-neon-url-password/F-07 [P3] closed - A Neon password with an unencoded `@` passes the URL check and part of it can reach the log

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
**Resolution:** fixed in `fix/refuse-raw-at-in-neon-url-password`: `looks_like_postgres_url` also requires exactly one `@` in the authority, so a raw `@` in the password is refused before publish through the existing malformed path (value never shown, publish stays pending); the message now says to write `@` as `%40`. Tests: the raw-`@` case in `test_malformed_neon_url_is_refused_before_publish_and_never_shown` and `test_percent_encoded_at_in_password_is_still_accepted`. Awaiting re-review.

Re-reviewed 2026-09-24 by /audit independent (fresh subagent, target
`7085076`): **reopened, not closed.** The exact case in the spec is now refused,
but the repair checks `@` only inside `urlsplit`'s netloc, and `urlsplit` ends
the netloc at the first `/`, `?` or `#`. So a password with a raw `@` followed
later by a raw `/`, `?` or `#` still passes (`pipeline.py:211`). Checked with
fake values only (no network): `postgresql://owner:pa@ss/word@example.neon.tech/db`
is accepted and `psycopg2.extensions.parse_dsn` takes `ss` as the host (`word@...`
as the database); the `#` form is accepted and gives host `ss#word@example.neon.tech`;
the `?` form is accepted and libpq's parse error names `"word@example.neon.tech/db"`.
In each case `redactor` leaves the password tail (`ss`, `ss#word`, `word`) in the
error line, so it can still reach the console, refresh log and summary. Even
rarer than the original case (needs a hand-edited password with both `@` and one
of `/?#`), same local-only impact, so it stays P3. Smallest fix: require exactly
one `@` in the whole URL (`url.count("@") == 1`; Neon URLs never carry `@`
outside the user info) instead of in `parts.netloc`, and add a `/`, `?` and `#`
variant to the malformed-URL test. No current requirement is lost.

Repair 2 (2026-09-24): the check now requires exactly one `@` in the whole URL (`url.count("@") == 1`), so a raw `@` followed by `/`, `?` or `#` is refused too. Tests cover the plain, `/`, `?` and `#` variants (refused, never shown) and a normal Neon URL with query options (accepted). Awaiting re-review.

Re-reviewed 2026-09-24 by /audit independent (fresh subagent, target
`4a6e80b`): **closed.** `looks_like_postgres_url` (`pipeline.py:209-212`) now
requires `url.count("@") == 1` as well as a scheme, host and password from
`urlsplit`. With a single `@`, `urlsplit` returns a password only when no `/`,
`?` or `#` comes before that `@`, and libpq's user-info scan (stops at the
first `@` or `/`) then finds the same `@`. So every accepted URL splits the
same way in both parsers. Checked with fake values only (no network): for each
accepted URL (plain Neon with query options, `%40` in the password, `:` in the
password, a comma host list) `psycopg2.extensions.parse_dsn` returns the same
user, password and host as `urlsplit`. The raw-`@` forms (plain, `/`, `?`, `#`)
and `/`, `?`, `#`, `[` without `@` are all refused. One accepted edge, an
invalid percent escape such as `%zz`, makes libpq echo the raw password token,
and `redactor` replaces it with `***`. The repair adds no new defect. All three
test commands pass (16, 38, 28 tests) and `python pipeline.py --help` works.

## Independent review

# Independent Review

**Status:** passed
**Target commit:** 4a6e80b50027e827af82d68a380c39ca72bb05db
**Base commit:** fc335271fda11ad35e04f9a98c366b31daef8a7a
**Base ref:** main
**Spec hash:** 5fd87bcb51c26a55fe43a054ea39b0f1d2336e9846583d1751b1ada9ec27d210
**Prepared by:** claude
**Builder model:** claude-opus-5-5
**Requested reviewer:** claude
**Requested model:** claude-opus-5-5
**Requested execution:** automatic
**Requested at:** 2026-09-24T21:17:05+00:00
**Workflow:** regular
**Check required:** no
**Reviewer adapter:** claude
**Reviewer model:** claude-opus-5-5
**Reviewer context:** fresh subagent
**Actual execution:** automatic
**Reviewed at:** 2026-09-24T21:18:43+00:00
**Scope:** current
**Lenses:** quality, security, performance, tests
**Verdict:** passed
**Check result:** not-required

## Commands

- `git rev-parse HEAD` / `git merge-base main HEAD` / `sha256sum blueprint/context/current-feature.md` / `git status --porcelain --untracked-files=all`: pass (target, base and spec hash match; only `blueprint/context/review.md` differs)
- `cd api_requests && python -m unittest tests.test_scrapper`: pass (16 tests)
- `python -m unittest discover -s postgres_etl/tests`: pass (38 tests)
- `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export`: pass (28 tests)
- `python pipeline.py --help`: pass
- Read-only Python probe of `looks_like_postgres_url` and `redactor` against `psycopg2.extensions.parse_dsn`, fake URLs only (no network, no database): pass

## Evidence

- Delta `fc33527..4a6e80b` reviewed in full: `pipeline.py` (`looks_like_postgres_url`, malformed-URL message), `neon_publish/tests/test_publish.py` (malformed-URL cases and the new acceptance test), plus the spec and findings changes.
- Every URL the check accepts splits into the same user, password and host under `urlsplit` and libpq (plain Neon URL with `sslmode`/`channel_binding`, `%40` password, `:` in the password, comma host list).
- Raw `@` in the password (plain, then `/`, `?`, `#`) is refused before publish; the message is constant, never shows the URL, and the publish stays pending (covered by tests).
- Accepted edge with an invalid percent escape: libpq echoes the raw password token, and `redactor` masks it as `***`.
- The added `url.count("@")` is a constant-cost string scan run once per refresh; no performance impact. No em dash, en dash or ellipsis characters in the code delta.

## Findings

- F-07 [P3] closed (re-reviewed against `4a6e80b`; defect gone, no new defect)
- No new findings. F-03 [P3] unverified is untouched by this delta.

## Remaining risk

- Live libpq connection errors were not produced (no Neon or network use by rule); leak safety rests on `parse_dsn` parsing and the redactor probe with fake values.
- `/check` was not run (not required). No lint, typecheck or combined Verify command exists in this project (build-plan item 17).
