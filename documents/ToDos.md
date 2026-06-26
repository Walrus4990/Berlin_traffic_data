
# TODO — Berlin Traffic Pipeline



#### TODO — after first weekly DAG run
Check bronze.chunk_download_events for any failed rows with inverted date ranges. If they appear in the weekly run, the assumption above is wrong and the complete boolean fix must be implemented in load_traffic_to_bronze() in bronze_data_layer.py.

### DQ database — do in one pass (touch init_dq.sql and test_ingest.py together)
- [ ] Add `mission_start` and `mission_end` to `mission_completeness` table.
- [ ] Truncate `mission_completeness` and `missing_segments` before each run, or add `run_id` to distinguish runs.
- [ ] Confirm `today-1` fix resolves pattern 1 missing segments — rerun `validate_bronze` after fix and check DQ tables.

### Data integrity — investigate
- [ ] NULL speed values in gold — trace back through silver cleaning to source.
- [ ] Investigate stub segment filename mismatch at mission start — check if downloaded filenames match what completeness check expects for opening stubs.

### Human portal checks
- [ ] Manually check portal for missions 89637, 89638, 97589 — attempt manual download to confirm if data is genuinely blank or pipeline issue.
- [ ] Manually check portal for 32040 — entirely empty across all segments.
- [ ] Manually check portal for 54814 — 4 missing segments in Oct/Nov 2020 and 2021.

### Schema and init scripts
- [ ] SQL init scripts — confirm bronze/silver/gold schemas and tables correctly defined in `sql/init/`.
- [ ] Standardise table creation — replace inline `CREATE TABLE IF NOT EXISTS` with SQL init files throughout.

DQ table: doubling of missions in mission_copmleteness. investigate all DQ database tables for duploicates & go through code adn check if duplicates can be eradicated.


### db.py and DQ module — do in one pass
- [ ] `_write_chunk_event()` creates a new engine on every invocation inside the download loop — ~900 chunks means potentially many engine creations. Refactor to create engine once in `download_mission()` and pass as parameter. Discussion: with 20s sleep between chunks and failures being a small fraction of 900, overhead may be negligible — decide whether to fix or accept as is.


### Output and publishing — do in one pass
- [ ] Check if MinIO sub-folder can be pointed to an API endpoint.

### Data quality checks
- [ ] Define no-data alert — if `bronze.traffic` returns 0 new rows after load, raise error/alert rather than silently continuing.
- [ ] Check parquet file sizes in MinIO — validate memory assumptions for prod environment with 7-8GB RAM.

### Infrastructure — deferred to prod environment
- [ ] Airflow migration task for prod SQL init on government Kubernetes cluster.


### Investigations — low urgency
- [ ] Check if MinIO sub-folder can be pointed to an API endpoint.



### Download results:
complete download log: Start date > end date errors — missions 40671, 40687, 94076, 94074, 97594, 69502, 40688, 72976, 73698, 69501, 54814, 40718, 43114, 71077. All logged to bronze.segment_download_events. This is a data quality issue in the source — the portal has missions where end date is before start date. Not a code bug.
Empty segments — multiple missions returned no data (32040 entirely empty across many months, 89637, 89638, 97589, 40715, 40716, 40714). All correctly logged to DQ.
Successful uploads — missions 74739, 45098, 99512, 99516, 90938, 89639, 97593, 97595, 97596, 97592, 99511, 76539, 76538, 88538, 88539, 71078, 40963, 40964, 72973, 72975, 69478, 69481 all uploaded to MinIO.

mission 89637 shows segments being skipped up to 20260101 but nothing loaded for Feb, Mar, Apr 2026 — which matches the empty segments we saw in complete_download. Same for 89638 and 97589.



## TODO — Pagination in ddweb_ingest_ref

MISSIONS_PAYLOAD and LOCATIONS_PAYLOAD both hardcode "page": 1. If the portal paginates and either list exceeds one page, we silently fetch only the first page. Why it matters: Currently 44 missions and ~45 locations. If the portal default page size is 50, we are already close to the limit for missions. Any new mission pushes us over and we silently lose data.
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

##
Issues & concerns:
5. Staging is ephemeral — this destroys your audit trail
"Flags are non-destructive" and "audit trail lives in staging until next truncation" are contradictory in practice. If the DAG runs nightly, the audit window is ~24 hours. Any investigation triggered by a downstream anomaly that surfaces days later finds staging already truncated.

Suggestion: Either (a) promote flagged rows to a persistent silver.rejected_traffic table instead of relying on staging, or (b) write a daily snapshot of flagged rows to a cheap MinIO parquet file. Option (b) is lower-overhead and consistent with the rest of the architecture.



7. Bike speed ceiling (40 km/h) is hardcoded and undocumented
The 100 km/h ceiling for general traffic has an implicit engineering rationale (sensor max). The 40 km/h bike ceiling doesn't. Is it a legal limit, a sensor characteristic, or a domain assumption? If it's wrong for e-bikes or cargo bikes, you're silently nulling valid readings.

Suggestion: Document the source of the 40 km/h figure. If it's a regulatory limit rather than a sensor constraint, consider flagging rather than nulling — an e-bike doing 42 km/h is valid data, not a sensor error.


### — Gold Aggregation
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





🟠 Logic Issues (Not Yet Addressed)
5. load_all_to_gold — gold_processed_at never set on fresh INSERT
Only set in the ON CONFLICT ... DO UPDATE. New rows get NULL, which breaks the watermark recovery query SELECT MAX(gold_processed_at). Fix: add gold_processed_at, NOW() to the INSERT column list and SELECT.

8. load_dashboard — watermark filter may produce incomplete daily totals
WHERE gold_processed_at > :watermark can miss hourly rows for a date that was partially loaded in a prior run. As discussed, consider filtering on date IN (SELECT DISTINCT date FROM gold.export WHERE gold_processed_at > :watermark) instead.

🟡 Minor / Polish
9. _update_pairs — unfinished TODO
python## i want to extract the number of missions & mission Id...
Needs a RETURNING mission_id clause on the UPDATE plus logging of the returned IDs, or remove the comment.
10. load_all_to_gold — result used outside with block
result.rowcount and return result.rowcount, today are both outside the with engine.connect() block. Works due to SQLAlchemy caching but fragile — move the logger line inside, and assign rowcount = result.rowcount before the block closes.
11. load_dashboard — same result scoping issue as #10
