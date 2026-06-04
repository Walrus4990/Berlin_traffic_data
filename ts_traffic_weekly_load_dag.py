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
                     #execution_timeout=timedelta(minutes=15)  #commented out to fail fast uncomment in prod
    )
    def run_build_mission_location_to_silver(dag_dir: str) -> None:
        """Merge missions and locations from bronze.mission, bronze.location into silver_ref_mission_location
        Identifies sensor"""
        import logging
        import sys
        sys.path.insert(0, dag_dir)
        from etl.silver_ref import build_mission_location_to_silver
        logger = logging.getLogger(__name__)
        rows = build_mission_location_to_silver("weekly")
        logger.info("%d new rows rows appended to silver_ref_mission_location", rows)


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
    def run_load_all_to_gold(dag_dir: str) -> None:
        """Aggregates silver.traffic into hourly data with vehcle count and speeds.
        Merges traffic data to silver.ref_mission_location. Updates sensor pairs."""
        import logging
        import sys
        sys.path.insert(0, dag_dir)
        from etl.gold import load_all_to_gold
        logger = logging.getLogger(__name__)
        rows_inserted, load_date = load_all_to_gold("weekly")
        logger.info("%d new rows appended to gold.export and export watermark updated with date %s", rows_inserted, load_date)


    @task.virtualenv(requirements=REQUIREMENTS,
                     #execution_timeout=timedelta(hours=3)  #commented out to fail fast uncomment in prod
    )
    def run_load_dashboard(dag_dir: str) -> None:
        """Aggregates gold.export into daily data. Updates SQL queries for dashboard"""
        import logging
        import sys
        sys.path.insert(0, dag_dir)
        from etl.gold import load_dashboard
        logger = logging.getLogger(__name__)
        rows_inserted, load_date = load_dashboard("weekly")
        logger.info("%d new rows appended to gold.dashboard and dashboard watermark updated with date %s", rows_inserted, load_date)

    @task.virtualenv(requirements=REQUIREMENTS,
                     #execution_timeout=timedelta(hours=3)  #commented out to fail fast uncomment in prod
    )
    def run_load_ganglinien(dag_dir: str) -> None:
        """Loads tabe for Ganglinien chart"""
        import logging
        import sys
        sys.path.insert(0, dag_dir)
        from etl.gold import load_ganglinien
        logger = logging.getLogger(__name__)
        rows_inserted, load_date = load_ganglinien("weekly")
        logger.info("%d new rows appended to gold.ganglinien and ganglinien watermark updated with date %s", rows_inserted, load_date)

    @task.virtualenv(requirements=REQUIREMENTS,
                     #execution_timeout=timedelta(hours=3)  #commented out to fail fast uncomment in prod
    )
    def run_publish_csv(dag_dir: str) -> None:
        """Export gold.export as dated CSV to MinIO"""
        import logging, sys
        sys.path.insert(0, dag_dir)
        from etl.publish import publish_csv
        logger = logging.getLogger(__name__)
        filename = publish_csv()
        logger.info("MinIO export complete: %s", filename)


    # ── Dependencies ──────────────────────────────────────────────────────────
    bronze_ref = run_load_ref_to_bronze(dag_dir=DAG_DIR)
    ingest = run_ingest_traffic(dag_dir=DAG_DIR)
    bronze_traffic = run_load_traffic_to_bronze(dag_dir=DAG_DIR)
    bronze_validate = run_validate_bronze(dag_dir=DAG_DIR)
    silver_ref = run_build_mission_location_to_silver(dag_dir=DAG_DIR)
    silver_traffic = run_load_traffic_to_silver(dag_dir=DAG_DIR)
    silver_validate = run_validate_silver(dag_dir=DAG_DIR)
    gold_export = run_load_all_to_gold(dag_dir=DAG_DIR)
    gold_dashboard = run_load_dashboard(dag_dir=DAG_DIR)
    gold_ganglinien = run_load_ganglinien(dag_dir=DAG_DIR)
    publish = run_publish_csv(dag_dir=DAG_DIR)


    [bronze_ref, ingest] >> bronze_traffic >> bronze_validate
    bronze_traffic >> silver_traffic
    silver_traffic >> silver_validate
    bronze_ref>>silver_ref
    [silver_ref, silver_traffic] >> gold_export >> gold_dashboard
    gold_export >> gold_ganglinien
    gold_export >> publish

ts_traffic_weekly_load()
