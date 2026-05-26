import logging
from sqlalchemy import text
from datetime import datetime
from utils.db import get_traffic_engine, get_dq_engine, save

logger = logging.getLogger(__name__)
PAIRING_WINDOW_DAYS = 45  #sensor pairs are identified if less than 45 elapse between each of their set-up

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


def load_all_to_gold(run_type) -> tuple[int, datetime]:
    """
    Loads rows from silver.traffic and silver.ref_mission_location
    While loading aggregates rows and joins.
    Returns number of rows appended.
    """
    engine = get_traffic_engine()
    dq_engine = get_dq_engine
    logger.info("=== GOLD LAYER START ===")

    #check watermark is there, if not add it and raise error if missing on weekly run
    with engine.connect() as conn:
        watermark = conn.execute(text("SELECT last_processed FROM gold.watermark WHERE table_name = 'gold.export'")).scalar()

        if watermark is None:  # table is empty
            if run_type == "initial":
                conn.execute(text("INSERT INTO gold.watermark (table_name, last_processed) VALUES ('gold.export', '1970-01-01')"))
                conn.commit()
                watermark = datetime(1970, 1, 1)
            else:
                recovered_ts = conn.execute(text("SELECT MAX(gold_processed_at) FROM gold.export")).scalar() #recovers timestamp from gold.traffic
                conn.execute(text("INSERT INTO gold.watermark (table_name, last_processed) VALUES ('gold.export', :ts)"), {"ts": recovered_ts})
                conn.commit()
                watermark = recovered_ts
                logger.warning("gold.watermark was empty on weekly run — recovered from gold.export. Investigate.")
                #save error to DQ database
                with dq_engine.connect() as dq_conn:
                    dq_conn.execute(text("""
                        INSERT INTO gold.missing_watermark_alerts (run_at, message, recovered_timestamp)
                        VALUES (:run_at, :message, :recovered_ts)
                    """), {
                        "run_at": datetime.now(),
                        "message": "gold.watermark empty on weekly run — recovered from gold.export",
                        "recovered_ts": recovered_ts
                    })
                    dq_conn.commit()

   # update pairs
    _update_pairs(run_type)

    # insert new rows & aggregate them
    with engine.connect() as conn:
        result =conn.execute(
            text(
            """
            INSERT INTO gold.export (
                mission_id, device_id, start_date, end_date, date, hour, street, street_number, zipcode,
                city, location_description, lat, lon, motorised, car, bicycle, delivery_van, motorbike,
                lorry, other_motorised_vehicle, v_all_motorised, v_car, v_delivery_van, v_motorbike, v_lorry, v_other,
                v85, modal_share_car, modal_share_bicycle, modal_share_delivery_van, modal_share_motorbike,
                modal_share_lorry, is_pair, paired_mission_id, driving_direction, opposite_direction
            )
            SELECT
                t.mission_id,
                t.device_id,
                r.start_date,
                r.end_date,
                t.date_parsed::date                        AS date,
                EXTRACT(HOUR FROM t.date_parsed)::SMALLINT AS hour,
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
                PERCENTILE_CONT(0.85) WITHIN GROUP (ORDER BY t.speed) FILTER (WHERE t.vehicle_class IN (2,3,5,7,8,9,10,11)) AS v85,
                COUNT(*) FILTER (WHERE t.vehicle_class = 7)/  COUNT(*)::numeric  AS modal_share_car,
                COUNT(*) FILTER (WHERE t.vehicle_class = 230)/COUNT(*)::numeric  AS modal_share_bicycle,
                COUNT(*) FILTER (WHERE t.vehicle_class = 11)/ COUNT(*)::numeric  AS modal_share_delivery_van,
                COUNT(*) FILTER (WHERE t.vehicle_class = 10)/ COUNT(*)::numeric  AS modal_share_motorbike,
                COUNT(*) FILTER (WHERE t.vehicle_class = 3)/  COUNT(*)::numeric  AS modal_share_lorry,
                r.is_pair,
                r.paired_mission_id,
                r.driving_direction,
                r.opposite_direction
            FROM silver.traffic t JOIN silver.ref_mission_location r using (mission_id)
            WHERE t.silver_processed_at > :watermark
            GROUP BY
                t.date_parsed::date,
                EXTRACT(HOUR FROM t.date_parsed)::SMALLINT,
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
        logger.info("GOLD LAYER COMPLETE - %d new rows appended to gold.export.", result.rowcount)


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
