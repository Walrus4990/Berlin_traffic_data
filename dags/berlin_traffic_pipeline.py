
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


# ------ If logic in case new mission go to location otherwise skip
def branch_on_new_mission(**kwargs):
    new_mission = kwargs["ti"].xcom_pull(   #pulls the short True/False value from previsous function
        task_ids="fetch_and_load_missions",
        key="new_mission_detected"
    )
    return "fetch_and_load_locations" if new_mission else "skip_locations"


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
    import os, requests
    from utils.db import get_traffic_engine

    base = "http://superset:8088"
    session = requests.Session()

    # --- login ---
    r = session.post(f"{base}/api/v1/security/login", json={
        "username": os.getenv("SUPERSET_ADMIN_USER", "admin"),  #remove hardcoding in prod
        "password": os.getenv("SUPERSET_ADMIN_PASSWORD", "admin"),
        "provider": "db"
    })
    r.raise_for_status()
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    csrf = session.get(f"{base}/api/v1/security/csrf_token/", headers=headers)
    csrf_token = csrf.json()["result"]
    headers["X-CSRFToken"] = csrf_token
    headers["Referer"] = base

   # ---------------- DB connection ----------------
    with get_traffic_engine() as engine:
        sqlalchemy_uri = str(engine.url)

    dbs = session.get(f"{base}/api/v1/database/", headers=headers).json()

    db = next(
        (d for d in dbs.get("result", []) if d.get("database_name") == "traffic_db"),
        None
    )

    if not db:
        resp = session.post(f"{base}/api/v1/database/", json={
            "database_name": "traffic_db", #why the name, check on final tidy - it's teh superset db connection'
            "sqlalchemy_uri": sqlalchemy_uri
        }, headers=headers)
        db = resp.json()
        
    db_id = db["id"]

    # ---------------- dataset: gold.traffic ----------------
    datasets = session.get(f"{base}/api/v1/dataset/", headers=headers).json()

    exists = any(
        d.get("schema") == "gold" and d.get("table_name") == "traffic"
        for d in datasets.get("result", [])
    )

    if not exists:
        session.post(f"{base}/api/v1/dataset/", json={
            "database": db_id,
            "schema": "gold",
            "table_name": "traffic"
        }, headers=headers)

    # ---------------- dashboard import ----------------
    try:
        with open("/app/superset_home/exports/dashboard_export_20260419T194107.zip", "rb") as f:
            session.post(
                f"{base}/api/v1/dashboard/import/",
                headers=headers,
                files={"formData": f},
                data={"overwrite": "true", "passwords": '{"databases/traffic_db.yaml": "traffic"}'}
            )
    except FileNotFoundError:
        logger.warning("Dashboard zip not found, skipping import")


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
        execution_timeout=timedelta(hours=2), 
    )

    t_silver = PythonOperator(
        task_id="run_silver_layer",
        python_callable=run_silver_layer,
        execution_timeout=timedelta(hours=1), 
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
    t_missions >> t_branch
    t_branch >> [t_locations, t_skip_locations]
    [t_locations, t_skip_locations] >> t_ingest_traffic
    t_ingest_traffic >> t_bronze >> t_silver >> t_gold >> t_superset
