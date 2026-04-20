import re
from datetime import datetime, timezone
import pytz

# --- Date parsing: Convert milliseconds (ms) string to datetime and back watching out for timezone

def parse_date(raw: str) -> datetime:
    ms = int(re.search(r"\d+", raw).group())
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).astimezone(
        pytz.timezone("Europe/Berlin")
    )
