# Fix: Test the unattended missing Neon URL branch

**Type:** Fix
**Status:** verified
**Branch:** fix/test-the-unattended-missing-neon-url-branch
**Fixes:** F-11

## The problem

The scheduled 06:00 refresh runs without a console. Its safety contract is that it
never waits at a hidden prompt: with no Neon URL it must stop with
`FAILED at Publish (missing Neon URL)`. The code does this today
(`resolve_neon_url`'s `if not interactive: return None, ...` in
[pipeline.py:220](../../pipeline.py#L220) and the missing-URL return in `refresh`,
[pipeline.py:413-416](../../pipeline.py#L413-L416)), but no unit test covers it.
The existing `refresh` tests pass `interactive=False` only with a URL present, and
`test_neon_prompt_waits_until_gold_quality_passes` stops at Gold quality before the
URL is looked up. If the guard regressed, `getpass` on Windows reads the console
directly, and the scheduled run would hang in its hidden window until the 2-hour
task limit, with no result or summary in the log.

## The fix

Test only; no production code change. Add one test next to the other `refresh`
tests in `neon_publish/tests/test_publish.py`, in the same style:

- `refresh(build_parser().parse_args(["--skip-fetch"]), "E2025", ...)` with a stage
  runner where every stage passes, `environ={}`, `dotenv_path` pointing at a
  missing file in a temporary directory, `interactive=False`, and a `prompt` that
  fails the test if called.
- Assert the result is `(1, "FAILED at Publish (missing Neon URL)", ...)`, that
  `neon_publish/main.py` never ran, and that publish stays pending.

Must not break: the other publisher and CSV tests.

## Build steps

- [x] 1. Add the test. **Done when:** it passes, and it fails if the
   `if not interactive` guard in `resolve_neon_url` is removed (checked by hand,
   then restored).

## Verify

- `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export`
  passes, with one more test than before (72 -> 73).
- Temporarily remove the `if not interactive` guard: the new test fails because
  the prompt was called. Restore the guard.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":2145,"specSha256":"faade98bdca0a61b7e9edd2e8dd2abc4195262ec6960d0e1e46a0da3e7118e0f","branch":"refs/heads/fix/test-the-unattended-missing-neon-url-branch","head":"b81b3276dff17d2f9d715272156e85349cb8f154","baseRef":"refs/heads/main","baseCommit":"b81b3276dff17d2f9d715272156e85349cb8f154","sourceTree":"438ef41f5cb6881c9e78618e08226f5ab7bd29dc","absentOptional":[]} -->
