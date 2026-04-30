
# TODO — Berlin Traffic Pipeline
_Last updated: 2026-04-27_
## Technical Debt
- [ ] Airflow 2.7.0 / Python 3.8 EOL — plan upgrade path when prod environment allows.
      Risks: DAG API changes, provider packages unbundled, DB migration, dependency breaks.
      Do in a separate branch with full test run before touching prod.
- [ ] Airflow admin credentials (admin/admin) hardcoded in compose — move to .env vars
      AIRFLOW_ADMIN_USER and AIRFLOW_ADMIN_PASSWORD

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


## MinIO / Prod Integration
- [ ] Confirm MinIO endpoint, access key, secret key with Civitas team
- [ ] Swap MINIO_ROOT_USER/PASSWORD to MINIO_ACCESS_KEY/SECRET_KEY for prod
- [ ] Check ETL Python client (boto3 vs minio) and align env var names accordingly
- [ ] Confirm whether SSL needed for Civitas MinIO endpoint

## Infrastructure
- [ ] Check prod client VM memory limits and adjust mem_limit values accordingly.
      Current: scheduler 1500m, webserver 1000m, postgres instances 512m.
      Risk: silent OOM-kill if load increases.




Write empty/failed chunk events to DQ DB alongside logger calls in _download_into_parquet() and download_mission()
Manually check portal for 89637, 97589, 32040 to understand empty chunks
Fix timezone-naive datetime.datetime.now() in initial_load_dag.py — DONE
Wipe MinIO and tracker, rerun clean full download after all fixes confirmed working



Session 1: Fix check_bronze_completeness() only. Define done: DQ table shows correct expected/actual counts for all 44 missions. Nothing else.
Session 2: Fix the date format bug and rerun clean full download. Define done: all missions downloaded, tracker complete, bronze loaded.
Session 3: Silver layer — only once bronze is confirmed clean.
Session 4: Refactor and tidy — only once pipeline works end to end.
Rule for each session: write the done criteria at the top of the chat before writing any code. If something new comes up, add to ToDo and ignore it until its session.



# Migration to-do: switch to PostgresHook
## Why we're making this change

The client runs a managed Kubernetes cluster where we do not control the environment.
This means our current approach of reading `POSTGRES_TRAFFIC_*` env vars will break
on their infrastructure — those vars won't exist, so `os.getenv()` returns `None` and
the connection fails silently.

Their Airflow instance will have Postgres registered as a named connection in Airflow's
own Connections store (standard practice in managed K8s Airflow setups). The correct
pattern is to reference that connection by its `conn_id` via `PostgresHook` — Airflow
resolves the credentials internally, and our code never needs to know the host,
password, or port.

This also means:
- credentials are managed by the client's team, not stored in our codebase or .env files
- if they rotate credentials, they update one place in their Airflow UI — no redeploy needed
- our code is portable: it works identically in local Docker (via `AIRFLOW_CONN_*` env var)
  and in their K8s cluster (via their Connections config)

The change is minimal — one function in `utils/db.py`, drop the context manager pattern
in the ETL files, DAGs are untouched.

## 1. Ask the client
- [ ] Confirm the `conn_id` they use for Postgres in their Airflow setup (probably `"postgres_conn"` but confirm before hardcoding)


## 2. Update the code
- [ ] Rewrite `get_traffic_engine()` in `utils/db.py`:
```python
  from airflow.providers.postgres.hooks.postgres import PostgresHook

  def get_traffic_engine(conn_id: str = "postgres_conn"):
      return PostgresHook(postgres_conn_id=conn_id).get_sqlalchemy_engine()
```
- [ ] Find every `with get_traffic_engine() as engine:` across all ETL files (bronze, silver, gold) and replace with `engine = get_traffic_engine()` — drop the context manager, PostgresHook doesn't use one
- [ ] DAG files need no changes

## 3. Reconfigure Docker for local testing
- [ ] Remove `POSTGRES_TRAFFIC_HOST`, `POSTGRES_TRAFFIC_USER`, `POSTGRES_TRAFFIC_PASSWORD`, `POSTGRES_TRAFFIC_DB`, `POSTGRES_TRAFFIC_PORT` env vars from the Airflow service in `compose.yml` — confirms your code no longer relies on them
- [ ] Add this to the Airflow service environment in `compose.yml` instead:
```yaml
  AIRFLOW_CONN_POSTGRES_CONN: "postgresql://youruser:yourpassword@postgres-traffic:5432/yourdb"
```
  This tells Airflow about the connection via env var — mimics how their K8s cluster manages it, no UI clicking needed on every restart

## 4. Test locally
- [ ] Bring compose stack up and trigger the DAG manually
- [ ] Confirm bronze, silver, gold layers all write successfully
- [ ] Confirm Superset refresh still works

## 5. Deploy
- [ ] Send client the `conn_id` you're using so they can verify it matches their Airflow Connections config
- [ ] Remove any leftover `POSTGRES_TRAFFIC_*` vars from any `.env` files or CI/CD configs

etl/ddweb_ingest_traffic.py — _write_chunk_event calls get_dq_engine() on every invocation inside a loop. Refactor to create engine once in download_mission() and pass as parameter.
etl/ddweb_ingest_traffic.py — active_missions filtered to hardcoded IDs [89637, 89639] — marked TEMP, remove before prod.
dag/berlin_traffic_pipeline.py — refresh_superset uses get_traffic_engine() to extract raw URI and pass to Superset API. Needs rethinking for prod.
silver_data_layer.py — step_flag_duplicates operates within chunks only; cross-chunk duplicates not caught. Acceptable for now, address for prod.
