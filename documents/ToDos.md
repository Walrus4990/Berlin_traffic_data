# TODO — Berlin Traffic Pipeline
_Last updated: 2026-04-24_

## P1 — Blocking or data integrity risk

1. **DONE** Implement `write_tracker()` in `download_mission()` after successful chunk upload — without this portal is hit for all data every weekly run
2. **DONE** Audit datetime parsing and timezone handling throughout — verify `parse_date()` output is consistently timezone-aware (Europe/Berlin) across all functions that consume dates: `download_mission()`, `weekly_download()`, `ingest_missions()`, silver join logic
3. NULL speed values in gold — trace back through silver cleaning to source
4. Remove TEMP mission filter from `weekly_download()` before any prod run
5. SQL init scripts — confirm bronze/silver/gold schemas and tables are correctly defined in `sql/init/`

## P2 — Data quality

6. Check if `mission_id` should be added as column to `bronze.traffic` at load time — extract from `source_file` filename or add during merge with `bronze.mission`
7. Check if MISSION_RENAME and LOCATION_RENAME are necessary — if portal column names are already clean, drop renaming to reduce confusion
8. Audit ID uniqueness across mission_df, location_df, traffic files
9. Check `device_id` always arrives as clean int from portal
10. Silver cross-chunk dedup for prod
11. Silver `NOT IN` query — fix for large `processed_set`
12. Change `bronze.location` from full-replace to append once ID uniqueness confirmed

## P3 — Output and publishing

13. Change MinIO gold export from parquet to CSV — calculate expected row counts first, may need chunking. Civil servants cannot open parquet
14. Two gold files in MinIO (`traffic_today` and `traffic_latest`) — decide if both needed
15. Rename MinIO folder from `gold/` to something intuitive for civil servants e.g. `exports/` or `open-data/`
16. Check if MinIO sub-folder can be pointed to an API endpoint
17. Clean location display column for dashboard — strip device prefix (e.g. 'DD 8472 Halker Zeile' → 'Halker Zeile')

## P4 — Code quality and prod readiness

18. Replace f-strings with `%s` logging throughout
19. Superset connection not persisting — DB connection still needs setting manually after each run. Debug `refresh_superset` API call
20. Airflow migration task for prod SQL init on government Kubernetes cluster
21. Build initial load DAG — same structure as weekly but calls `complete_download()` instead of `weekly_download()`
22. Define no-data alert — if `bronze.traffic` returns 0 new rows after load, raise error/alert rather than silently continuing
