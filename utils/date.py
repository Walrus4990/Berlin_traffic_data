import re
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

# --- Date parsing: Convert milliseconds (ms) string to datetime and back watching out for timezone

def parse_date(raw: str) -> datetime:
    ms = int(re.search(r"\d+", raw).group())
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).astimezone(ZoneInfo("Europe/Berlin"))


# --- return the correct timestamp to feed teh download portal with
def yesterday_end() -> datetime:
    now = datetime.now(tz=ZoneInfo("Europe/Berlin"))
    return now.replace(hour=23, minute=59, second=59, microsecond=0) - timedelta(days=1)
