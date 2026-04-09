# Joining adn Aggregrating

- - -
## Step 1 — Aggregate to hourly

- Group `traffic` by `Geräte-ID` + `datum` + `stunde` + `Richtung`
- Calculate per group:
    - Count per vehicle class → modal split inputs
    - Mean speed per vehicle class → average speed
    - 85th percentile speed (excl. Fahrrad, Krad) → V85
    - Total vehicle count → hourly flow
- Carry forward any flags from steps 4–8 as aggregate-level flags
- - -

## Step 2 — Joining deployment and location
* examine best join strategy, below are two options
* discuss in team and with teachers which is best for automation
* Option 1:
	* deterministic string cleaning → then exact join
	- Create `standort_key` in **deployment** and **location**
	- transform Standort & Descriptions:
	    - lowercase
	    - trim
	    - collapse spaces
	    - normalize `"dd####"` → `"dd ####"`
	    - remove minor noise (`i.h.`, `in hö.` etc. if safe)
	- Join: deployment and location on standort_key
	- May require manual matching - not good for automation
* Option 2:
* extract DD number from `Standort` and use it as auxiliary key
* Extract Gerät-ID from Standort using regex in both location and deployment file
* Compare Geräte-ID in both files & merge on Geräte-ID

---

## Step 3 — Joining traffic and deployment

* join traffic and deployment file on
	* Gerät-ID **AND**
	* datum in `traffic`BETWEEN  startdatum AND enddatum in `deployment`
* check that each device (Gerät-ID) is only deployed once after joining - raise a BIG error

- - - -

## Step 4 — Identify sensor pairs
- Filter sensors on the same street name and timestamps -> identify as pairs
- Confirm opposite or complementary `Fahrtrichtung` and `Gegenrichtung` (might be too manual)
- Use longitude and latitude to check lateral proximity across street (approximate offset equal to street width)
- add the following columns
	- is_pair - Boolean - Quick flag whether a sensor belongs to a paired setup
	-  pair_id - Groups sensors that belong to the same pair (create the ID)

---

## Step 5 — Near-school flag

- Flag all records from sensors located near schools, look at description for word 'Schule' in description fields
