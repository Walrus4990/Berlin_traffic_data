## Datetime and timezone handling across pipeline phases

**Portal boundary (bronze ingest — missions)**
`parse_date()` converts millisecond epoch strings from the DDWeb portal API
to timezone-aware `datetime` objects in `Europe/Berlin`. Used in
`ingest_missions()` for `created_at`, `start_date`, `end_date`.

**Portal boundary (download — traffic chunks)**
`parse_date()` used in `weekly_download()` and `complete_download()` for
mission `FromDate` and `ToDate`. Chunk boundaries passed to `_build_payload()`
as `"%d.%m.%Y %H:%M"` strings — portal expects Berlin local time, which
`parse_date()` correctly produces.

**Bronze storage — traffic**
`date_raw` stored as raw TEXT. The portal exports `Datum` as a naive Berlin
local time string e.g. `"04/23/2026 00:01:20"` with no timezone indicator.
No parsing at bronze — intentional. Timezone correctness is preserved because
the portal is a Berlin-based system and exports in local time.

**PostgreSQL storage — missions**
`parse_date()` produces timezone-aware datetimes. PostgreSQL `TIMESTAMP`
(without time zone) strips timezone on write. Silver reads these back as naive
timestamps. This is acceptable because all timestamps originate from the same
timezone and comparisons in silver are internal.

**Silver — timestamp parsing**
`pd.to_datetime(date_raw, dayfirst=True, errors="coerce")` produces naive
timestamps already in Berlin local time. `stunde` derived from these is
correct for gold hourly aggregation — no UTC offset risk.

**Gold — hourly aggregation**
`stunde` is reliable because `date_raw` is Berlin local time at source. Rush
hour buckets (07:00–09:00) are correct.

**Rule: never apply timezone conversion in silver or gold.** Timestamps are
naive but implicitly Berlin local throughout. Applying tz conversion at a later
stage would corrupt the data.
