
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
- [ ] Add `mission_start` and `mission_end` to `mission_completeness` table.
- [ ] Truncate `mission_completeness` and `missing_segments` before each run, or add `run_id` to distinguish runs.
- [ ] Confirm `today-1` fix resolves pattern 1 missing segments — rerun `validate_bronze` after fix and check DQ tables.

### Data integrity — investigate
- [ ] NULL speed values in gold — trace back through silver cleaning to source.
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
- [ ] `_write_chunk_event()` creates a new engine on every invocation inside the download loop — ~900 chunks means potentially many engine creations. Refactor to create engine once in `download_mission()` and pass as parameter. Discussion: with 20s sleep between chunks and failures being a small fraction of 900, overhead may be negligible — decide whether to fix or accept as is.


### Output and publishing — do in one pass
- [ ] Change MinIO gold export from parquet to CSV — calculate expected row counts first, may need chunking. Civil servants cannot open parquet.
- [ ] Two gold files in MinIO (`traffic_today` and `traffic_latest`) — decide if both needed.
- [ ] Rename MinIO folder from `gold/` to something intuitive e.g. `exports/` or `open-data/`.
- [ ] Check if MinIO sub-folder can be pointed to an API endpoint.
- [ ] Clean location display column for dashboard — strip device prefix (e.g. `DD 8472 Halker Zeile` → `Halker Zeile`).

### Data quality checks
- [ ] Define no-data alert — if `bronze.traffic` returns 0 new rows after load, raise error/alert rather than silently continuing.
- [ ] Check parquet file sizes in MinIO — validate memory assumptions for prod environment with 7-8GB RAM.


## Priority 4 — Nice to have / deferred


### Infrastructure — deferred to prod environment
- [ ] Airflow migration task for prod SQL init on government Kubernetes cluster.


### Investigations — low urgency
- [ ] Two gold files in MinIO (`traffic_today` and `traffic_latest`) — decide if both needed.
- [ ] Check if MinIO sub-folder can be pointed to an API endpoint.



### Download results:
complete download log: Start date > end date errors — missions 40671, 40687, 94076, 94074, 97594, 69502, 40688, 72976, 73698, 69501, 54814, 40718, 43114, 71077. All logged to bronze.segment_download_events. This is a data quality issue in the source — the portal has missions where end date is before start date. Not a code bug.
Empty segments — multiple missions returned no data (32040 entirely empty across many months, 89637, 89638, 97589, 40715, 40716, 40714). All correctly logged to DQ.
Successful uploads — missions 74739, 45098, 99512, 99516, 90938, 89639, 97593, 97595, 97596, 97592, 99511, 76539, 76538, 88538, 88539, 71078, 40963, 40964, 72973, 72975, 69478, 69481 all uploaded to MinIO.

load_traffic_to_bronze — working correctly. Idempotency confirmed — already-loaded files skipped, only new segments loaded. 40,995 rows appended total. Tracker updated correctly for each mission.
validate_bronze — ran cleanly. 44 missions checked, 44 rows written to mission_completeness, 65 missing segments written to missing_segments.
One thing to flag from load_traffic_to_bronze: mission 89637 shows segments being skipped up to 20260101 but nothing loaded for Feb, Mar, Apr 2026 — which matches the empty segments we saw in complete_download. Same for 89638 and 97589. So those are genuinely empty from the portal, not missing due to a pipeline bug. But we need DBeaver to confirm.


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


## Step 3 — load data (initial & weekly) check idempotency

Note: currect dedup approach as a bug: - issue: 1. Zero rows written repeatedly
Silver thinks there's nothing left to process. get_loaded_files is returning all source files as already processed, so the query returns 0 rows — but the loop still iterates producing empty chunks instead of breaking.

---

## Step 4 — Location Cleaning (incl. Pair Logic)

**Rationale:**
`bronze.location` is small (~45 rows). Pandas is appropriate. This is where sensor pair enrichment belongs — it is not a quality flag, it is enrichment (`is_pair: bool`, `paired_mission_id`).

**What we know:**
- Current `step_flag_ambiguous_location` misidentifies pairs as errors. Needs replacing with enrichment logic.
- Pairs: two different devices, same street, opposite driving directions, overlapping deployment windows.
- Pair matching rules not yet fully defined — deferred until we get to this step.
- Join key between mission and location TBD pending audit (Step 1).

**TBD:** pair matching rules, join key, whether `location_id` or `location_title` is the right key.


---


## New inputs- To Dos
- Partitioning silver.traffic — rebuild with partitions (by date or source_file) to reduce disk temp space usage on large queries. File: init.sql / silver DDL.
- vehicle_class_label vs lookup table — decide at gold/dashboard layer whether to drop vehicle_class_label from silver/gold and replace with a reference lookup table for Superset display. File: gold DDL, Superset config.





# Handover Note — Next Session

## Who you are
Coding coach helping the human rebuild a medallion ETL pipeline for Berlin traffic sensor data. You do not write code unprompted. You do not move to the next step until explicitly told. Follow the Ways of Working document strictly.

---

## What this pipeline does
Medallion architecture ETL for traffic sensors in Tempelhof-Schöneberg, Berlin.
- **Orchestrator:** Latest Apache Airflow
- **Source:** PostgreSQL — `bronze` schema
- **Destination:** PostgreSQL — `silver` schema (same database)
- **DQ destination:** Separate PostgreSQL database (`postgres_dq`)
- **Scale:** 39m rows historical; hundreds of thousands per weekly run
- **Language pattern:** SQL-first for large data, pandas for small reference tables

---

## Sensor hardware — critical context
- Single-point sensors, ~10cm wide, mounted on residential streets
- Most sensors in pairs — one each side of a street
- Entry and exit are two readings milliseconds apart at the same physical location
- Sensor unreliable below ~10kmh
- Data uploaded to portal once daily at 3am (data included past 24h)
- Pipeline retrieves from portal, not sensors directly
- Data structure: two reference tables (mission, location) + many traffic tables

---

## Current stack state
- `bronze.mission`, `bronze.location`, `bronze.traffic` — fully loaded, working
- `silver.traffic` — rebuilt and working. Clean rows only (no flag columns). Dedup handled via `flag_duplicate` in staging.
- `silver.staging_traffic` — intermediate table, truncated at start of each run
- `postgres_dq` silver tables — DDL created, not yet populated (validate_silver not yet wired into DAG)

---

## Tasks for this session

### Task 1 — Build `silver.ref_mission_location`
Merge `bronze.mission` and `bronze.location`, enrich with pair info, write to `silver.ref_mission_location`.

**Source tables:**
- `bronze.mission`: `mission_id`, `device_id`, `start_date`, `end_date`, `location_title`, `street`, `street_number`, `zipcode`, `description`, `created_at`
- `bronze.location`: `location_id`, `location_title`, `street`, `street_number`, `zipcode`, `description` , `driving_direction`, `lat`, `lon`
- Join key: `location_title`

`bronze.location` is small (~45 rows). Pandas appropriate here.
1. merge location adn mission (onyl relvant cols)
2. clean files (save to dq)
3. refactor location descritopm fields so they are suiatbel for display in dashboard,
4. pair locations
    - Pairs: two devices, same street, opposite directions, overlapping deployment windows
    - Pair matching rules not yet defined — define before writing code
    - Output: `silver.ref_mission_location` — one row per deployment, enriched with coordinates and pair info

- Columns: device_id, location_title, street, lat, lon, start_date, deploy_end, is_pair, paired_mission_id
- Whether full replace or append depends on pair logic outcome from Task 3. Append is alwys preferred in case portal clears data, we do not want to lose ours


**Output columns for `silver.ref_mission_location`:**
- `mission_id`, `device_id`
- `deploy_start`, `deploy_end`  dates 2049/2100 → open-ended)
- `street`, `street_number`, `zipcode`
- `description` — longe rtext, may need parsing from `bronze.location`
- `lat`, `lon`
- `is_pair` (boolean), `paired_mission_id`

**Pair matching rules — partially agreed:**
- Same `street`
- Different `driving_direction` (used temporarily for matching, not in output)
- Overlapping `start_date`/`deploy_end` windows
- Whether `street_number` must also match — NOT yet decided, discuss with human first

**Scale:** ~45 location rows, ~44 missions. Pandas appropriate throughout.

**Append preferred** — do not full replace, in case portal clears historical data.

---

### Task 2 — Design and build `gold.dashboard` and gold.export_traffic
Aggregated, one row per `(mission_id, datum, stunde)`.

**Columns:**
- `datum` (DATE), `stunde` (SMALLINT 0-23)
- `mission_id`, `device_id`
- `location descrition` (several fields: postcode, street (likely used fro Dashboard diplay), street number, text field for special things liek schools)
- `lat`, `lon`
- `is_pair`, `paired_mission_id`
- Vehicle counts: `pkw`, `lkw`, `lfw`, `krad`, `fahrrad` etc.
- Speed metrics: `v_kfz`, `v_pkw`, `v_lkw`,
-  `v85` (85th percentile, excl. fahrrad)
- Modal shares (must sum to 100): `modal_share_pkw`, `modal_share_fahrrad`, `modal_share_lkw`, `modal_share_krad` (other, decide on how to split shoudl not show less than 5% modal share)

**Join:** `silver.traffic` → `silver.ref_mission_location` on `mission_id` + time window (`date_parsed` between `deploy_start` and `deploy_end`)

**Approach:** SQL aggregation, no pandas for the main query.


Schemas not yet finalised — discuss with human before writing DDL.

---

## Vehicle classes
| code | label |
|------|-------|
| 2 | PkwA — car with trailer |
| 3 | Lkw — lorry |
| 5 | Bus |
| 7 | Pkw — car (68% of rows) |
| 8 | LkwA — lorry with trailer |
| 9 | Sattel-Kfz — articulated HGV |
| 10 | Krad — motorcycle |
| 11 | Lfw — delivery van |
| 230 | Fahrrad — bicycle (18% of rows) |
| 6 | nk Kfz — unclassified (0.10%, keep as-is) |

Motorised classes for speed aggregation: `2,3,5,7,8,9,10,11`

---

## Key files to provide
3. `silver.py` — current working version
4. `utils/db.py` — connection helpers
5. `init.sql` — full DDL bronze/silver/gold
7. `dag.py` — both DAGs

---

## Open issues / ToDos

2. **Gold DDL** — `gold.traffic` in `init.sql` is old/stale, needs replacing with `gold.dashboard` and `gold.export`
5. **Superset** — needs reconnecting once gold tables are ready

---


## Open ToDos
1. Partition `silver.traffic` on rebuild — by date or `source_file` — to reduce disk temp space on large queries
2. `vehicle_class_label` vs lookup table — decide at gold/dashboard layer
3. `is_pair` underestimates pairs - check if helps to increase distance form 75 to 100m, also change code so that only last update is checked not update before that one (check last update=x adn only look at rows where last update=x)
4. Dedup check (see long text below




4. Query silver traffic for all rows that arrived after the traffic watermark and return the distinct set of (mission_id, date, hour)
5. if large apply chunking logic
6. aggregate within chunks, compute avg speed, modal share etc.
7. join location - log row without location as awarning adn omit, but copy into dq database
8. Upsert the enriched, aggregated rows into gold. Where a row for that (mission_id, date, hour) already exists, overwrite all metric and location columns and update gold_processed_at to reflect the recomputation time.
9. advance traffic watermark
10.  Detect changed pairing rows
Query silver.ref_mission_location for any rows whose updated_at is more recent than the location watermark. These are missions whose pairing metadata has changed since the last gold run.
— Apply pairing-only update to gold
For each changed mission, update only the three pairing columns — is_pair, paired_mission_id, pair_confidence — on existing gold rows. Restrict the update to gold rows whose date falls within 45 days of the mission's created_at. Rows outside that window are considered settled and are not touched.
— Advance location watermark
Update the silver.ref_mission_location watermark to reflect that pairing updates have been applied up to this point in time.



#### Dedup check
Critical Review of the Deduplication & Processing Strategy
ADR-001 — Download Tracking
Strong decisions:

Single tracker as source of truth is correct. Splitting it across DAGs would introduce drift.
Updating tracker after bronze ingestion (not download) is the right call — it keeps the two systems in sync. The re-download-on-failure tradeoff is well-reasoned.

Issues & concerns:
1. Tracker-filename coupling is a hidden fragility (Decision 8)
The tracker update parsing mission_id and chunk_end from the filename is a load-bearing implicit contract. If any upstream change touches the filename format — even a well-intentioned refactor — the tracker silently starts writing wrong dates or fails to parse. This should be an explicit schema with a version field, not an implicit contract documented in an ADR footnote.

Suggestion: Define a FILENAME_SCHEMA_VERSION constant shared between _download_into_parquet() and load_traffic_to_bronze(), and assert it at parse time. A mismatch should hard-fail, not silently corrupt the tracker.

2. consecutive_empty_weeks doesn't reset on resume
If a mission goes silent for 2 weeks, then delivers data on week 3, does consecutive_empty_weeks reset to 0? If not, the counter becomes meaningless over time. If yes, that reset logic needs to be explicitly stated and tested — it's currently absent from the ADR.

Suggestion: Add an explicit reset rule: counter resets to 0 on any successful non-empty download. Document it in the ADR.

3. The 3-week alert threshold is arbitrary and undifferentiated
Some missions may legitimately go quiet (seasonal sensors, maintenance). A flat threshold of 3 weeks sends false alerts and risks alert fatigue.

Suggestion: Consider a per-mission expected_cadence field in the tracker, or at minimum a suppress-until date, so known-quiet missions don't page.

4. max_active_runs=1 is a correctness crutch, not a guarantee
It prevents tracker race conditions within Airflow, but if a DAG is ever triggered manually, kicked off via API, or run in a different scheduler context, the concurrency assumption silently breaks. The ADR acknowledges "mild duplication risk on DAG retry" — but it doesn't acknowledge the scenario where the tracker itself gets corrupted by two concurrent writers.

Suggestion: Add an optimistic lock or ETag check on the tracker file in MinIO. On write, assert the file hasn't changed since it was read. If it has, abort and retry. This makes the tracker safe regardless of how DAGs are invoked.


ADR-002 — Silver Cleaning
Strong decisions:

Source-file idempotency is clean and correct.
Staging table as a quality gate is a good pattern — keeps promotion logic auditable.
Non-destructive flags are correct; you want raw signal preserved.

Issues & concerns:
5. Staging is ephemeral — this destroys your audit trail
"Flags are non-destructive" and "audit trail lives in staging until next truncation" are contradictory in practice. If the DAG runs nightly, the audit window is ~24 hours. Any investigation triggered by a downstream anomaly that surfaces days later finds staging already truncated.

Suggestion: Either (a) promote flagged rows to a persistent silver.rejected_traffic table instead of relying on staging, or (b) write a daily snapshot of flagged rows to a cheap MinIO parquet file. Option (b) is lower-overhead and consistent with the rest of the architecture.

6. The deduplication partition key may over-deduplicate
The partition key (device_id, date_raw, vehicle_class, speed_entry, speed_exit, length_dm) is very specific. This is good for catching exact re-sends, but it will silently drop two genuinely different vehicles that happen to share all six attributes within the same timestamp bucket. For dense traffic this is a real risk, especially for common vehicle classes at low speed variance.

Suggestion: If the portal includes any row-level sequence number, transaction ID, or even ingestion order within a file, include it in the partition key. If not, document explicitly that same-second coincidental duplicates are accepted losses, and estimate the frequency from historical data.

7. Bike speed ceiling (40 km/h) is hardcoded and undocumented
The 100 km/h ceiling for general traffic has an implicit engineering rationale (sensor max). The 40 km/h bike ceiling doesn't. Is it a legal limit, a sensor characteristic, or a domain assumption? If it's wrong for e-bikes or cargo bikes, you're silently nulling valid readings.

Suggestion: Document the source of the 40 km/h figure. If it's a regulatory limit rather than a sensor constraint, consider flagging rather than nulling — an e-bike doing 42 km/h is valid data, not a sensor error.


ADR-003 — Gold Aggregation
Strong decisions:

Watermark table with atomic advancement is correct.
Unioning the two invalidation paths into a single combo set is clean.
LEFT JOIN with NULL guard is the right call — partial rows are worse than missing rows.
gold_processed_at reflecting recomputation time is genuinely useful for audit.

Issues & concerns:
8. The single transaction may be too large for large mission sets
Wrapping read watermarks → compute combos → aggregate → upsert → advance watermarks in one transaction is elegant for correctness, but if the affected combo set is large (e.g. a location metadata change affecting years of history for a mission), the transaction can run for a very long time. Long-running transactions in Postgres hold locks, bloat WAL, and risk OOM on the aggregation side.

Suggestion: Add a cap: if affected combos exceed a configurable threshold (e.g. 10,000 rows), split into batches, each with its own transaction. Advance the watermark only after all batches commit. On failure mid-batch, the watermark stays at the pre-run value and the next run reprocesses from there — still correct.

9. Location change triggers full historical reprocessing — this is potentially catastrophic
"A location metadata change propagates to all historical gold hours for that mission on the next run." If a location record is corrected for a mission with 3 years of data, the next gold run silently rewrites thousands of rows. There's no gate, no diff check, no human review step.

Suggestion: Add a location_change_scope concept: by default, location changes only reprocess gold rows from the effective_from date of the new location value onward. Full historical reprocessing should require an explicit operator flag. This also requires adding an effective_from column to silver.ref_mission_location.

10. PERCENTILE_CONT(0.85) on sparse hours produces misleading v85
On hours with very few vehicle records (e.g. 3 vehicles at 3am), the 85th percentile is not statistically meaningful but gets written to gold as if it were. Downstream consumers may not know to distrust it.

Suggestion: Add a v85_sample_n column to gold.export recording the count of vehicles contributing to the v85 calculation. Let downstream consumers apply their own minimum-sample threshold. This is a low-cost addition that significantly improves the layer's usability.


Summary
#SeverityAreaIssue1HighADR-001Filename-tracker coupling is fragile, needs versioned contract2MediumADR-001consecutive_empty_weeks reset logic is unspecified5HighADR-002Ephemeral staging destroys audit trail within 24h6MediumADR-002Dedup key may silently drop coincidental duplicates in dense traffic8MediumADR-003Single large transaction risks lock contention and OOM9HighADR-003Unbounded historical reprocessing on any location change10LowADR-003Sparse-hour v85 is misleading without sample count3LowADR-001Alert threshold is undifferentiated across mission types4LowADR-001max_active_runs=1 is not a safe concurrency guarantee7LowADR-002Bike speed ceiling source undocumented
Issues 1, 5, and 9 are the ones I'd address before this goes to production. The rest are quality-of-life improvements, but they will bite you eventually.
