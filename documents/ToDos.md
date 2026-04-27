
# TODO — Berlin Traffic Pipeline
_Last updated: 2026-04-27_

## P1 — Blocking or data integrity risk
1. NULL speed values in gold — trace back through silver cleaning to source
2. Remove TEMP mission filter from `weekly_download()` before any prod run
3. SQL init scripts — confirm bronze/silver/gold schemas and tables are correctly defined in `sql/init/`
4. Standardise table creation approach across traffic and DQ databases — replace inline `CREATE TABLE IF NOT EXISTS` with SQL init files throughout
5. Fix weekly DAG `start_date` and `schedule_interval` to `datetime(2026, 4, 28)` and `0 5 * * 1` before production

## P2 — Data quality
6. Check if `mission_id` should be added as column to `bronze.traffic` at load time — extract from `source_file` filename or add during merge with `bronze.mission`
7. Check if MISSION_RENAME and LOCATION_RENAME are necessary — if portal column names are already clean, drop renaming to reduce confusion
8. Audit ID uniqueness across mission_df, location_df, traffic files
9. Check `device_id` always arrives as clean int from portal
10. Silver cross-chunk dedup for prod
11. Silver `NOT IN` query — fix for large `processed_set`
12. Change `bronze.location` from full-replace to append once ID uniqueness confirmed
13. Define no-data alert — if `bronze.traffic` returns 0 new rows after load, raise error/alert rather than silently continuing
14. Write `tests/ingest_test_weekly.py` for weekly download validation
15. Check parquet file sizes in MinIO after initial download completes — validate memory assumptions for prod environment with 7-8GB RAM

## P3 — Output and publishing
16. Change MinIO gold export from parquet to CSV — calculate expected row counts first, may need chunking. Civil servants cannot open parquet
17. Two gold files in MinIO (`traffic_today` and `traffic_latest`) — decide if both needed
18. Rename MinIO folder from `gold/` to something intuitive for civil servants e.g. `exports/` or `open-data/`
19. Check if MinIO sub-folder can be pointed to an API endpoint
20. Clean location display column for dashboard — strip device prefix (e.g. 'DD 8472 Halker Zeile' → 'Halker Zeile')

## P4 — Code quality and prod readiness
21. Replace f-strings with `%s` logging throughout
22. Superset connection not persisting — DB connection still needs setting manually after each run. Debug `refresh_superset` API call
23. Airflow migration task for prod SQL init on government Kubernetes cluster
24. Refactor `save_qa_report()` out of `db.py` — move DQ logic to DQ module, use `save()` instead
25. Review and standardise file naming across `etl/` and `utils/`
26. Full refactor and rename — replace bronze/silver/gold naming with descriptive alternatives across DAG, ETL files, DB schemas, and utils
27. Rename bronze/silver/gold schema names across traffic DB and DQ DB in one go during naming refactor
28. Rename DAG to reflect TS only structure
29. Initial DAG currently stops at bronze validation — decide whether it should run the full pipeline (silver → gold → publish → superset) after initial load completes

## Misc
- Debug/quality assure download records
