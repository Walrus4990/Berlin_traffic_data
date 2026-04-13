from etl.ddweb_auth import DDWebAuth
from etl.ddweb_ingest_traffic import _build_payload, _do_analyze, _parse_date
from etl.ddweb_ingest import fetch_missions
from datetime import date

auth = DDWebAuth()
auth.ensure_authenticated()

missions_df = fetch_missions(auth)
print(missions_df[["Id", "FromDate", "ToDate"]].head())

row = missions_df[missions_df["Id"] == 40671].iloc[0]
from_date = _parse_date(row["FromDate"])
to_date = _parse_date(row["ToDate"])
print(from_date, to_date) #2022-01-28 2023-04-29


payload = _build_payload(40671, date(2022, 2, 1), date(2022, 2, 28))
analysis_id = _do_analyze(auth.session, 40671, payload)
print(analysis_id)#294138

from etl.ddweb_ingest_traffic import _get_partial_result
_get_partial_result(auth.session, 294139)

from etl.ddweb_ingest_traffic import _get_partial_result
_get_partial_result(auth.session, 294139)

from etl.ddweb_ingest_traffic import _get_file_metadata
file_guid, file_name = _get_file_metadata(auth.session, 294139)
print(file_guid, file_name)

from etl.ddweb_ingest_traffic import _download_excel
filepath = _download_excel(auth.session, file_guid, 40671, date(2022, 2, 1), date(2022, 2, 28))
print(filepath)

from etl.ddweb_auth import DDWebAuth
from etl.ddweb_ingest import fetch_missions
from etl.ddweb_ingest_traffic import download_mission, _parse_date
from datetime import date

auth = DDWebAuth()
auth.ensure_authenticated()

missions_df = fetch_missions(auth)
row = missions_df[missions_df["Id"] == 40687].iloc[0]
from_date = _parse_date(row["FromDate"])
to_date = _parse_date(row["ToDate"])
print(from_date, to_date)
download_mission(auth, 40687, from_date, to_date)
