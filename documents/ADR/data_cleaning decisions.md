# ADR: Silver Layer Data Quality — Traffic Sensor Data

## Context
Tempelhof-Schöneberg traffic sensor pipeline. 38.5m rows in `silver.traffic`. Single-point sensors mounted on residential streets. All findings based on exploratory queries against existing `silver.traffic`.

---

## DQ-01: Timestamp completeness
**Query:** COUNT(*) WHERE datum_parsed IS NULL and check for zero/epoch values in date_raw
**Result:** 0 NULLs, 0 zeros, 0 epoch values across 28m rows. date_raw is always populated and always parses to a valid timestamp.
**Decision:** No flag needed. Timestamp is a fully reliable column.

---


## DQ-02: Motorised speed distribution
**Query:** Proportion above 60-110kmh and below 1-10kmh using `GREATEST(speed_entry, speed_exit)`

| threshold | proportion |
|-----------|-----------|
| >100kmh | 0.004% |
| >60kmh | 0.13% |
| <3kmh | 0% |
| <10kmh | 0.06% |

**Decision:** Keep `SPEED_MAX_MOTORISED = 100`. No lower bound set. Sensor detection floor means effectively 0% below in practice.
**Note:** Sensor unreliable below ~7-10kmh — no readings observed below this in practice.

---

## DQ-03: Bicycle speed distribution
**Query:** Quintiles + min + % above 40 using `GREATEST(speed_entry, speed_exit)`

| stat | value |
|------|-------|
| min | 9kmh |
| p20 | 15kmh |
| p40 | 18kmh |
| p60 | 20kmh |
| p80 | 23kmh |
| max | 42kmh |
| >40kmh | 0.00001% |

**Decision:** Keep `SPEED_MAX_BICYCLE = 40`. Negligible rows above threshold.
**Note:** min=9kmh reflects sensor sensitivity floor, not true minimum cycling speed.


## DQ-04: Speed column construction

### Sensor characteristics
Single-point sensor. Entry and exit are two readings milliseconds apart at the same location. Sensors stop being accurate below 10kmh as per manufacturer

### Entry vs exit reliability — they fail differently
- `speed_entry`: never NULL/zero. Contains values >100 that are not real speeds: 157, 160, 175, 180, 185, 201 etc. Also clusters at exact low integers (5, 8, 9kmh). This is close to the sensor detectable speed floor and likely a misread. Note 348 rows with entry=201, potential error code.
- `speed_exit`: 935 000 zeros (~2%) interpreted as missing values (NULL) — sensor failed to record exit reading. Small counts of values >150. Exit speed is cleaner than entry speed at normal speeds but as a significant null problem.
- Neither column is fully reliable. They fail in complementary ways: entry has many high values, exit has many zeros, both indicate sensor error.

### Speed column construction
1. Flag speed values >100 in either entry or exit as error codes
2. Set values values >100 in either entry or exit as NULL (missing)
3. Set zeros in either entry or exit as NULL (missing)
4. Apply `GREATEST(speed_entry_clean, speed_exit_clean)` — picks the highest reading between ebtry and exit, after likely sensor errors haev been set to missing
5. 41 rows where both entry and exit >100 — `speed` will be NULL, row kept

### Speed flags (applied on raw values before nulling)
- `flag_speed_entry_100`: `speed_entry > 100`
- `flag_speed_exit_100`: `speed_exit > 100`
- `flag_speed_100`: motorised class AND `GREATEST(speed_entry, speed_exit) > 100`
- `flag_bike_speed_40`: bicycle class AND `GREATEST(speed_entry, speed_exit) > 40`

---

## DQ-05: Speed ratio distribution
**Query:** `GREATEST/LEAST` ratio on rows where `speed_exit > 0`
**Overall avg ratio:** 1.12

| class | n | >1.5 | >2.0 | >2.5 | >3.0 | >3.5 | avg ratio | stdev |
|-------|---|------|------|------|------|------|-----------|-------|
| bicycle | 6.9m | 8.4% | 2.1% | 0.8% | 0.3% | 0.15% | 1.18 | 0.29 |
| motorised | 30.7m | 2.8% | 0.55% | 0.17% | 0.07% | 0.03% | 1.10 | 0.18 |
| other | 39k | 3.6% | 1.3% | 0.9% | 0.6% | 0.49% | 1.15 | 0.34 |

At 3 stdev above mean: motorised cutoff = 1.64, bicycle = 2.05.
High ratios driven by entry speed misreads at sensor floor — physically impossible over sensor distance.
**Decision:** for info only, no flag implemented.

---

## DQ-06: Duplicate rows
**Query:** `ROW_NUMBER() OVER PARTITION BY device_id, date_raw, vehicle_class, speed_entry, speed_exit, length_dm`
**Result:** 79 duplicate rows total (~0.0002% of 38m rows)

- All duplicates n=2 — no triple or higher
- Concentrated in devices 5950, 5951, 7207, may indicate persistently degraded sensors double-firing
- Sporadic across time — months apart, not consecutive — rules out bulk re-ingestion error


**Decision:** Flag with `flag_duplicate`. Keep first occurrence by `ingested_at`, drop second. Log count to DQ report.

---

## DQ-7: Multi-location device readings
No true location duplicates. Readings on the same day at two locations represent the sensor being physically moved. Pattern consistent — old deployment ends, new starts same day with 1-3 hour gap.

| device_id | datum | location | start | end | n |
|-----------|-------|----------|-------|-----|---|
| 5949 | 2023-03-18 | Bahnstraße Nr. 10 | 2022-02-25 | 2023-03-18 07:00 | 66 |
| 5949 | 2023-03-18 | Wehnertstraße | 2023-03-18 10:10 | 2026-03-13 | 294 |
| 5949 | 2023-03-18 | NULL | — | — | 23 |
| 5949 | 2026-03-13 | DD 5949 Halker Zeile | 2026-03-13 12:00 | 2048-12-31 | 883 |
| 5949 | 2026-03-13 | Wehnertstraße | 2023-03-18 | 2026-03-13 10:00 | 76 |
| 6424 | 2025-01-25 | Handjerystraße neu | 2025-01-25 12:00 | 2048-12-31 | 830 |
| 6424 | 2025-01-25 | Handjerystraße Nr. 6-9 | 2022-02-26 | 2025-01-25 10:00 | 142 |
| 6424 | 2025-01-25 | NULL | — | — | 9 |
| 6428 | 2023-04-15 | Goethstraße | 2023-04-15 11:00 | 2023-10-02 | 481 |
| 6428 | 2023-04-15 | Waldsassener Straße | 2022-03-14 | 2023-04-15 08:00 | 163 |
| 6428 | 2023-04-15 | NULL | — | — | 112 |
| 6428 | 2023-10-02 | Goethstraße | 2023-04-15 | 2023-10-02 17:00 | 791 |
| 6428 | 2023-10-02 | Halker Zeile | 2023-10-02 19:00 | 2048-12-31 | 48 |
| 6428 | 2023-10-02 | NULL | — | — | 62 |
| 6429 | 2023-04-29 | Albanstraße | 2022-01-28 | 2023-04-29 09:00 | 109 |
| 6429 | 2023-04-29 | Goethestraße | 2023-04-29 11:00 | 2023-10-02 | 476 |
| 6429 | 2023-04-29 | NULL | — | — | 142 |
| 7206 | 2023-04-29 | Eisenacher Straße | 2022-12-07 | 2023-04-29 08:00 | 109 |
| 7206 | 2023-04-29 | Lessingstraße | 2023-04-29 11:00 | 2100-01-01 | 156 |
| 7206 | 2023-04-29 | NULL | — | — | 9 |
| 7208 | 2023-04-15 | Goltzstraße | 2022-12-07 | 2023-04-15 08:00 | 8 |
| 7208 | 2023-04-15 | Lessingstraße | 2023-04-15 09:00 | 2100-01-01 | 326 |
| 7208 | 2023-04-15 | NULL | — | — | 5 |
| 7871 | 2026-03-14 | Monopolstraße | 2025-08-16 | 2026-03-14 09:00 | 11 |
| 7871 | 2026-03-14 | Schulenburgring | 2026-03-14 12:00 | 2100-01-01 | 95 |
| 7871 | 2026-03-14 | NULL | — | — | 9 |
| 7872 | 2026-03-14 | Monopolstraße | 2025-08-16 | 2026-03-14 10:00 | 9 |
| 7872 | 2026-03-14 | Schulenburgring | 2026-03-14 13:00 | 2100-01-01 | 153 |
| 7872 | 2026-03-14 | NULL | — | — | 9 |
| 8472 | 2026-03-13 | Briesingstraße | 2025-10-25 | 2026-03-13 10:00 | 48 |
| 8472 | 2026-03-13 | Halker Zeile | 2026-03-13 10:00 | 2100-01-01 | 606 |

**NULL location rows:** Small counts (5-142) on transition days — sensor recording during physical move, not yet assigned to new mission.
**Decision:** Drop NULL location rows — no valid location, limited analytical value.

---

## DQ-8: Unclassifiable vehicles
Only class 6 (nk Kfz) present — class 250 absent from data entirely.

| class | label | n | % | avg speed | median speed | avg length | median length |
|-------|-------|---|---|-----------|--------------|------------|---------------|
| 6 | nk Kfz | 39,853 | 0.10% | 27 | 28 | 49dm | 44dm |

Speed and length profile consistent with class 7 (Pkw). Negligible volume.
**Decision:** No flag, no drop. Keep in silver as-is.

---

## DQ-9: Length data quality

### Sensor characteristics
Length unreliable across most classes, particularly slow-moving traffic. Sensor always records a value — no NULLs or zeros observed.

### Expected vs observed bounds (dm)

| class | label | min obs | max obs | avg | n | min exp | max exp |
|-------|-------|---------|---------|-----|---|---------|---------|
| 2 | PkwA | 1 | 255 | 84 | 409k | 55 | 188 |
| 3 | Lkw | 1 | 246 | 75 | 960k | 50 | 120 |
| 5 | Bus | 12 | 216 | 133 | 254k | 60 | 188 |
| 6 | nk Kfz | 1 | 255 | 49 | 40k | 15 | 120 |
| 7 | Pkw | 6 | 250 | 42 | 26.1m | 25 | 120 |
| 8 | LkwA | 1 | 255 | 123 | 94k | 80 | 188 |
| 9 | Sattel-Kfz | 1 | 255 | 148 | 63k | 100 | 165 |
| 10 | Krad | 10 | 27 | 22 | 1.2m | 15 | 40 |
| 11 | Lfw | 8 | 186 | 56 | 2.4m | 35 | 120 |
| 230 | Fahrrad | 8 | 23 | 16 | 6.9m | 10 | 20 |

### Legal length context
- 18.75m: EU/German max for most vehicle combinations
- 16.50m: semitrailer combinations
- 25.25m: Gigaliner/EMS limit, specific routes only
- 255dm: sentinel/error code — appears as max across multiple classes, above any legal vehicle length

### Min floor reasoning
- Pkw min reflects smallest production cars (~2.5m sensor detection threshold)
- LkwA/Sattel-Kfz minimums reflect tractor unit alone ~6m
- Krad/LVm share ~1.50m as practical sensor detection floor for two-wheelers
- Fahrrad uses 1.00m as absolute sensor floor

### Out-of-range counts

| class | label | below min | above max | total |
|-------|-------|-----------|-----------|-------|
| 2 | PkwA | 15,106 | 540 | 409k |
| 3 | Lkw | 146,729 | 10,780 | 960k |
| 5 | Bus | 523 | 6,582 | 254k |
| 6 | nk Kfz | 82 | 1,713 | 40k |
| 7 | Pkw | 9,635 | 277 | 26.1m |
| 8 | LkwA | 14,044 | 9,415 | 94k |
| 9 | Sattel-Kfz | 2,454 | 16,213 | 63k |
| 10 | Krad | 31,994 | 0 | 1.2m |
| 11 | Lfw | 97 | 2 | 2.4m |
| 230 | Fahrrad | 216,539 | 623,627 | 6.9m |

Bicycles worst affected (~12% outside bounds) — sensor struggles with thin/slow two-wheelers. May indicate undercounting or overcounting of cyclists.
**Decision:** Flag `flag_length_below_min` and `flag_length_above_max` per class. No drops. Log counts to DQ report per class. Note bicycle sensor unreliability in DQ report.

---

## DQ-10: Vehicle class distribution

| class | label | n | % |
|-------|-------|---|---|
| 7 | Pkw | 26.1m | 67.77% |
| 230 | Fahrrad | 6.9m | 18.04% |
| 11 | Lfw | 2.4m | 6.26% |
| 10 | Krad | 1.2m | 3.21% |
| 3 | Lkw | 960k | 2.49% |
| 2 | PkwA | 409k | 1.06% |
| 5 | Bus | 254k | 0.66% |
| 8 | LkwA | 94k | 0.24% |
| 9 | Sattel-Kfz | 63k | 0.16% |
| 6 | nk Kfz | 40k | 0.10% |

Cars dominate at 68% — consistent with urban residential. Bicycles at 18% — likely undercounted given sensor limitations. Delivery vans (Lfw) at 6% — plausible for last-mile logistics. Heavy vehicles combined ~3% — expected on residential streets. No unexpected classes present. Label/class mapping is 1:1 and consistent throughout.

**Decision:** `vehicle_class_label` redundant with `vehicle_class` — keep both in silver for now.
