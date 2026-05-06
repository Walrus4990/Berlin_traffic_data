
# TODO — Berlin Traffic Pipeline
_Last updated: 2026-04-30_

## Priority 1 — Must fix before next weekly run (data integrity)
These directly affect data correctness in the next scheduled run.

### ddweb_ingest_traffic.py + weekly DAG — do in one pass
- [ ] Change `chunk_end = min(to_date, today)` to `min(to_date, today - 1 day at 23:59:59)` in `download_mission()` — applies to both DAGs. Verify time component is `23:59:59` not `00:00:00`.
- [ ] Remove TEMP mission filter `[89637, 89639]` from `weekly_download()` — without this only 2 missions get updated weekly.
- [ ] Fix weekly DAG `start_date` and `schedule_interval` to `datetime(2026, 4, 28)` and `0 5 * * 1` before production — scheduled at 5am, after portal's 3am upload, consistent with `today-1` fix.
- [ ] Add `complete` boolean to tracker — stops inverted date range errors for fully-downloaded missions hitting the portal on every run.

### Initial DAG
- [ ] Extend initial DAG to run silver → gold after bronze validation completes.
      Stops short of superset refresh and gold Excel export (weekly DAG handles those).
      Discuss scope with AI colleague before implementing.

### Silver and gold
- [ ] Full review of silver and gold transformations — correctness and performance.
      Specific focus: replace pandas operations with SQL where appropriate given row volumes.
      Likely slow/memory-heavy on full dataset — test before prod load.
      12:59 PM# TODO: OOM risk in run_silver — chunked read may still buffer large result sets
      """pd.read_sql with chunksize=50000 on 39M rows uses a psycopg2 server-side cursor
      but the full query is held open for the duration. On low-memory systems this
      can cause SIGKILL before the first chunk is processed.
      Investigate: server-side cursor with named cursor in psycopg2, or LIMIT/OFFSET
      batching by source_file to bound memory per iteration."""

### Pipeline architecture — do alongside silver/gold review
- [ ] Refactor superset logic out of DAG into a dedicated `superset.py` module.
      Current: DAG contains DB connection, dataset registration, dashboard import, and cache refresh.
      Problem: `refresh_superset` uses `get_traffic_engine()` to extract raw URI — brittle and wrong for prod.
      Goal: clean separation — DAG orchestrates, `superset.py` handles all superset interactions.
- [ ] Superset DB connection not persisting — debug as part of above refactor.


## Priority 2 — Fix before prod load (pipeline correctness)

### DQ database — do in one pass (touch init_dq.sql and test_ingest.py together)
- [ ] Audit all DQ tables — align naming to `segment` throughout, drop serial IDs, check schemas.
      Currently inconsistent: `chunk_download_events`, `missing_segments`, `mission_completeness`, `segment_download_events`.
- [ ] Add `mission_start` and `mission_end` to `mission_completeness` table.
- [ ] Truncate `mission_completeness` and `missing_segments` before each run, or add `run_id` to distinguish runs.
- [ ] Confirm `today-1` fix resolves pattern 1 missing segments — rerun `validate_bronze` after fix and check DQ tables.

### Data integrity — investigate
- [ ] NULL speed values in gold — trace back through silver cleaning to source.
- [ ] Check `mission_id` added as column to `bronze.traffic` at load time — extract from `source_file` or add during merge with `bronze.mission`.
- [ ] Silver `NOT IN` query — fix for large `processed_set`.
- [ ] Investigate stub segment filename mismatch at mission start (pattern 2) — check if downloaded filenames match what completeness check expects for opening stubs.

### Human portal checks
- [ ] Manually check portal for missions 89637, 89638, 97589 — attempt manual download to confirm if data is genuinely blank or pipeline issue.
- [ ] Manually check portal for 32040 — entirely empty across all segments.
- [ ] Manually check portal for 54814 — 4 missing segments in Oct/Nov 2020 and 2021.

### Schema and init scripts
- [ ] SQL init scripts — confirm bronze/silver/gold schemas and tables correctly defined in `sql/init/`.
- [ ] Standardise table creation — replace inline `CREATE TABLE IF NOT EXISTS` with SQL init files throughout.


## Priority 3 — Code quality and prod readiness

### db.py and DQ module — do in one pass
- [ ] Remove stale `save_qa_report()` from `db.py` — move any needed DQ logic to DQ module, use `save()` instead.
- [ ] `_write_chunk_event()` creates a new engine on every invocation inside the download loop — ~900 chunks means potentially many engine creations. Refactor to create engine once in `download_mission()` and pass as parameter. Discussion: with 20s sleep between chunks and failures being a small fraction of 900, overhead may be negligible — decide whether to fix or accept as is.

### Airflow and infrastructure
- [ ] Airflow admin credentials (admin/admin) hardcoded in compose — move to `.env` vars `AIRFLOW_ADMIN_USER` and `AIRFLOW_ADMIN_PASSWORD`.
- [ ] Airflow 2.7.0 / Python 3.8 EOL — plan upgrade path when prod environment allows.
      Risks: DAG API changes, provider packages unbundled, DB migration, dependency breaks.
      Do in a separate branch with full test run before touching prod.
- [ ] Check prod client VM memory limits and adjust `mem_limit` values accordingly.
      Current: scheduler 1500m, webserver 1000m, postgres instances 512m.
      Risk: silent OOM-kill if load increases.

### Output and publishing — do in one pass
- [ ] Change MinIO gold export from parquet to CSV — calculate expected row counts first, may need chunking. Civil servants cannot open parquet.
- [ ] Two gold files in MinIO (`traffic_today` and `traffic_latest`) — decide if both needed.
- [ ] Rename MinIO folder from `gold/` to something intuitive e.g. `exports/` or `open-data/`.
- [ ] Check if MinIO sub-folder can be pointed to an API endpoint.
- [ ] Clean location display column for dashboard — strip device prefix (e.g. `DD 8472 Halker Zeile` → `Halker Zeile`).

### Data quality checks
- [ ] Define no-data alert — if `bronze.traffic` returns 0 new rows after load, raise error/alert rather than silently continuing.
- [ ] Check parquet file sizes in MinIO — validate memory assumptions for prod environment with 7-8GB RAM.
- [ ] Audit ID uniqueness across `mission_df`, `location_df`, traffic files.
- [ ] Check `device_id` always arrives as clean int from portal.
- [ ] Check if `MISSION_RENAME` and `LOCATION_RENAME` are necessary — if portal column names already clean, drop renaming.
- [ ] Change `bronze.location` from full-replace to append once ID uniqueness confirmed.

### Code quality
- [ ] Replace f-strings with `%s` logging throughout.
- [ ] Review and standardise file naming across `etl/` and `utils/`.
- [ ] Rename DAG to reflect TS only structure.

## Priority 4 — Nice to have / deferred

### Naming and refactoring — do in one pass, low urgency
- [ ] Full refactor and rename — replace bronze/silver/gold naming with descriptive alternatives
      across DAG, ETL files, DB schemas, and utils.
- [ ] Rename bronze/silver/gold schema names across traffic DB and DQ DB in one go during naming refactor.
- [ ] Review and standardise file naming across `etl/` and `utils/`.
- [ ] Rename DAG to reflect TS only structure.

### Infrastructure — deferred to prod environment
- [ ] Airflow migration task for prod SQL init on government Kubernetes cluster.
- [ ] Check prod client VM memory limits and adjust `mem_limit` values accordingly.
      Current: scheduler 1500m, webserver 1000m, postgres instances 512m.
      Risk: silent OOM-kill if load increases.

### Investigations — low urgency
- [ ] Check if `MISSION_RENAME` and `LOCATION_RENAME` are necessary — if portal column names
      already clean, drop renaming to reduce confusion.
- [ ] Two gold files in MinIO (`traffic_today` and `traffic_latest`) — decide if both needed.
- [ ] Check if MinIO sub-folder can be pointed to an API endpoint.
- [ ] Audit `device_id` always arrives as clean int from portal.
- [ ] Audit ID uniqueness across `mission_df`, `location_df`, traffic files.






### Download results:
complete download log: Start date > end date errors — missions 40671, 40687, 94076, 94074, 97594, 69502, 40688, 72976, 73698, 69501, 54814, 40718, 43114, 71077. All logged to bronze.segment_download_events. This is a data quality issue in the source — the portal has missions where end date is before start date. Not a code bug.
Empty segments — multiple missions returned no data (32040 entirely empty across many months, 89637, 89638, 97589, 40715, 40716, 40714). All correctly logged to DQ.
Successful uploads — missions 74739, 45098, 99512, 99516, 90938, 89639, 97593, 97595, 97596, 97592, 99511, 76539, 76538, 88538, 88539, 71078, 40963, 40964, 72973, 72975, 69478, 69481 all uploaded to MinIO.

load_traffic_to_bronze — working correctly. Idempotency confirmed — already-loaded files skipped, only new segments loaded. 40,995 rows appended total. Tracker updated correctly for each mission.
validate_bronze — ran cleanly. 44 missions checked, 44 rows written to mission_completeness, 65 missing segments written to missing_segments.
One thing to flag from load_traffic_to_bronze: mission 89637 shows segments being skipped up to 20260101 but nothing loaded for Feb, Mar, Apr 2026 — which matches the empty segments we saw in complete_download. Same for 89638 and 97589. So those are genuinely empty from the portal, not missing due to a pipeline bug. But we need DBeaver to confirm.
