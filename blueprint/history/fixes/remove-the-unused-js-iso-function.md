# Fix: Remove the unused js_iso function

**Type:** Fix
**Status:** verified
**Branch:** fix/remove-the-unused-js-iso-function

## The problem

`js_iso` in `postgres_etl/raw_transform.py:148` formatted source timestamps the way an old web-app
view returned them (JavaScript `toISOString()`). No production code calls it any more; only its
own test does (`postgres_etl/tests/test_raw_etl.py:293`). The docstrings of
`parse_source_timestamp` and `utc_wall_time` still name it as a user.

## The fix

- Delete `js_iso` from `postgres_etl/raw_transform.py`.
- In `test_js_iso_and_timestamp_casts_share_one_parsing_rule`, drop the `js_iso` assertions and keep
  the loop that checks the loader's `TIMESTAMPTZ` cast equals `parse_source_timestamp`; rename the
  test to `test_timestamp_casts_share_one_parsing_rule`.
- Drop the `js_iso` mentions from the two docstrings.
- Must not change `parse_source_timestamp`, `utc_wall_time` or any loaded value.

## Build steps

1. [x] Remove the function, trim the test and docstrings. Done when no file outside
   `blueprint/history` mentions `js_iso` and the postgres_etl suite passes.

## Verify

- `python -m unittest discover -s postgres_etl/tests` passes with the same test count (201).
- A search for `js_iso` in the code folders finds nothing.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":1287,"specSha256":"0f3adc0b11c3bc9e2db8e7bd68fb43ff4432660c8e7433fa7597a9db8a5bb5fe","branch":"refs/heads/fix/remove-the-unused-js-iso-function","head":"913672cb186ae9e301148526434f3fb202ffca67","baseRef":"refs/heads/main","baseCommit":"913672cb186ae9e301148526434f3fb202ffca67","sourceTree":"3ce0bddc64dcacbbe59c4436dc6b0edac27e749d","absentOptional":[]} -->
