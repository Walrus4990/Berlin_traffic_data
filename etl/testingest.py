from datetime import date

import etl.ddweb_auth as auth
from etl.ddweb_ingest import fetch_missions
import etl.ddweb_ingest_traffic as traffic


# --- Authenticate ---
client = auth.DDWebAuth()
client.ensure_authenticated()

# --- Fetch missions ---
missions_df = fetch_missions(client)
print(missions_df[["Id", "FromDate", "ToDate"]].head())


# =========================
# TEST CASE 1
# =========================
mission_id = 40671

row = missions_df[missions_df["Id"] == mission_id].iloc[0]
from_date = traffic._parse_date(row["FromDate"])
to_date = traffic._parse_date(row["ToDate"])
print(from_date, to_date)

test_chunks=traffic._get_month_chunks(from_date, to_date)
print(test_chunks)

payload = traffic._build_payload(
    mission_id,
    date(2022, 2, 1),
    date(2022, 2, 28),
)

analysis_id = traffic._do_analyze(client.session, mission_id, payload)
print(analysis_id)

traffic._get_partial_result(client.session, analysis_id)

file_guid, file_name = traffic._get_file_metadata(client.session, analysis_id)
print(file_guid, file_name)

filepath = traffic._download_excel(
    client.session,
    file_guid,
    mission_id,
    date(2022, 2, 1),
    date(2022, 2, 28),
)
print(filepath)


# =========================
# TEST CASE 2
# =========================
mission_id = 40687

row = missions_df[missions_df["Id"] == mission_id].iloc[0]
from_date = traffic._parse_date(row["FromDate"])
to_date = traffic._parse_date(row["ToDate"])
print(from_date, to_date)

traffic.download_mission(client, mission_id, from_date, to_date)


# =========================
# SANITY CHECK
# =========================
print(traffic._parse_date("1645794000000"))
