# ADR-001: Download Tracking and Deduplication Strategy
Date: 2026-04-23
Status: Accepted

## Context:
The pipeline downloads traffic sensor data from the DDWeb portal for 44+ missions. Data arrives nightly. Two DAGs exist: an initial historical load and a weekly incremental load. We needed a strategy to track download progress, prevent duplicate processing, and handle failures gracefully.

## Decisions:
1. Single shared download tracker (download_tracker.json in MinIO)
One JSON file keyed by mission_id. Tracks last_downloaded_to and consecutive_empty_weeks per mission. Both DAGs share it. Rationale: single source of truth, no handover logic needed between DAGs.
2. Tracker updated after successful bronze ingestion, not after download
Ensures tracker and bronze.traffic stay in sync. If ingestion fails, next run re-downloads from portal. Re-download is wasteful but harmless — MinIO overwrites same file, bronze dedup prevents duplicate rows, tracker then updates correctly.
3. Active mission filter uses ToDate > today
More robust than sentinel date lists. Handles any future date a human might enter. Closed missions never appear in tracker.
4. chunk_end = min(ToDate, today)
Captures final days of a closing mission mid-week.
5. Three-layer deduplication

MinIO: file presence check before portal hit
Bronze: source_file dedup on ingestion
Silver: source_file dedup on processing
Accepted mild duplication risk (one file per DAG run) from concurrent runs — caught by silver dedup.

6. max_active_runs=1 on both DAGs
Prevents portal conflicts and tracker race conditions.
7. Empty file handling
Two retries with doubling sleep (10s → 20s) before skipping. consecutive_empty_weeks incremented in tracker. Alert email triggered at 3 consecutive empty weeks. Next weekly run naturally covers missed weeks via last_downloaded_to + 1 day.

## Consequences:
Portal re-hit on bronze ingestion failure (acceptable, rare)
Mild duplicate risk on DAG retry (acceptable, caught downstream)
No data loss on empty portal response beyond 3 weeks without alert
