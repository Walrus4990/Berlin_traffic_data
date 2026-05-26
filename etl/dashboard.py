import logging
from sqlalchemy import text
from datetime import datetime
from utils.db import get_traffic_engine, get_dq_engine, save

logger = logging.getLogger(__name__)

def load_dashboard(run_type) -> tuple[int, datetime]:
    """
    Loads rows from gold.export aggregates by day. One row = one day.
    Returns number of rows appended.
    """
    engine = get_traffic_engine()
    dq_engine = get_dq_engine
    logger.info("=== Dashboard build start ===")

    #check watermark is there, if not add it and raise error if missing on weekly run
    with engine.connect() as conn:
        watermark = conn.execute(text("SELECT last_processed FROM gold.watermark WHERE table_name = 'gold.dashboard'")).scalar()

        if watermark is None:  # table is empty
            if run_type == "initial":
                conn.execute(text("INSERT INTO gold.watermark (table_name, last_processed) VALUES ('gold.dashboard', '1970-01-01')"))
                conn.commit()
                watermark = datetime(1970, 1, 1)
            else:
                recovered_ts = conn.execute(text("SELECT MAX(dashboard_processed_at) FROM gold.dashboard")).scalar() #recovers timestamp
                conn.execute(text("INSERT INTO gold.watermark (table_name, last_processed) VALUES ('gold.dashboard', :ts)"), {"ts": recovered_ts})
                conn.commit()
                watermark = recovered_ts
                logger.warning("gold.watermark was empty on weekly run — recovered from gold.dashboard. Investigate.")
                #save error to DQ database
                with dq_engine.connect() as dq_conn:
                    dq_conn.execute(text("""
                        INSERT INTO gold.missing_watermark_alerts (run_at, message, recovered_timestamp)
                        VALUES (:run_at, :message, :recovered_ts)
                    """), {
                        "run_at": datetime.now(),
                        "message": "gold.watermark empty on weekly run — recovered from gold.dashboard",
                        "recovered_ts": recovered_ts
                    })
                    dq_conn.commit()

    # insert new rows & aggregate them
    with engine.connect() as conn:
        result =conn.execute(
            text(
            """
            INSERT INTO gold.dashboard (
                mission_id, start_date, end_date, date, streetnr, city, location_description, lat, lon, car,
                bicycle, delivery_van, motorbike, lorry, other, v_car, v_delivery_van, v_motorbike,
                v_lorry, v_other, v85, modal_share_car, modal_share_bicycle, modal_share_delivery_van, modal_share_motorbike,
                modal_share_lorry, modal_share_other, is_pair, paired_mission_id
            )
            SELECT
                mission_id,
                start_date,
                end_date,
                date,
                street || ' ' || street_number AS streetnr,
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
                SUM(v_other * other_motorised_vehicle) / NULLIF(SUM(other_motorised_vehicle), 0) AS v_other,
                SUM(v85 * motorised)  / NULLIF(SUM(motorised), 0)                  AS v85,
                SUM(car)::numeric        / NULLIF(SUM(motorised + bicycle), 0)     AS modal_share_car,
                SUM(bicycle)::numeric    / NULLIF(SUM(motorised + bicycle), 0)     AS modal_share_bicycle,
                SUM(delivery_van)::numeric / NULLIF(SUM(motorised + bicycle), 0)   AS modal_share_delivery_van,
                SUM(motorbike)::numeric  / NULLIF(SUM(motorised + bicycle), 0)     AS modal_share_motorbike,
                SUM(lorry)::numeric      / NULLIF(SUM(motorised + bicycle), 0)     AS modal_share_lorry,
                SUM(other_motorised_vehicle)::numeric / NULLIF(SUM(motorised + bicycle), 0) AS modal_share_other,
                is_pair,
                paired_mission_id
            FROM gold.export
            WHERE gold_processed_at > :watermark
            GROUP BY
                date,
                mission_id,
                start_date,
                end_date,
                street,
                street_number,
                city,
                location_description,
                lat,
                lon,
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
                v_other                     = EXCLUDED.v_other,
                v85                         = EXCLUDED.v85,
                modal_share_car             = EXCLUDED.modal_share_car,
                modal_share_bicycle         = EXCLUDED.modal_share_bicycle,
                modal_share_delivery_van    = EXCLUDED.modal_share_delivery_van,
                modal_share_motorbike       = EXCLUDED.modal_share_motorbike,
                modal_share_lorry           = EXCLUDED.modal_share_lorry,
                modal_share_other           = EXCLUDED.modal_share_other,
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

    return result.rowcount, today
