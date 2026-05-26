import os
import pendulum
from datetime import timedelta
from airflow.sdk import dag, task

DAG_DIR = os.path.dirname(os.path.abspath(__file__))
REQUIREMENTS_PATH = os.path.join(DAG_DIR, "requirements.txt")

with open(REQUIREMENTS_PATH, "r") as f:
    REQUIREMENTS = [
        line.strip()
        for line in f
        if line.strip() and not line.startswith("#") and "apache-airflow" not in line.lower()
    ]

# ── DAG ID ──────────────────────────────────────────────────────────────

@dag(
    dag_id="ts_traffic_weekly_load",
    schedule="0 6 * * MON",
    start_date=pendulum.datetime(2026, 5, 13, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    tags=["ts", "traffic", "weekly"],
    default_args={
        "owner": "ts",
        "retries": 2,
        "retry_delay": timedelta(hours=12),  #code is dynamic so should catch up failed dag runs without needing retry or catch-up
    }
)
def ts_traffic_weekly_load():
    """
    ### Tempelhof Schöneberg weekly traffic data ingest
    """

# ── Tasks  ────────────────────────────────────────────────────────────

    @task.virtualenv(requirements=REQUIREMENTS,
                     #execution_timeout=timedelta(minutes=15)  #commented out to fail fast uncomment in prod
    )
    def run_load_ref_to_bronze(dag_dir: str) -> None:
        """Fetch missions and locations from DDWeb portal → bronze.mission, bronze.location"""
        import logging
        import sys
        sys.path.insert(0, dag_dir)
        from etl.bronze import load_ref_to_bronze
        logger = logging.getLogger(__name__)
        new_mission, new_location = load_ref_to_bronze()
        logger.info("%d new mission rows and %d new location rows appended", new_mission, new_location)


    @task.virtualenv(requirements=REQUIREMENTS,
                     #execution_timeout=timedelta(hours=4)  #commented out to fail fast uncomment in prod
    )
    def run_ingest_traffic(dag_dir: str) -> None:
        """Download this week's traffic files from DDWeb portal → MinIO"""
        import logging
        import sys
        sys.path.insert(0, dag_dir)
        from etl.ddweb_ingest_traffic import weekly_download
        logger = logging.getLogger(__name__)
        weekly_download()
        logger.info("Traffic files downloaded to MinIO")

    @task.virtualenv(requirements=REQUIREMENTS,
                     #execution_timeout=timedelta(hours=3)  #commented out to fail fast uncomment in prod
    )
    def run_load_traffic_to_bronze(dag_dir: str) -> None:
        """Read new parquet files from MinIO → append to bronze.traffic"""
        import logging
        import sys
        sys.path.insert(0, dag_dir)
        from etl.bronze import load_traffic_to_bronze
        logger = logging.getLogger(__name__)
        rows = load_traffic_to_bronze()
        logger.info("Traffic rows appended to bronze: %d", rows)

    @task.virtualenv(requirements=REQUIREMENTS,
                     #execution_timeout=timedelta(hours=3)  #commented out to fail fast uncomment in prod
    )
    def run_validate_bronze(dag_dir: str) -> None:
        """Checks download, saves missing file info & error messages  → append to bronze.dq"""
        import logging
        import sys
        sys.path.insert(0, dag_dir)
        from tests.test_ingest import check_bronze_completeness
        logger = logging.getLogger(__name__)
        result = check_bronze_completeness("weekly")
        logger.info("Validation result: %s", result)

    @task.virtualenv(requirements=REQUIREMENTS,
                     #execution_timeout=timedelta(hours=3)  #commented out to fail fast uncomment in prod
    )
    def run_load_traffic_to_silver(dag_dir: str) -> None:
        """Clean and enrich bronze data into silver tables"""
        import logging
        import sys
        sys.path.insert(0, dag_dir)
        from etl.silver import load_traffic_to_silver
        logger = logging.getLogger(__name__)
        rows = load_traffic_to_silver()
        logger.info("Traffic rows written to silver: %d", rows)

    @task.virtualenv(requirements=REQUIREMENTS,
                     #execution_timeout=timedelta(hours=3)  #commented out to fail fast uncomment in prod
    )
    def run_validate_silver(dag_dir: str) -> None:
        """Runs DQ checks on silver.staging_traffic and writes flag reports to DQ database."""
        import logging
        import sys
        sys.path.insert(0, dag_dir)
        from tests.test_silver import check_silver_dq
        logger = logging.getLogger(__name__)
        result = check_silver_dq()
        logger.info("Validation result: %s", result)


    @task.virtualenv(requirements=REQUIREMENTS,
                     #execution_timeout=timedelta(hours=3)  #commented out to fail fast uncomment in prod
    )
    def run_gold_layer(dag_dir: str) -> None:
        """Run gold aggregation using Monica's gold_data_layer.py"""
        import logging
        import sys
        sys.path.insert(0, dag_dir)
        from etl.gold import run_gold
        from utils.db import get_traffic_engine
        logger = logging.getLogger(__name__)
        engine= get_traffic_engine()
        result = run_gold(engine)
        logger.info("Gold layer result: %s", result)

    @task.virtualenv(requirements=REQUIREMENTS,
                     #execution_timeout=timedelta(hours=3)  #commented out to fail fast uncomment in prod
    )
    def run_publish(dag_dir: str) -> None:
        """Export gold.traffic to MinIO as CSV"""
        import logging
        import sys
        sys.path.insert(0, dag_dir)
        from etl.publish import publish_gold
        logger = logging.getLogger(__name__)
        publish_gold()
        logger.info("Gold data published to MinIO")

#BUGGY _ NEEDS TIDYING

# def refresh_superset(**kwargs):
#     import os, requests
#     from utils.db import get_traffic_engine

#     base = "http://superset:8088"
#     session = requests.Session()

#     # --- login ---
#     r = session.post(f"{base}/api/v1/security/login", json={
#         "username": os.getenv("SUPERSET_ADMIN_USER", "admin"),  #remove hardcoding in prod
#         "password": os.getenv("SUPERSET_ADMIN_PASSWORD", "admin"),
#         "provider": "db"
#     })
#     r.raise_for_status()
#     token = r.json()["access_token"]
#     headers = {"Authorization": f"Bearer {token}"}

#     csrf = session.get(f"{base}/api/v1/security/csrf_token/", headers=headers)
#     csrf_token = csrf.json()["result"]
#     headers["X-CSRFToken"] = csrf_token
#     headers["Referer"] = base

#    # ---------------- DB connection ----------------
#     # TODO: replace with env var — get_traffic_engine() should not be used to extract URI

#     engine= get_traffic_engine()
#     sqlalchemy_uri = str(engine.url)

#     dbs = session.get(f"{base}/api/v1/database/", headers=headers).json()

#     db = next(
#         (d for d in dbs.get("result", []) if d.get("database_name") == "traffic_db"),
#         None
#     )

#     if not db:
#         resp = session.post(f"{base}/api/v1/database/", json={
#             "database_name": "traffic_db", #why the name, check on final tidy - it's teh superset db connection'
#             "sqlalchemy_uri": sqlalchemy_uri
#         }, headers=headers)
#         db = resp.json()

#     db_id = db["id"]

#     # ---------------- dataset: gold.traffic ----------------
#     datasets = session.get(f"{base}/api/v1/dataset/", headers=headers).json()

#     exists = any(
#         d.get("schema") == "gold" and d.get("table_name") == "traffic"
#         for d in datasets.get("result", [])
#     )

#     if not exists:
#         session.post(f"{base}/api/v1/dataset/", json={
#             "database": db_id,
#             "schema": "gold",
#             "table_name": "traffic"
#         }, headers=headers)

#     # ---------------- dashboard import ----------------
#     try:
#         with open("/app/superset_home/exports/dashboard_export_20260419T194107.zip", "rb") as f:
#             session.post(
#                 f"{base}/api/v1/dashboard/import/",
#                 headers=headers,
#                 files={"formData": f},
#                 data={"overwrite": "true", "passwords": '{"databases/traffic_db.yaml": "traffic"}'}
#             )
#     except FileNotFoundError:
#         logger.warning("Dashboard zip not found, skipping import")



    # ── Dependencies ──────────────────────────────────────────────────────────
    bronze_ref = run_load_ref_to_bronze(dag_dir=DAG_DIR)
    ingest = run_ingest_traffic(dag_dir=DAG_DIR)
    bronze_traffic = run_load_traffic_to_bronze(dag_dir=DAG_DIR)
    bronze_validate = run_validate_bronze(dag_dir=DAG_DIR)
    silver_traffic = run_load_traffic_to_silver(dag_dir=DAG_DIR)
    silver_validate = run_validate_silver(dag_dir=DAG_DIR)
    gold = run_gold_layer(dag_dir=DAG_DIR)
    publish = run_publish(dag_dir=DAG_DIR)

    [bronze_ref, ingest] >> bronze_traffic >> bronze_validate
    bronze_traffic >> silver_traffic >> gold >> publish
    silver_traffic >> silver_validate
    #Superset needs adding once fixed

ts_traffic_weekly_load()
