"""
Berlin Traffic Pipeline DAG
Weekly orchestration: ingest → bronze → silver → gold → Superset refresh
"""
from airflow import DAG
from airflow.operators.python import PythonOperator, BranchPythonOperator
from airflow.providers.postgres.operators.postgres import PostgresOperator
from airflow.utils.dates import days_ago
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)

# ── Default args ──────────────────────────────────────────────────────────────
default_args = {
    "owner": "lucia",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

# ── Task functions ────────────────────────────────────────────────────────────

def ingest_missions_and_locations(**kwargs):
    """Fetch missions and locations from DDWeb → bronze tables"""
    from etl.ddweb_auth import DDWebAuth
    from etl.ddweb_ingest import fetch_missions, fetch_locations
    import psycopg2, os

    auth = DDWebAuth()
    auth.ensure_authenticated()

    missions_df  = fetch_missions(auth)
    locations_df = fetch_locations(auth)

    # Push to XCom for next task
    kwargs["ti"].xcom_push(key="missions_count",  value=len(missions_df))
    kwargs["ti"].xcom_push(key="locations_count", value=len(locations_df))
    logger.info(f"Fetched {len(missions_df)} missions, {len(locations_df)} locations")


def check_new_missions(**kwargs):
    """Compare fetched missions to bronze.deployment → branch decision"""
    import psycopg2

    conn = psycopg2.connect(
        host="postgres-traffic", dbname="berlin_traffic",
        user="traffic", password="traffic"
    )
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM bronze.deployment")
    existing = cur.fetchone()[0]
    conn.close()

    if existing == 0:
        logger.info("No existing missions — full update path")
        return "full_update"
    else:
        logger.info("Missions exist — checking for new ones")
        return "reduced_update"


def full_update(**kwargs):
    """New mission detected: update bronze, silver_active_mission, run full clean"""
    logger.info("Running FULL update pipeline...")
    # TODO: implement full clean using etl/transform.py


def reduced_update(**kwargs):
    """No new mission: lookup location, run reduced clean"""
    logger.info("Running REDUCED update pipeline...")
    # TODO: implement reduced clean using etl/transform.py


def ingest_traffic_files(**kwargs):
    """Download weekly traffic Excel files from DDWeb → bronze.traffic"""
    from etl.ddweb_auth import DDWebAuth
    from etl.ddweb_ingest import fetch_missions
    from etl.ddweb_ingest_traffic import complete_download

    auth = DDWebAuth()
    missions_df = fetch_missions(auth)
    complete_download(auth, missions_df)
    logger.info("Traffic files downloaded")


def refresh_superset(**kwargs):
    """Trigger Superset dataset cache refresh via API"""
    import requests, os

    session = requests.Session()
    base = "http://superset:8088"

    # Login
    r = session.post(f"{base}/api/v1/security/login", json={
        "username": os.getenv("SUPERSET_ADMIN_USER", "admin"),
        "password": os.getenv("SUPERSET_ADMIN_PASSWORD", "admin"),
        "provider": "db"
    })
    token = r.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}"}

    # Refresh all datasets
    datasets = session.get(f"{base}/api/v1/dataset/", headers=headers).json()
    for ds in datasets.get("result", []):
        session.put(
            f"{base}/api/v1/dataset/{ds['id']}/refresh",
            headers=headers
        )
        logger.info(f"Refreshed dataset: {ds['table_name']}")


# ── DAG definition ────────────────────────────────────────────────────────────
with DAG(
    dag_id="berlin_traffic_pipeline",
    default_args=default_args,
    start_date=days_ago(1),
    schedule_interval="@weekly",
    catchup=False,
    tags=["berlin", "traffic", "superset"],
) as dag:

    t_ingest_ref = PythonOperator(
        task_id="ingest_missions_locations",
        python_callable=ingest_missions_and_locations,
    )

    t_branch = BranchPythonOperator(
        task_id="check_new_missions",
        python_callable=check_new_missions,
    )

    t_full = PythonOperator(
        task_id="full_update",
        python_callable=full_update,
    )

    t_reduced = PythonOperator(
        task_id="reduced_update",
        python_callable=reduced_update,
    )

    t_ingest_traffic = PythonOperator(
        task_id="ingest_traffic_files",
        python_callable=ingest_traffic_files,
        trigger_rule="none_failed_min_one_success",
    )

    t_gold_location = PostgresOperator(
        task_id="refresh_gold_by_location",
        postgres_conn_id="postgres_traffic",
        sql="sql/tempelhof_queries/06_ds_map.sql",
    )

    t_gold_vehicle = PostgresOperator(
        task_id="refresh_gold_by_vehicle",
        postgres_conn_id="postgres_traffic",
        sql="sql/tempelhof_queries/01_ds_modal_share.sql",
    )

    t_gold_time = PostgresOperator(
        task_id="refresh_gold_by_time",
        postgres_conn_id="postgres_traffic",
        sql="sql/tempelhof_queries/03_ds_peaks.sql",
    )

    t_superset = PythonOperator(
        task_id="refresh_superset_cache",
        python_callable=refresh_superset,
        trigger_rule="all_done",
    )

    # ── Dependencies ──────────────────────────────────────────────────────────
    t_ingest_ref >> t_branch
    t_branch >> [t_full, t_reduced]
    [t_full, t_reduced] >> t_ingest_traffic
    t_ingest_traffic >> [t_gold_location, t_gold_vehicle, t_gold_time]
    [t_gold_location, t_gold_vehicle, t_gold_time] >> t_superset
