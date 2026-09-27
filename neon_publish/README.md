# Neon publisher (paused)

Publishing is paused until feature 30 builds gold tables from silver. The CLI
reports the pause and does not connect to local PostgreSQL or Neon:

```powershell
python neon_publish/main.py --dry-run
```

The web app continues reading its existing Neon tables. It receives no new data
during this pause. The season publishing engine remains in `publish.py` for
feature 30: one Neon transaction per season, a guard against large row-count
shrinks, and per-game diffs for large play-by-play and shots tables. No tables
are selected for publishing now.

The [data dictionary](../docs/DATA_DICTIONARY.md#web-app-tables) preserves the
previous gold table contract as historical reference.

```powershell
python -m unittest neon_publish.tests.test_publish
```
