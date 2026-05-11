
# TODO — Berlin Traffic Pipeline
_Last updated: 2026-04-30_

## Priority 1 — Must fix before next weekly run (data integrity)
These directly affect data correctness in the next scheduled run.


### ddweb_ingest_traffic.py + weekly DAG — do in one pass
- [ ] Fix weekly DAG `start_date` and `schedule_interval` to `datetime(2026, 4, 28)` and `0 5 * * 1` before production — scheduled at 5am, after portal's 3am upload, consistent with `today-1` fix.

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
      - check if silver shoudl have same numebr of rows as bronze at teh moment it does not
      - issue: 1. Zero rows written repeatedly
Silver thinks there's nothing left to process. get_loaded_files is returning all source files as already processed, so the query returns 0 rows — but the loop still iterates producing empty chunks instead of breaking.
2. Why is the loop not breaking on empty?
The if not rows: break should catch this. But with a server-side cursor returning 0-row chunks repeatedly, something is off. My suspicion: fetchmany(50000) is returning empty lists but not falsy in the way we expect, or the cursor is behaving unexpectedly when the result set is exhausted.
The bug: when fetchmany returns an empty list [], if not rows: break should trigger. But something is preventing it. Can you share the current while True block from your silver.py?

          ADR: Tracker date inversion — decision to defer fix
          Date: 2026-05-06
          Context
          During repeated debug runs of complete_download() we saw errors like:
          ERROR - Mission 40671 chunk 2023-04-30-2023-04-29 failed: DoAnalyze failed for mission 40671:
          {'Success': False, 'Message': 'Das Startdatum muss kleiner als das Enddatum sein!'}
          Diagnosis
          The inversion is caused by the tracker, not bad portal data. For a mission that ended 2023-04-29:

          Tracker records last_downloaded_to = 20230429
          get_chunk_start() adds 1 day → chunk_start = 2023-04-30
          chunk_end = min(to_date, ye) = 2023-04-29
          chunk_start > chunk_end → portal rejects

          bronze.mission confirmed clean start_date < end_date for all affected missions — ruling out bad source data.
          Decision
          No fix applied. complete_download() is a one-off and will not be re-run in production. weekly_download()  filters to ToDate > ye so fully completed missions are never touched.
          The bug only manifests when complete_download() is re-run after completion — which only happened during debugging.
#### TODO — after first weekly DAG run
Check bronze.chunk_download_events for any failed rows with inverted date ranges. If they appear in the weekly run, the assumption above is wrong and the complete boolean fix must be implemented in load_traffic_to_bronze() in bronze_data_layer.py.

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

DQ table: doubling of missions in mission_copmleteness. investigate all DQ database tables for duploicates & go through code adn check if duplicates can be eradicated.

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



# Silver Layer — Session TODO
_Last updated: 2026-05-06_

---

## Step 1 — Uniqueness Audit (one-off SQL, not persisted)




---
## TODO — Pagination in ddweb_ingest_ref
Date: 2026-05-07
Issue
MISSIONS_PAYLOAD and LOCATIONS_PAYLOAD both hardcode "page": 1. If the portal paginates and either list exceeds one page, we silently fetch only the first page.
Why it matters
Currently 44 missions and ~45 locations. If the portal default page size is 50, we are already close to the limit for missions. Any new mission pushes us over and we silently lose data.
What needs checking

What is the portal's default page size?
Does the response include total count or pagination metadata we can use?
Is page: 1 a default (i.e. omitting it returns all) or does it actively limit results?

Action
Inspect a live portal response for pagination metadata, then implement either:

A loop over pages until exhausted, or
Confirm single-page fetch is safe and document the page size limit as a known constraint

---

## Step 2 — Dedup + `new_mission_detected` flag

Remove new_mission_detected parameter from run_silver() signature
All cleaning steps run unconditionally
Remove pipeline_path column from silver output
work out dedup by looking at current python fiel but translate to sql

---

## Step 3 — Initial vs Weekly Fork Decision

**Rationale:**
Current code has a single `run_silver` entry point with behaviour modified by `new_mission_detected`. The question is whether initial and weekly runs need structurally different logic, or whether one entry point with clean conditionals is sufficient.

**What we know:**
- Initial run: 39M rows, full history, all missions. Performance is the main concern.
- Weekly run: small incremental append, only new source files processed (idempotency via `get_loaded_files`).
- Gold is already fully incremental — entire aggregation reruns in SQL each time. Silver could follow same pattern.
- The idempotency mechanism (`get_loaded_files` → skip already-processed `source_file`) works at both scales.
- Main structural difference: initial run may need a post-ingestion dedup pass; weekly run does not (or it is cheap enough to always run).

**Options:**
- Single entry point, conditionals for scale-dependent steps (e.g. post-dedup pass).
- Two entry points (`run_silver_initial`, `run_silver_weekly`) — cleaner separation but code duplication risk.
dedup move to SQL post-ingestion
check if new_mission_detected gating be dropped entirely and clean rows saved to silver and not touched again
Confirm dedup key columns against actual traffic schema

**Decision needed:** agree before writing any silver entry point code. Linked to dedup decision in step 2.

---

## Step 4 — Location Cleaning in Pandas (incl. Pair Logic)

**Rationale:**
`bronze.location` is small (~45 rows). Pandas is appropriate. This is where sensor pair enrichment belongs — it is not a quality flag, it is enrichment (`is_pair: bool`, `paired_mission_id`).

**What we know:**
- Current `step_flag_ambiguous_location` misidentifies pairs as errors. Needs replacing with enrichment logic.
- Pairs: two different devices, same street, opposite driving directions, overlapping deployment windows.
- Pair matching rules not yet fully defined — deferred until we get to this step.
- Join key between mission and location TBD pending audit (Step 1).

**TBD:** pair matching rules, join key, whether `location_id` or `location_title` is the right key.



---

## Before next run:

Rebuild Docker container to apply updated init.sql (data-safe — do NOT use -v):

bashdocker-compose build
docker-compose up -d
---

## Step 5 — SQL Cleaning (Flag → Inspect → Drop → DQ)

**Rationale:**
Gold proves SQL-first works at 39M row scale. All row-wise cleaning steps (speed flags, class flags, window checks, duplicates) translate to SQL WHERE/CASE. Pandas chunking approach in current code has confirmed OOM risk and cross-chunk dedup gaps.

**What we know:**
- Current cleaning steps and their SQL translatability:
  - `step_parse_timestamps` → move to bronze ingest (agreed)
  - `step_flag_unknown_device` → SQL: LEFT JOIN to mission, flag NULLs
  - `step_flag_unclassifiable` → SQL: WHERE vehicle_class IN (6, 250)
  - `step_flag_speed` → SQL: CASE WHEN by class
  - `step_flag_duplicates` → SQL: ROW_NUMBER() OVER (PARTITION BY dedup_cols)
  - `step_flag_speed_ratio` → SQL: CASE WHEN both speeds > 0
  - `step_flag_outside_window` → SQL: JOIN to mission deployment windows
  - `step_consolidate_flags` → SQL: CASE WHEN any flag col is true

- Human-in-the-loop process agreed:
  1. Run flags in SQL
  2. Inspect flagged rows
  3. Adjust thresholds if needed
  4. Confirm → convert flag to drop
  5. Log dropped rows + reason to DQ database

**TBD:** DQ table schema and granularity — will emerge from seeing actual flag volumes in step 5. Do not pre-design.

---

## Step 6 — Merge Traffic + Location in SQL

**Rationale:**
With `mission_id` stamped onto traffic at ingest, and mission joined to location on confirmed key (TBD from audit), the merge becomes a straightforward SQL join — no time-window logic needed.

**What we know:**
- Current approach: time-windowed join on `device_id` + `datum_parsed` — fragile and complex.
- Proposed: `bronze.traffic` JOIN `bronze.mission` ON `mission_id` JOIN `bronze.location` ON `location_title` (or `location_id` — TBD).
- `mission_id` stamp in `_download_into_parquet` is a one-line addition at ingest — needs doing before this step.

**TBD:** join key confirmed in Step 1. Mission_id stamp confirmed working before this step runs.

---

## Step 7 — Write silver.traffic and silver.mission

**Rationale:**
Output of the cleaned, merged dataset into the silver schema. Idempotency must be preserved.

**What we know:**
- Idempotency via `source_file`: already-processed files skipped using `get_loaded_files`.
- `silver.active_mission` currently written as full replace each run — may need revisiting.
- Gold reads from `silver.traffic` and reruns full aggregation in SQL each time — so silver append behaviour is fine.

**TBD:** whether `silver.mission` is a full replace or append. Depends on pair logic output from Step 4.
