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
    from etl.bronze_data_layer import fetch_and_ingest_missions
    from utils.db import get_traffic_engine

    auth = DDWebAuth()
    auth.ensure_authenticated()

    with get_traffic_engine() as engine:
        new_mission_detected, rows_added = fetch_and_ingest_missions(auth, engine)

    #store a short value in Airflow: True = a new mission ID was found, run the full update path. False = no change, run the reduced path
    kwargs["ti"].xcom_push(key="new_mission_detected", value=new_mission_detected)
    logger.info(f"new_mission_detected={new_mission_detected}, rows_added={rows_added}")


t_missions = PythonOperator(
    task_id="fetch_and_load_missions",
    python_callable=fetch_and_load_missions,
)

# ------ If logic in case new mission go to location otherwise skip
def branch_on_new_mission(**kwargs):
    new_mission = kwargs["ti"].xcom_pull(   #pulls the short True/False value from previsous function
        task_ids="fetch_and_load_missions",
        key="new_mission_detected"
    )
    if new_mission:
        return "fetch_and_load_locations"
    return "skip_locations"

t_branch = BranchPythonOperator(
    task_id="branch_on_new_mission",
    python_callable=branch_on_new_mission,
)

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

t_locations = PythonOperator(
    task_id="fetch_and_load_locations",
    python_callable=fetch_and_load_locations,
)

t_skip_locations = EmptyOperator(
    task_id="skip_locations",
)

def load_bronze_traffic(**kwargs):
    from etl.bronze_data_layer import ingest_traffic
    from utils.db import get_traffic_engine

    with get_traffic_engine() as engine:
        rows = ingest_traffic(engine)
    logger.info(f"Traffic rows appended: {rows}")

t_ingest_traffic = PythonOperator(
    task_id="ingest_traffic_files",
    python_callable=load_bronze_traffic,
    trigger_rule="none_failed_min_one_success",
)






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
    t_missions >> t_branch
    t_branch >> [t_locations, t_skip_locations]
    [t_locations, t_skip_locations] >> t_ingest_traffic
    t_ingest_traffic >> [t_gold_location, t_gold_vehicle, t_gold_time]
    [t_gold_location, t_gold_vehicle, t_gold_time] >> t_superset
