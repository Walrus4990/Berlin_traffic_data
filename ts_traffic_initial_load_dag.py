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
    dag_id="ts_traffic_initial_load",
    schedule=None,
    start_date=pendulum.datetime(2026, 5, 13, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    tags=["ts", "traffic", "initial"],
    default_args={
        "owner": "ts",
        "retries": 0,
    }
)
def ts_traffic_initial_load():
    """
    ### Tempelhof Schöneberg initial traffic data ingest
    One-off orchestration: ingest → hand over to weekly DAG
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
                     #execution_timeout=timedelta(hours=24)  #commented out to fail fast uncomment in prod
    )
    def run_complete_download(dag_dir: str) -> None:
        """Complete download of historical traffic data → parquet files to MinIO"""
        import logging
        import pytz
        from datetime import datetime
        import sys
        sys.path.insert(0, dag_dir)
        from etl.ddweb_ingest_traffic import complete_download
        logger = logging.getLogger(__name__)
        logger.info("Initial download started at %s", datetime.now(tz=pytz.timezone("Europe/Berlin")))
        complete_download()
        logger.info("Initial download finished at %s", datetime.now(tz=pytz.timezone("Europe/Berlin")))

    @task.virtualenv(requirements=REQUIREMENTS,
                     #execution_timeout=timedelta(hours=5)  #commented out to fail fast uncomment in prod
    )
    def run_load_traffic_to_bronze(dag_dir: str) -> None:
        """Read new parquet files from MinIO → append to bronze.traffic"""
        import logging
        import sys
        sys.path.insert(0, dag_dir)
        from etl.bronze import load_traffic_to_bronze
        logger = logging.getLogger(__name__)
        rows = load_traffic_to_bronze()
        logger.info("Loaded %d rows to bronze", rows)

    @task.virtualenv(requirements=REQUIREMENTS,
                     #execution_timeout=timedelta(XXX)  #set value in prod
    )
    def run_validate_bronze(dag_dir: str) -> None:
        """Checks download, saves missing file info & error messages  → append to bronze.dq"""
        import logging
        import sys
        sys.path.insert(0, dag_dir)
        from tests.test_ingest import check_bronze_completeness
        logger = logging.getLogger(__name__)
        result = check_bronze_completeness("initial")
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



    # ── Dependencies ──────────────────────────────────────────────────────────
    bronze_ref = run_load_ref_to_bronze(dag_dir=DAG_DIR)
    complete_traffic_download = run_complete_download(dag_dir=DAG_DIR)
    bronze_traffic = run_load_traffic_to_bronze(dag_dir=DAG_DIR)
    bronze_validate = run_validate_bronze(dag_dir=DAG_DIR)
    silver_traffic = run_load_traffic_to_silver(dag_dir=DAG_DIR)
    silver_validate = run_validate_silver(dag_dir=DAG_DIR)


    [bronze_ref, complete_traffic_download] >> bronze_traffic >> bronze_validate
    bronze_traffic >> silver_traffic
    silver_traffic >> silver_validate



ts_traffic_initial_load()
