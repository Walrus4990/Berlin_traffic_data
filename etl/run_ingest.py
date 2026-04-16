"""
run_ingest.py — Quick ingest runner for local testing
=====================================================
Fetches missions + locations from the DDweb portal, then downloads
traffic data for active missions.

By default downloads only the most recent FULL calendar month so you
get real data quickly (~20 s per mission instead of minutes/hours).
Pass --full to download the complete history for all missions.

Usage (from project root):
    python etl/run_ingest.py           # last full month only
    python etl/run_ingest.py --full    # all historical data (slow)
"""

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

# ── Project root on path ──────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from etl.ddweb_auth import DDWebAuth
from etl.ddweb_ingest_ref import fetch_missions, fetch_locations
from etl.ddweb_ingest_traffic import _parse_date, download_mission, DOWNLOAD_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

BERLIN = ZoneInfo("Europe/Berlin")
ACTIVE_SENTINELS = {"2049", "2100"}   # years used as "still active" markers


def _last_full_month() -> tuple[datetime, datetime]:
    """Return (first_day, last_day) of the most recently completed calendar month."""
    import calendar
    today = datetime.now(tz=BERLIN)
    # Step back to last month
    if today.month == 1:
        year, month = today.year - 1, 12
    else:
        year, month = today.year, today.month - 1
    last_day = calendar.monthrange(year, month)[1]
    start = datetime(year, month, 1,  tzinfo=BERLIN)
    end   = datetime(year, month, last_day, tzinfo=BERLIN)
    return start, end


def run(full_history: bool = False) -> None:
    # ── Step 1: Authenticate ──────────────────────────────────────────────────
    logger.info("Authenticating with DDweb portal …")
    auth = DDWebAuth()
    auth.ensure_authenticated()
    logger.info("Authenticated.")

    # ── Step 2: Fetch missions ────────────────────────────────────────────────
    logger.info("Fetching missions …")
    missions_df = fetch_missions(auth)
    logger.info("Retrieved %d missions.", len(missions_df))
    print("\nMissions:")
    print(missions_df[["Id", "Description", "FromDate", "ToDate", "DeviceNumber"]].to_string(index=False))

    # ── Step 3: Fetch locations ───────────────────────────────────────────────
    logger.info("Fetching locations …")
    locations_df = fetch_locations(auth)
    logger.info("Retrieved %d locations.", len(locations_df))
    print("\nLocations:")
    print(locations_df[["Id", "LocationTitle", "PosUserLat", "PosUserLng"]].to_string(index=False))

    # ── Step 4: Download traffic files ───────────────────────────────────────
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(tz=BERLIN)

    if full_history:
        logger.info("--full flag set: downloading complete history for all missions.")
    else:
        dl_start, dl_end = _last_full_month()
        logger.info(
            "Downloading most recent full month: %s → %s",
            dl_start.strftime("%Y-%m-%d"), dl_end.strftime("%Y-%m-%d"),
        )

    downloaded: list[Path] = []
    skipped = 0

    for _, row in missions_df.iterrows():
        mission_id = int(row["Id"])
        mission_from = _parse_date(row["FromDate"])
        mission_to_raw = _parse_date(row["ToDate"])

        # Clamp the end date: don't go past today
        mission_to = min(mission_to_raw, today)

        if full_history:
            dl_from, dl_to = mission_from, mission_to
        else:
            # Intersect mission window with last full month
            dl_from = max(mission_from, dl_start)
            dl_to   = min(mission_to,   dl_end)

            if dl_from > dl_to:
                logger.info("Mission %d not active in last full month — skipping.", mission_id)
                skipped += 1
                continue

        logger.info(
            "Mission %d (%s): downloading %s → %s",
            mission_id, row.get("Description", ""),
            dl_from.strftime("%Y-%m-%d"), dl_to.strftime("%Y-%m-%d"),
        )
        try:
            files = download_mission(auth, mission_id, dl_from, dl_to)
            downloaded.extend(files)
        except Exception as exc:
            logger.error("Mission %d failed: %s", mission_id, exc)

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'─'*50}")
    print(f"Download complete.")
    print(f"  Files written : {len(downloaded)}")
    print(f"  Missions skipped (not active in window): {skipped}")
    print(f"  Location      : {DOWNLOAD_DIR.resolve()}")
    if downloaded:
        print("  Files:")
        for f in downloaded:
            print(f"    {f.name}")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--full",
        action="store_true",
        help="Download complete history for all missions (slow — many hours).",
    )
    args = parser.parse_args()
    run(full_history=args.full)
