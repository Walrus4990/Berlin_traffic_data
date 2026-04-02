
# CLeaning traffic data file process

## Step 1

**Columns to drop on ingestion:**

| Column                            | Reason                                                                                    |
| --------------------------------- | ----------------------------------------------------------------------------------------- |
| `Schall (dB)`                     | Always 0 — never implemented                                                              |
| `Abstand (cm)`                    | Always 0 — never implemented                                                              |
| `Fahrspur`                        | Always 0 — never implemented— multi-lane indicator, not applicable on residential streets |
| `Eintrittsgeschwindigkeit (km/h)` | Always 0 — never implemented— single speed value sufficient                               |
| `Austrittsgeschwindigkeit (km/h)` | Always 0 — never implemented— single speed value sufficient                               |
| `Richtung`                        | Direction — for paired sensor analysis - always 1 - not useful to find direction          |

**Columns to keep:**

| Column                        |                                                              |
| ----------------------------- | ------------------------------------------------------------ |
| `Geräte-ID`                   | Sensor identifier                                            |
| `Datum`                       | Timestamp to the second                                      |
| `Geschwindigkeit (km/h)`      | Individual vehicle speed                                     |
| `Länge (dm)`                  | Vehicle length — useful for classification consistency check |
| `Klasse`                      | Numeric vehicle class code                                   |
| `Fahrzeugklassen-Bezeichnung` | Vehicle class label — human readable                         |

---

## Step 2 — Parse and standardise timestamp

- Parse `Datum` to datetime — format DD.MM.YYYY HH:MM:SS
- Extract `datum` (date) and `stunde` (hour, 0–23) as separate columns
- Flag any rows with unparseable timestamps — do not drop, investigate

---

## Step 3 — Validate Geräte-ID

- Check every `Geräte-ID` exists in device reference table
- Flag any records where no match is found — sensor may have been deployed without being registered, or georeferencing table has not been updated after a move
- Do not drop — flag for investigation

---

## Step 4 — check unclassifiable vehicles and blanks

- Check rows where `Klasse` = 6 (unclassified) or 250 (partially obscured)
- Log count of mostly rows per sensor — a high drop rate indicates a sensor alignment or obstruction problem
- discuss oddities and develop exclusion routine

---

## Step 5 — Speed plausibility check

- Flag any motorised vehicle where `Geschwindigkeit` > 150 km/h
- Flag any motorised vehicle where `Geschwindigkeit` < 1 km/h
- Flag any bicycle where `Geschwindigkeit` >50 km/h
- Do not drop flagged rows automatically — log and investigate, develop exclusion routine

---

## Step 6 — Length plausibility check

- Cross-check `Länge (dm)` against expected range for declared `Klasse`:

|Klasse|Expected length range (dm)|
|---|---|
|Pkw (7)|30–55|
|PkwA (2)|50–80|
|Lfw (11)|40–65|
|Lkw (3)|60–120|
|LkwA (8)|100–180|
|Sattel-Kfz (9)|120–200|
|Bus (5)|80–180|
|Krad (10)|15–30|
|Fahrrad (230)|10–25|

- Flag rows where length falls outside expected range for declared class
- Do not drop — a mismatch may indicate misclassification rather than an error
- According to engineers the sensors may not be very good at measuring this. Report back your findings and let's draw conclusions about vehicle classification.

---

## Step 7 — Duplicate detection

- Flag duplicates — do not drop automatically
- True duplicates are rare and likely indicate a data transmission error

---

## Step 8 — Completeness check

- Check for sensor error by calculating average number of expected records per sensor-hour/location
- Flag any hour where completeness < 80%, many indicate fault/low battery
