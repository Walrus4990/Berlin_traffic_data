
# Indicator definitions, calculation & translations

**Vehicle codes**
notes:
* van/LKW distinction is unreliable at lower speeds
* Bike count unreliable at lower speeds

| Code | German Label              | English Label                  | Notes                           |
| ---- | ------------------------- | ------------------------------ | ------------------------------- |
| 2    | PkwA                      | Car with trailer               |                                 |
| 3    | Lkw                       | Lorry                          |                                 |
| 4    | Lkwk                      | Lorry (short)                  |                                 |
| 5    | Bus                       | Bus                            |                                 |
| 6    | Kfz (nicht klassifiziert) | Motor vehicle (unclassified)   |                                 |
| 7    | Pkw                       | Car                            | Confirmed from sample data      |
| 8    | LkwA                      | Lorry with trailer             |                                 |
| 9    | Sattel-Kfz                | Articulated vehicle / HGV      |                                 |
| 10   | Krad                      | Motorcycle                     |                                 |
| 11   | Lfw                       | Delivery van                   |                                 |
| 34   | SGV                       | Heavy goods vehicle (combined) |                                 |
| 37   | LVm                       | Light motorised vehicle        |                                 |
| 40   | SV                        | Special vehicle                |                                 |
| 64   | Kfz                       | Motor vehicle (all)            | Top-level grouping              |
| 230  | Fahrrad                   | Bicycle                        | Confirmed from sample data      |
| 250  | Teilverdeckte Kfz         | Partially obscured vehicle     | Sensor could not fully classify |
- - -

**Modal Share (Modal Split)**

- German label: Modalsplit
- Definition: Share of each vehicle type as percentage of total traffic
- Calculation:

	Share of cars (%) = (Cars / Total vehicles) × 100
	Share of lorries (%) = (Lorries / Total vehicles) × 100
	Share of bikes (%) = (Bikes / Total vehicles) × 100

- Where total vehicles = Cars + Lorries + Delivery vans + Motorcycles + Bikes
- Notes: Denominator must include all vehicle types.
- Guard against division by zero.
- Note that bikes under 10km/h may be undercounted

---

**V85**

- German label: V85 (85. Perzentil-Geschwindigkeit)
- Definition: The speed below which 85% of vehicles travel. Standard input for speed limit assessments.
- Calculation:

```python
v85 = df['speed'].quantile(0.85)
```

- Exclude bicycles

---

**Average Speed by Vehicle Type**

- German label: Durchschnittsgeschwindigkeit
- Definition: Mean speed in km/h per vehicle type per hour
- Calculation:
	Average speed (km/h) = Sum of speeds of all vehicles / Number of vehicles

* So for cars: Average speed PKW = Sum of all individual PKW speeds / Number of PKW
* Note: exclude bikes due to measurement errors at low speed.

---

**Traffic peaks - Hourly Flow**

- German label: Durchfahrten pro Stunde
- Definition: Total vehicle count per hour per sensor
- Calculation:
	Hourly flow = total vehicle count recorded by a single sensor in a one-hour period.

- Notes: The Dashboard will require averaging the hourly flow across days.
- used to plot **Traffic Flow Over Time)**
	- German label: Ganglinie
	- Definition: Time-series of vehicle counts showing traffic patterns over hours, days, weeks or seasons
	- Calculation: group by date + hour, plot count

---
### Not in Dashboard - one-off analyses:
---

**Before/After Index**

- German label: Vorher-Nachher-Vergleich
- Background: The Bezirksamt Tempelhof-Schöneberg has implemented two traffic infrastructure interventions on specific streets:

	- Handjerystraße — converted to a Fahrradstraße, completed May 2024
	- Boelckestraße — new protected cycle lanes, Tempo 30, and zebra crossings, completed April 2024. Construction began September 2023.

* The purpose of the before/after comparison is to measure whether these interventions had a measurable effect on traffic behaviour:
	* did modal split shift toward cycling,
	* did vehicle speeds decrease,
	* did total motorised traffic volume change?
- Definition: Percentage change in indicator between pre- and post-intervention periods
- Calculation:

```python
delta = (post_value - pre_value) / pre_value * 100
```

- Construction period (Boelckestr. Sep 2023 – Apr 2024, Handjerystr. until May 2024) should be excluded from both pre and post periods or flagged separately.

---

**Schulwegbelastung (School Route Traffic)**

- German label: Schulwegbelastung
- Background: measure traffic volume and speed during the hours when children are travelling to and from school — typically 07:00–09:00 in the morning and 12:00–15:00 in the afternoon
- Definition: Traffic volume during school arrival and departure hours
- Calculation: filter stunde IN (7, 8, 13, 14, 15), aggregate kfz
- Notes: sensors located near schools may show anomalous speed readings due to very slow-moving vehicles during drop-off and pick-up..
