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
        sys.path.insert(0, os.path.dirname(dag_dir))
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
        sys.path.insert(0, os.path.dirname(dag_dir))
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
        sys.path.insert(0, os.path.dirname(dag_dir))
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
        sys.path.insert(0, os.path.dirname(dag_dir))
        from tests.test_ingest import check_bronze_completeness
        logger = logging.getLogger(__name__)
        result = check_bronze_completeness("initial")
        logger.info("Validation result: %s", result)

    @task.virtualenv(requirements=REQUIREMENTS,
                     #execution_timeout=timedelta(minutes=15)  #commented out to fail fast uncomment in prod
    )
    def run_build_mission_location_to_silver(dag_dir: str) -> None:
        """Merge missions and locations from bronze.mission, bronze.location into silver_ref_mission_location
        Identifies sensor"""
        import logging
        import sys
        sys.path.insert(0, os.path.dirname(dag_dir))
        from etl.silver_ref import build_mission_location_to_silver
        logger = logging.getLogger(__name__)
        rows = build_mission_location_to_silver("initial")
        logger.info("%d new rows rows appended to silver_ref_mission_location", rows)

    @task.virtualenv(requirements=REQUIREMENTS,
                     #execution_timeout=timedelta(hours=3)  #commented out to fail fast uncomment in prod
    )
    def run_load_traffic_to_silver(dag_dir: str) -> None:
        """Clean and enrich bronze data into silver tables"""
        import logging
        import sys
        sys.path.insert(0, os.path.dirname(dag_dir))
        from etl.silver import load_traffic_to_silver
        logger = logging.getLogger(__name__)
        rows = load_traffic_to_silver()
        logger.info("Traffic rows written to silver: %d", rows)

    @task.virtualenv(requirements=REQUIREMENTS,
                     #execution_timeout=timedelta(hours=3)  #commented out to fail fast uncomment in prod
    )
    def run_validate_silver(dag_dir: str) -> None:
        """Merges """
        import logging
        import sys
        sys.path.insert(0, os.path.dirname(dag_dir))
        from tests.test_silver import check_silver_dq
        logger = logging.getLogger(__name__)
        result = check_silver_dq()
        logger.info("Validation result: %s", result)

    @task.virtualenv(requirements=REQUIREMENTS,
                     #execution_timeout=timedelta(hours=3)  #commented out to fail fast uncomment in prod
    )
    def run_load_all_to_gold(dag_dir: str) -> None:
        """Aggregates silver.traffic into hourly data with vehcle count and speeds.
        Merges traffic data to silver.ref_mission_location. Updates sensor pairs."""
        import logging
        import sys
        sys.path.insert(0, os.path.dirname(dag_dir))
        from etl.gold import load_all_to_gold
        logger = logging.getLogger(__name__)
        rows_inserted, load_date = load_all_to_gold("initial")
        logger.info("%d new rows appended to gold.export and export watermark updated with date %s", rows_inserted, load_date)

    @task.virtualenv(requirements=REQUIREMENTS,
                     #execution_timeout=timedelta(hours=3)  #commented out to fail fast uncomment in prod
    )
    def run_load_dashboard(dag_dir: str) -> None:
        """Aggregates gold.export into daily data. Updates SQL queries for dashboard"""
        import logging
        import sys
        sys.path.insert(0, os.path.dirname(dag_dir))
        from etl.gold import load_dashboard
        logger = logging.getLogger(__name__)
        rows_inserted, load_date = load_dashboard("initial")
        logger.info("%d new rows appended to gold.dashboard and dashboard watermark updated with date %s", rows_inserted, load_date)

    @task.virtualenv(requirements=REQUIREMENTS,
                     #execution_timeout=timedelta(hours=3)  #commented out to fail fast uncomment in prod
    )
    def run_load_ganglinien(dag_dir: str) -> None:
        """Loads tabe for Ganglinien chart"""
        import logging
        import sys
        sys.path.insert(0, os.path.dirname(dag_dir))
        from etl.gold import load_ganglinien
        logger = logging.getLogger(__name__)
        rows_inserted, load_date = load_ganglinien("initial")
        logger.info("%d new rows appended to gold.ganglinien and ganglinien watermark updated with date %s", rows_inserted, load_date)

    @task.virtualenv(requirements=REQUIREMENTS,
                     #execution_timeout=timedelta(hours=3)  #commented out to fail fast uncomment in prod
    )
    def run_import_dashboard(dag_dir: str) -> None:
        """imports the .zip file to set up teh dashboard and connect to gold.dashpboard and gold.ganglinien"""
        import logging
        import sys
        sys.path.insert(0, os.path.dirname(dag_dir))
        from etl.dashboard import import_dashboard
        logger = logging.getLogger(__name__)
        logger.info("Starting dashboard import")
        import_dashboard()
        logger.info("Dashboard import task complete")

    # ── Dependencies ──────────────────────────────────────────────────────────
    complete_traffic_download = run_complete_download(dag_dir=DAG_DIR)
    bronze_ref = run_load_ref_to_bronze(dag_dir=DAG_DIR)
    bronze_traffic = run_load_traffic_to_bronze(dag_dir=DAG_DIR)
    bronze_validate = run_validate_bronze(dag_dir=DAG_DIR)
    silver_ref = run_build_mission_location_to_silver(dag_dir=DAG_DIR)
    silver_traffic = run_load_traffic_to_silver(dag_dir=DAG_DIR)
    silver_validate = run_validate_silver(dag_dir=DAG_DIR)
    gold_export = run_load_all_to_gold(dag_dir=DAG_DIR)
    gold_dashboard = run_load_dashboard(dag_dir=DAG_DIR)
    gold_ganglinien = run_load_ganglinien(dag_dir=DAG_DIR)
    dashboard_setup = run_import_dashboard(dag_dir=DAG_DIR)


    [bronze_ref, complete_traffic_download] >> bronze_traffic >> bronze_validate
    bronze_traffic >> silver_traffic
    silver_traffic >> silver_validate
    bronze_ref>>silver_ref
    [silver_ref, silver_traffic] >> gold_export >> gold_dashboard
    gold_export >> gold_ganglinien
    [gold_dashboard, gold_ganglinien] >> dashboard_setup

ts_traffic_initial_load()
