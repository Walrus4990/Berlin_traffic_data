# ADR: Bronze Layer Data Quality Strategy

## Context
The pipeline ingests traffic sensor data from the DDWeb portal by mission,
split into monthly segments due to portal limitations. Downloads are chunked,
some segments are empty, some fail. After download, parquet files are loaded
into postgres bronze.traffic. We need to track what happened at each stage.

## Decision
Two complementary DQ mechanisms, both writing to a dedicated postgres-dq database.

### 1. Download event logging (at download time)
**Where:** `_write_chunk_event()` in `ddweb_ingest_traffic.py`
**Trigger:** called inside `download_mission()` at two points:
- `df.empty` — portal returned a file with no data
- `except Exception` — any chunk-level failure (portal error, date error, network etc.)

**Writes to:** `bronze.segment_download_events`
**Captures:** mission_id, segment_start, segment_end, status (`empty` or `failed`), reason (exception message or NULL)
**Scope:** chunk-level only. Mission-level failures in `complete_download()` are not captured here — they remain in Airflow logs only.

### 2. Bronze completeness check (after load)
**Where:** `check_bronze_completeness(run_type)` in `tests/test_ingest.py`
**Trigger:** called as `validate_bronze` task in both DAGs, after `load_traffic_to_bronze`

**Logic:**
- Reads `bronze.mission` for all missions and their start/end dates
- Computes expected segment filenames deterministically using `get_chunks()` — same logic as the downloader, capped at `min(end_date, today - 1 day at 23:59:59)`
- Compares expected filenames against `source_file` values in `bronze.traffic`
- Writes summary and missing segments to DQ tables

**Writes to:**
- `bronze.mission_completeness` — one row per mission per run: expected_segments, actual_segments, missing_count
- `bronze.missing_segments` — one row per missing filename

## Timezone
All `run_at` timestamps written in Europe/Berlin timezone, consistent with pipeline ADR.

## Scope
This ADR covers bronze ingestion only. Silver DQ flags (speed, duplicates, unknown device etc.) are computed in `silver_data_layer.py` and persistence to postgres-dq is deferred to the silver/gold DQ refactor.

## Consequences
- Every segment failure is captured with a reason at download time
- After each pipeline run, expected vs actual segment counts are queryable per mission
- Missing segments are individually identifiable by filename
- Two runs without truncation produce duplicate rows in completeness tables — truncate before run or add run_id (open ToDo)
