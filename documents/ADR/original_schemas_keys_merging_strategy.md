# ADR — ID Fields Across Portal Data Types
_Date: 2026-05-07_

## Context

The DDWeb portal serves three data types: missions, locations, and traffic files.
Each has its own identifier. The naming is inconsistent across the portal API,
our rename layer, and the payload used to request traffic data.

## ID Fields by Data Type

**Mission**
- Portal name: `Id`
- Payload name: `OrderId` — the portal uses this term when requesting traffic data, creating confusion with mission identity
- Our name after rename: `mission_id`
- Role: unique key for each sensor deployment. One mission = one device at one location for one time period.

**Location**
- Portal name: `Id`
- Our name after rename: `location_id`
- Role: unique key for each physical location record. Not present in mission or traffic data — not used as a join key.
- join key: `LocationTitle` in portal `location_title` after rename

**Traffic (per row)**
- Portal name: `Geräte-ID`
- Our name after rename: `device_id`
- Role: identifies the physical sensor device. Not unique as a key — one device has multiple missions over time as it moves between locations.
- `mission_id` is absent from the portal Excel export. It is known at download time and will be stamped onto the dataframe in `_download_into_parquet` before saving to parquet.


## Portal Raw Field Names — Reference

### Mission (`/Mission/ReadDataAjax`)

| Portal field | Type | Notes |
|---|---|---|
| `Id` | int | mission identifier, called `OrderId` in traffic payload |
| `Created` | str | `/Date(ms)/` format |
| `FromDate` | str | `/Date(ms)/` format |
| `ToDate` | str | `/Date(ms)/` format, sentinel values 2049/2100 = active |
| `Description` | str | |
| `LocationTitle` | str | join key to location table |
| `City` | str | |
| `Street` | str | |
| `StreetNumber` | str | |
| `Zipcode` | str | |
| `DeviceNumber` | int | physical sensor identifier |
| `DeviceType` | str | e.g. `DD.plus` |

### Location (`/Location/ReadDataAjax`)

| Portal field | Type | Notes |
|---|---|---|
| `Id` | int | location identifier, not used as join key |
| `Created` | str | `/Date(ms)/` format |
| `Description` | str | |
| `LocationTitle` | str | join key to mission table |
| `Street` | str | |
| `StreetNumber` | str | |
| `Zipcode` | str | |
| `City` | str | |
| `DrivingDirection` | str | e.g. Nord, Süd |
| `OppositeDirection` | str | |
| `PosUserLat` | float | GPS latitude, inferred by pandas from JSON |
| `PosUserLng` | float | GPS longitude, inferred by pandas from JSON |

### Traffic (Excel export via `/AnalysisX/DownloadExcel`)

| Portal field | Type | Notes |
|---|---|---|
| `Geräte-ID` | int | physical sensor identifier |
| `Datum` | str | timestamp, dayfirst format |
| `Richtung` | int | always 0 — dropped at ingest |
| `Fahrspur` | int | always 0 — dropped at ingest |
| `Geschwindigkeit (km/h)` | int | always 0 — dropped at ingest |
| `Eintrittsgeschwindigkeit (km/h)` | int | entry speed |
| `Austrittsgeschwindigkeit (km/h)` | int | exit speed |
| `Länge (dm)` | int | vehicle length |
| `Klasse` | int | vehicle class code |
| `Fahrzeugklassen-Bezeichnung` | str | vehicle class label e.g. Pkw |
| `Schall (dB)` | int | always 0 — dropped at ingest |
| `Abstand (cm)` | int | always 0 — dropped at ingest |

### Join Keys

| Join | Key | Notes |
|---|---|---|
| traffic → mission | `mission_id` | stamped at ingest from filename, not in portal export |
| mission → location | `LocationTitle` | human-entered, confirmed 1:1, duplicates across time acceptable |

## Columns Dropped from Traffic at Ingest

`Richtung`, `Fahrspur`, `Geschwindigkeit (km/h)`, `Schall (dB)`, `Abstand (cm)` — confirmed always zero, dropped before parquet write via `TRAFFIC_COLS_DROP`.


## Decisions

- `location_title` duplicates across time are expected and acceptable — same physical spot can host different missions at different times with slightly different human-entered descriptions.
