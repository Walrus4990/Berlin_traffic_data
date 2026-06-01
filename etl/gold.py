import logging
from sqlalchemy import text
from datetime import datetime
from utils.db import get_traffic_engine, get_dq_engine

logger = logging.getLogger(__name__)
PAIRING_WINDOW_DAYS = 45  #sensor pairs are identified if less than 45 elapse between each of their set-up

def _get_or_create_watermark(conn, table_name: str, run_type: str, recovery_sql: str, dq_engine) -> datetime:
    """
    Gold layer uses timestamp as a watermark to upsert new rows. This function manges timestamps.
    It add last time gold layer was run adn checks before every run when that was.
    Returns the watermark timestamp for a table. On initial run inserts earliest date (1970) if missing.
    On weekly run, if missing recovers last run timestamp from table.
    """

    watermark = conn.execute(
        text("SELECT last_processed FROM gold.watermark WHERE table_name = :table"),
        {"table": table_name}
    ).scalar()

    if watermark is None:
        if run_type == "initial":
            conn.execute(
                text("INSERT INTO gold.watermark (table_name, last_processed) VALUES (:table, '1970-01-01')"),
                {"table": table_name}
            )
            conn.commit()
            return datetime(1970, 1, 1)
        else:
            recovered_ts = conn.execute(text(recovery_sql)).scalar()
            conn.execute(
                text("INSERT INTO gold.watermark (table_name, last_processed) VALUES (:table, :ts)"),
                {"table": table_name, "ts": recovered_ts}
            )
            conn.commit()
            logger.warning("gold.watermark empty on weekly run — recovered from %s. Investigate.", table_name)
            with dq_engine.connect() as dq_conn:
                dq_conn.execute(text("""
                    INSERT INTO gold.missing_watermark_alerts (run_at, message, recovered_timestamp)
                    VALUES (:run_at, :message, :recovered_ts)
                """), {
                    "run_at": datetime.now(),
                    "message": f"gold.watermark empty on weekly run — recovered from {table_name}",
                    "recovered_ts": recovered_ts
                })
                dq_conn.commit()
            return recovered_ts

    return watermark

def _update_pairs(run_type) -> int:
    """
    check if any missions created within past 45 days have aquired a pair since last data load.
    Only change is_pair=False to is_pair=True, not the other way round.
    """
    engine = get_traffic_engine()
    logger.info("=== PAIR UPDATE START ===")

    if run_type == "initial":
        sql="""
            UPDATE gold.export
            SET
                is_pair = r.is_pair,
                paired_mission_id = r.paired_mission_id,
                driving_direction = r.driving_direction,
                opposite_direction = r.opposite_direction
            FROM silver.ref_mission_location r
            WHERE
                gold.export.mission_id = r.mission_id AND
                (gold.export.is_pair = FALSE AND r.is_pair = TRUE)
            """
    else:
        sql="""
            UPDATE gold.export
            SET
                is_pair = r.is_pair,
                paired_mission_id = r.paired_mission_id,
                driving_direction = r.driving_direction,
                opposite_direction = r.opposite_direction
            FROM silver.ref_mission_location r
            WHERE
                gold.export.mission_id = r.mission_id AND
                (gold.export.is_pair = FALSE AND r.is_pair = TRUE) AND
                (r.created_at >= NOW() - INTERVAL '1 day' * :pairing_window)
            """

    with engine.connect() as conn:
        result = conn.execute(
            text(sql),
            {"pairing_window": PAIRING_WINDOW_DAYS}
        )
        conn.commit()
        ## i want to extract the numbe rof missions & mission Id...
        logger.info("PAIR UPDATE COMPLETE. %d rows in gold.export updated as pairs.", result.rowcount)
    return result.rowcount


def _modalsplit_view(engine) -> None:
    """Creates long-format view of gold.dashboard for modalsplit pie chart."""
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE OR REPLACE VIEW gold.v_modalsplit AS
            SELECT date, mission_id, streetnr, day_of_week, 'Auto' AS "Fahrzeugtyp", car AS value FROM gold.dashboard
            UNION ALL
            SELECT date, mission_id, streetnr, day_of_week, 'Fahrrad' AS "Fahrzeugtyp", bicycle AS value FROM gold.dashboard
            UNION ALL
            SELECT date, mission_id, streetnr, day_of_week, 'LKW' AS "Fahrzeugtyp", lorry AS value FROM gold.dashboard
            UNION ALL
            SELECT date, mission_id, streetnr, day_of_week, 'Motorrad' AS "Fahrzeugtyp", motorbike AS value FROM gold.dashboard
            UNION ALL
            SELECT date, mission_id, streetnr, day_of_week, 'Lieferwagen' AS "Fahrzeugtyp", delivery_van AS value FROM gold.dashboard
            UNION ALL
            SELECT date, mission_id, streetnr, day_of_week, 'Sonstige' AS "Fahrzeugtyp", other AS value FROM gold.dashboard
                    """))
        conn.commit()
        logger.info("View gold.v_modalsplit created.")

def _summary_table_view(engine) -> None:
    """Creates long-format view of gold.dashboard for summary table chart."""
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE OR REPLACE VIEW gold.v_summary_table AS
            SELECT * FROM (
            SELECT 1 AS sort_order, 'Auto' AS "Fahrzeugtyp", date, mission_id, streetnr, day_of_week, car AS daily_total, v_car AS avg_speed FROM gold.dashboard
            UNION ALL
            SELECT 2, 'Fahrrad', date, mission_id, streetnr, day_of_week, bicycle AS daily_total, NULL AS avg_speed FROM gold.dashboard
            UNION ALL
            SELECT 3, 'Lieferwagen', date, mission_id, streetnr, day_of_week, delivery_van AS daily_total, v_delivery_van AS avg_speed FROM gold.dashboard
            UNION ALL
            SELECT 4, 'LKW', date, mission_id, streetnr, day_of_week, lorry AS daily_total, v_lorry AS avg_speed FROM gold.dashboard
            UNION ALL
            SELECT 5, 'Motorrad', date, mission_id, streetnr, day_of_week, motorbike AS daily_total, v_motorbike AS avg_speed FROM gold.dashboard
            UNION ALL
            SELECT 6, 'Sonstige', date, mission_id, streetnr, day_of_week, other AS daily_total, NULL AS avg_speed FROM gold.dashboard
            ) sub
            ORDER BY sort_order
        """))
        conn.commit()
        logger.info("View gold.v_summary_table created.")

def _create_pairs_view(engine) -> None:
    """Creates view of paired sensor locations for Sensorpaare chart."""
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE OR REPLACE VIEW gold.v_pairs AS
            SELECT
                a.date,
                a.mission_id,
                a.streetnr AS "Standort",
                b.streetnr AS "Gegenüberliegender Standort"
            FROM gold.dashboard a
            JOIN gold.dashboard b ON a.paired_mission_id = b.mission_id
            WHERE a.is_pair = true
            GROUP BY a.date, a.streetnr, b.streetnr, a.mission_id
        """))
        conn.commit()
        logger.info("View gold.v_pairs created.")

def load_all_to_gold(run_type) -> tuple[int, datetime]:
    """
    Loads rows from silver.traffic and silver.ref_mission_location
    While loading aggregates rows and joins.
    Returns number of rows appended.
    """
    engine = get_traffic_engine()
    dq_engine = get_dq_engine()
    logger.info("=== GOLD LAYER START ===")
    logger.info("=== gold.export table update starting ===")

    #check watermark is there, if not add it and raise error if missing on weekly run
    with engine.connect() as conn:
        watermark = _get_or_create_watermark(
            conn,
            "gold.export",
            run_type,
            "SELECT MAX(gold_processed_at) FROM gold.export",
            dq_engine
        )

   # update pairs
    _update_pairs(run_type)

    # insert new rows & aggregate them
    with engine.connect() as conn:
        result =conn.execute(
            text(
            """
            WITH daily_v85 AS (
            SELECT
                mission_id,
                date_parsed::date AS date,
                PERCENTILE_CONT(0.85) WITHIN GROUP (ORDER BY speed)
                    FILTER (WHERE vehicle_class IN (2,3,5,7,8,9,10,11)) AS v85
            FROM silver.traffic
            WHERE silver_processed_at > :watermark
            GROUP BY mission_id, date_parsed::date
            )

            INSERT INTO gold.export (
                mission_id, device_id, start_date, end_date, date, hour, day_of_week_num, day_of_week_name, street, street_number, zipcode,
                city, location_description, lat, lon, motorised, car, bicycle, delivery_van, motorbike,
                lorry, other_motorised_vehicle, v_all_motorised, v_car, v_delivery_van, v_motorbike, v_lorry, v_other,
                v85, modal_share_car, modal_share_bicycle, modal_share_delivery_van, modal_share_motorbike,
                modal_share_lorry, is_pair, paired_mission_id, driving_direction, opposite_direction, gold_processed_at
            )
            SELECT
                t.mission_id,
                t.device_id,
                r.start_date,
                r.end_date,
                t.date_parsed::date   AS date,
                EXTRACT(HOUR FROM t.date_parsed) AS hour,
                EXTRACT(ISODOW FROM t.date_parsed)::SMALLINT AS day_of_week_num,
                CASE EXTRACT(ISODOW FROM t.date_parsed)::SMALLINT
                        WHEN 1 THEN 'Mo'
                        WHEN 2 THEN 'Di'
                        WHEN 3 THEN 'Mi'
                        WHEN 4 THEN 'Do'
                        WHEN 5 THEN 'Fr'
                        WHEN 6 THEN 'Sa'
                        WHEN 7 THEN 'So'
                    END AS day_of_week_name,
                r.street,
                r.street_number,
                r.zipcode,
                r.city,
                r.location_description,
                r.lat,
                r.lon,
                COUNT(*) FILTER (WHERE t.vehicle_class IN (2,3,5,7,8,9,10,11)) AS motorised,
                COUNT(*) FILTER (WHERE t.vehicle_class = 7)   AS car,
                COUNT(*) FILTER (WHERE t.vehicle_class = 230) AS bicycle,
                COUNT(*) FILTER (WHERE t.vehicle_class = 11)  AS delivery_van,
                COUNT(*) FILTER (WHERE t.vehicle_class = 10)  AS motorbike,
                COUNT(*) FILTER (WHERE t.vehicle_class = 3)   AS lorry,
                COUNT(*) FILTER (WHERE t.vehicle_class IN (2,5,8,9)) AS other_motorised_vehicle,
                AVG(t.speed) FILTER (WHERE t.vehicle_class IN (2,3,5,7,8,9,10,11)) AS v_all_motorised,
                AVG(t.speed) FILTER (WHERE t.vehicle_class = 7)   AS v_car,
                AVG(t.speed) FILTER (WHERE t.vehicle_class = 11)  AS v_delivery_van,
                AVG(t.speed) FILTER (WHERE t.vehicle_class = 10)  AS v_motorbike,
                AVG(t.speed) FILTER (WHERE t.vehicle_class = 3)   AS v_lorry,
                AVG(t.speed) FILTER (WHERE t.vehicle_class IN (2,5,8,9)) AS v_other,
                d.v85,
                COUNT(*) FILTER (WHERE t.vehicle_class = 7)/  COUNT(*)::numeric  AS modal_share_car,
                COUNT(*) FILTER (WHERE t.vehicle_class = 230)/COUNT(*)::numeric  AS modal_share_bicycle,
                COUNT(*) FILTER (WHERE t.vehicle_class = 11)/ COUNT(*)::numeric  AS modal_share_delivery_van,
                COUNT(*) FILTER (WHERE t.vehicle_class = 10)/ COUNT(*)::numeric  AS modal_share_motorbike,
                COUNT(*) FILTER (WHERE t.vehicle_class = 3)/  COUNT(*)::numeric  AS modal_share_lorry,
                r.is_pair,
                r.paired_mission_id,
                r.driving_direction,
                r.opposite_direction,
                NOW() as gold_processed_at
            FROM silver.traffic t
                JOIN silver.ref_mission_location r using (mission_id)
                JOIN daily_v85 d ON t.mission_id = d.mission_id AND t.date_parsed::date = d.date
            WHERE t.silver_processed_at > :watermark
            GROUP BY
                t.date_parsed::date,
                EXTRACT(HOUR FROM t.date_parsed),
                EXTRACT(ISODOW FROM t.date_parsed)::SMALLINT,
                CASE EXTRACT(ISODOW FROM t.date_parsed)::SMALLINT
                        WHEN 1 THEN 'Mo'
                        WHEN 2 THEN 'Di'
                        WHEN 3 THEN 'Mi'
                        WHEN 4 THEN 'Do'
                        WHEN 5 THEN 'Fr'
                        WHEN 6 THEN 'Sa'
                        WHEN 7 THEN 'So'
                    END,
                t.mission_id,
                t.device_id,
                r.start_date,
                r.end_date,
                r.street,
                r.street_number,
                r.zipcode,
                r.city,
                r.location_description,
                r.lat,
                r.lon,
                d.v85,
                r.is_pair,
                r.paired_mission_id,
                r.driving_direction,
                r.opposite_direction
            ON CONFLICT (mission_id, date, hour) DO UPDATE SET
                device_id                   = EXCLUDED.device_id,
                start_date                  = EXCLUDED.start_date,
                end_date                    = EXCLUDED.end_date,
                street                      = EXCLUDED.street,
                street_number               = EXCLUDED.street_number,
                zipcode                     = EXCLUDED.zipcode,
                city                        = EXCLUDED.city,
                location_description        = EXCLUDED.location_description,
                lat                         = EXCLUDED.lat,
                lon                         = EXCLUDED.lon,
                motorised                   = EXCLUDED.motorised,
                car                         = EXCLUDED.car,
                bicycle                     = EXCLUDED.bicycle,
                delivery_van                = EXCLUDED.delivery_van,
                motorbike                   = EXCLUDED.motorbike,
                lorry                       = EXCLUDED.lorry,
                other_motorised_vehicle     = EXCLUDED.other_motorised_vehicle,
                v_all_motorised             = EXCLUDED.v_all_motorised,
                v_car                       = EXCLUDED.v_car,
                v_delivery_van              = EXCLUDED.v_delivery_van,
                v_motorbike                 = EXCLUDED.v_motorbike,
                v_lorry                     = EXCLUDED.v_lorry,
                v_other                     = EXCLUDED.v_other,
                v85                         = EXCLUDED.v85,
                modal_share_car             = EXCLUDED.modal_share_car,
                modal_share_bicycle         = EXCLUDED.modal_share_bicycle,
                modal_share_delivery_van    = EXCLUDED.modal_share_delivery_van,
                modal_share_motorbike       = EXCLUDED.modal_share_motorbike,
                modal_share_lorry           = EXCLUDED.modal_share_lorry,
                is_pair                     = EXCLUDED.is_pair,
                paired_mission_id           = EXCLUDED.paired_mission_id,
                driving_direction           = EXCLUDED.driving_direction,
                opposite_direction          = EXCLUDED.opposite_direction,
                gold_processed_at           = NOW()
            """),
            {"watermark": watermark})
        conn.commit()
        logger.info(" gold.export updaet complete - %d new rows appended.", result.rowcount)


    with engine.connect() as conn:
        conn.execute(
            text(
            """
            UPDATE gold.watermark SET last_processed = NOW() WHERE table_name = 'gold.export'
            """)
        )
        conn.commit()
        today=datetime.now()
        logger.info("gold.watermarktable export watermark updated with date %s ", today)

    return result.rowcount, today


def load_dashboard(run_type) -> tuple[int, datetime]:
    """
    Loads rows from gold.export aggregates by day. One row = one day.
    Returns number of rows appended.
    """
    engine = get_traffic_engine()
    dq_engine = get_dq_engine()
    logger.info("=== gold.dashboard update start ===")

    #check watermark is there, if not add it and raise error if missing on weekly run
    with engine.connect() as conn:
        watermark = _get_or_create_watermark(
            conn,
            "gold.dashboard",
            run_type,
            "SELECT MAX(dashboard_processed_at) FROM gold.dashboard",
            dq_engine
        )

    # insert new rows & aggregate them
    with engine.connect() as conn:
        result =conn.execute(
            text(
            """
            INSERT INTO gold.dashboard (
                mission_id, start_date, end_date, date,  day_of_week, streetnr, city,
                location_description, lat, lon, car, bicycle, delivery_van, motorbike, lorry, other, v_car,
                v_delivery_van, v_motorbike, v_lorry, v85, is_pair, paired_mission_id, dashboard_processed_at
            )
            SELECT
                mission_id,
                start_date,
                end_date,
                date,
                day_of_week_num || '. ' || day_of_week_name AS day_of_week,
                CONCAT(street, ' ', street_number) AS streetnr,
                city,
                location_description,
                lat,
                lon,
                SUM(car)                    AS car,
                SUM(bicycle)                AS bicycle,
                SUM(delivery_van)           AS delivery_van,
                SUM(motorbike)              AS motorbike,
                SUM(lorry)                  AS lorry,
                SUM(other_motorised_vehicle) AS other,
                SUM(v_car * car) / NULLIF(SUM(car), 0)                             AS v_car,
                SUM(v_delivery_van * delivery_van) / NULLIF(SUM(delivery_van), 0)  AS v_delivery_van,
                SUM(v_motorbike * motorbike) / NULLIF(SUM(motorbike), 0)           AS v_motorbike,
                SUM(v_lorry * lorry)  / NULLIF(SUM(lorry), 0)                      AS v_lorry,
                v85,
                is_pair,
                paired_mission_id,
                NOW() AS dashboard_processed_at
            FROM gold.export
            WHERE gold_processed_at > :watermark
            GROUP BY
                date,
                day_of_week_num,
                day_of_week_name,
                mission_id,
                start_date,
                end_date,
                street,
                street_number,
                city,
                location_description,
                lat,
                lon,
                v85,
                is_pair,
                paired_mission_id
            ON CONFLICT (mission_id, date) DO UPDATE SET
                start_date                  = EXCLUDED.start_date,
                end_date                    = EXCLUDED.end_date,
                streetnr                    = EXCLUDED.streetnr,
                city                        = EXCLUDED.city,
                location_description        = EXCLUDED.location_description,
                lat                         = EXCLUDED.lat,
                lon                         = EXCLUDED.lon,
                car                         = EXCLUDED.car,
                bicycle                     = EXCLUDED.bicycle,
                delivery_van                = EXCLUDED.delivery_van,
                motorbike                   = EXCLUDED.motorbike,
                lorry                       = EXCLUDED.lorry,
                other                       = EXCLUDED.other,
                v_car                       = EXCLUDED.v_car,
                v_delivery_van              = EXCLUDED.v_delivery_van,
                v_motorbike                 = EXCLUDED.v_motorbike,
                v_lorry                     = EXCLUDED.v_lorry,
                v85                         = EXCLUDED.v85,
                is_pair                     = EXCLUDED.is_pair,
                paired_mission_id           = EXCLUDED.paired_mission_id,
                dashboard_processed_at      = NOW()
            """),
            {"watermark": watermark})
        conn.commit()
        logger.info("Dashboard table build complete - %d new rows appended to gold.dashboard.", result.rowcount)

    with engine.connect() as conn:
        conn.execute(
            text(
            """
            UPDATE gold.watermark SET last_processed = NOW() WHERE table_name = 'gold.dashboard'
            """)
        )
        conn.commit()
        today=datetime.now()
        logger.info("gold.watermarktable dashboard watermark updated with date %s ", today)

        _modalsplit_view(engine)
        _summary_table_view(engine)
        _create_pairs_view(engine)

    return result.rowcount, today


def load_ganglinien(run_type) -> tuple[int, datetime]:
    """
    Loads rows from gold.export aggregated by hour. One row per (mission_id, date, hour).
    Returns number of rows appended.
    """
    engine = get_traffic_engine()
    dq_engine = get_dq_engine()
    logger.info("=== gold.ganglinien update start ===")

    with engine.connect() as conn:
        watermark = _get_or_create_watermark(
            conn,
            "gold.ganglinien",
            run_type,
            "SELECT MAX(ganglinien_processed_at) FROM gold.ganglinien",
            dq_engine
        )

    with engine.connect() as conn:
        result = conn.execute(
            text("""
            INSERT INTO gold.ganglinien (
                mission_id, date, hour, day_of_week,
                streetnr, car, bicycle, delivery_van, motorbike, lorry,
                ganglinien_processed_at
            )
            SELECT
                mission_id,
                date,
                LPAD(hour::TEXT, 2, '0') AS hour,
                day_of_week_num || '. ' || day_of_week_name AS day_of_week,
                CONCAT(street, ' ', street_number) AS streetnr,
                car,
                bicycle,
                delivery_van,
                motorbike,
                lorry,
                NOW() AS ganglinien_processed_at
            FROM gold.export
            WHERE gold_processed_at > :watermark
            ON CONFLICT (mission_id, date, hour) DO UPDATE SET
                day_of_week             = EXCLUDED.day_of_week,
                streetnr                = EXCLUDED.streetnr,
                car                     = EXCLUDED.car,
                bicycle                 = EXCLUDED.bicycle,
                delivery_van            = EXCLUDED.delivery_van,
                motorbike               = EXCLUDED.motorbike,
                lorry                   = EXCLUDED.lorry,
                ganglinien_processed_at = NOW()
            """),
            {"watermark": watermark}
        )
        conn.commit()
        logger.info("gold.ganglinien update complete - %d new rows appended.", result.rowcount)

    with engine.connect() as conn:
        conn.execute(
            text("UPDATE gold.watermark SET last_processed = NOW() WHERE table_name = 'gold.ganglinien'")
        )
        conn.commit()
        today = datetime.now()
        logger.info("gold.watermark ganglinien watermark updated with date %s", today)

    logger.info("======== GOLD LAYER COMPLETE ========")
    return result.rowcount, today
