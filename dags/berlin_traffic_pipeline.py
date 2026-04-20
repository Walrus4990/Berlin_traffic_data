"""
Berlin Traffic Pipeline DAG
Weekly orchestration: ingest → bronze → silver → gold → Superset refresh
"""
from airflow import DAG
from airflow.operators.python import PythonOperator, BranchPythonOperator
from airflow.providers.postgres.operators.postgres import PostgresOperator
from airflow.operators.empty import EmptyOperator
from airflow.utils.dates import days_ago
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)

# ── Default args ──────────────────────────────────────────────────────────────
default_args = {
    "owner": "berlin",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

# ── Task functions ────────────────────────────────────────────────────────────

def fetch_and_load_missions(**kwargs):
    from etl.ddweb_auth import DDWebAuth
    from etl.ddweb_ingest_ref import fetch_missions, fetch_locations #check if this is teh more efficient functin to call
    import psycopg2, os  #the sql connection shoudl run via utils not her in the DAG, I think but need to check

    auth = DDWebAuth()
    auth.ensure_authenticated()

    with get_traffic_engine() as engine:
        new_mission_detected, rows_added = fetch_and_ingest_missions(auth, engine)

    #store a short value in Airflow: True = a new mission ID was found, run the full update path. False = no change, run the reduced path
    kwargs["ti"].xcom_push(key="new_mission_detected", value=new_mission_detected)
    logger.info(f"new_mission_detected={new_mission_detected}, rows_added={rows_added}")


def check_new_missions(**kwargs):
    """Compare fetched missions to bronze.mission → branch decision"""
    import psycopg2

    conn = psycopg2.connect(
        host="postgres-traffic", dbname="berlin_traffic",
        user="traffic", password="traffic"
    )
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM bronze.mission")
    existing = cur.fetchone()[0]
    conn.close()


# ----- load locations if new missions
def fetch_and_load_locations(**kwargs):
    from etl.ddweb_auth import DDWebAuth
    from etl.bronze_data_layer import fetch_and_ingest_locations
    from utils.db import get_traffic_engine

    auth = DDWebAuth()
    auth.ensure_authenticated()

    with get_traffic_engine() as engine:
        rows = fetch_and_ingest_locations(auth, engine)
    logger.info(f"Locations loaded: {rows} rows")


def load_bronze_traffic(**kwargs):
    from etl.bronze_data_layer import ingest_traffic
    from utils.db import get_traffic_engine

    with get_traffic_engine() as engine:
        rows = ingest_traffic(engine)
    logger.info(f"Traffic rows appended: {rows}")

def ingest_traffic_files(**kwargs):
    """Download weekly traffic Excel files from DDWeb → bronze.traffic"""
    from etl.ddweb_auth import DDWebAuth
    from etl.ddweb_ingest_ref import fetch_missions
    from etl.ddweb_ingest_traffic import complete_download

    auth = DDWebAuth()
    missions_df = fetch_missions(auth)

    # TEST MODE: only the first mission
    missions_df = missions_df.head(1)
    logger.info(f"TEST MODE: downloading only {len(missions_df)} mission(s)")
    
    complete_download(auth, missions_df)
    logger.info("Traffic files downloaded")

def run_bronze_layer(**kwargs):
    """Load missions, locations and traffic files into bronze tables"""
    from etl.bronze_data_layer import run_bronze
    result = run_bronze()
    logger.info(f"Bronze layer result: {result}")
    kwargs["ti"].xcom_push(key="new_mission_detected",
                           value=result["new_mission_detected"])

def run_silver_layer(**kwargs):
    """Clean and enrich bronze data into silver tables"""
    from etl.silver_data_layer import run_silver
    from utils.db import get_traffic_engine
    new_mission = kwargs["ti"].xcom_pull(
        key="new_mission_detected",
        task_ids="run_bronze_layer"
    )
    with get_traffic_engine() as engine:
        result = run_silver(bool(new_mission), engine)
    logger.info(f"Silver layer result: {result}")

def run_gold_layer(**kwargs):
    """Run gold aggregation using Monica's gold_data_layer.py"""
    from etl.gold_data_layer import run_gold
    from utils.db import get_traffic_engine
    with get_traffic_engine() as engine:
        result = run_gold(engine)
    logger.info(f"Gold layer result: {result}")

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

    t_missions = PythonOperator(
        task_id="fetch_and_load_missions",
        python_callable=fetch_and_load_missions,
    )

    t_branch = BranchPythonOperator(
        task_id="branch_on_new_mission",
        python_callable=branch_on_new_mission,
    )

    t_locations = PythonOperator(
        task_id="fetch_and_load_locations",
        python_callable=fetch_and_load_locations,
    )

    t_skip_locations = EmptyOperator(
        task_id="skip_locations",
    )

    t_ingest_traffic = PythonOperator(
        task_id="ingest_traffic_files",
        python_callable=load_bronze_traffic,
        trigger_rule="none_failed_min_one_success",
        execution_timeout=timedelta(hours=2),
    )

    t_bronze = PythonOperator(
        task_id="run_bronze_layer",
        python_callable=run_bronze_layer,
    )

    t_silver = PythonOperator(
        task_id="run_silver_layer",
        python_callable=run_silver_layer,
    )

    t_gold = PythonOperator(
        task_id="run_gold_layer",
        python_callable=run_gold_layer,
        trigger_rule="none_failed_min_one_success",
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
    t_ingest_traffic >> t_bronze >> t_silver >> t_gold >> t_superset
