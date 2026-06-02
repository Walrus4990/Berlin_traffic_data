# Berlin Traffic Data
## Verkehrsdaten nutzbar machen

Built with the Straßen- und Grünflächenamt Tempelhof-Schöneberg and the
CityLAB Data Hub Berlin.

## Background

**The problem:** Bezirksämter are responsible for residential streets.
They make decisions about traffic calming in front of schools, bicycle
street assessments, and responding to citizen complaints about speeding.
To make these decisions well, they need data.

The data exists. Berlin uses commercial off-the-shelf vehicle counters
(Dialogdisplays) that record vehicle counts, speeds, and type splits at
hourly resolution. There are 20-30 units in Tempelhof-Schöneberg alone,
generating roughly 2.5 million rows per month. The devices are mobile
and get moved between locations. Each device has a permanent ID but
can appear at different locations over time.

The data is not useable as-is. To access it, someone must log into the
manufacturer's portal, navigate a menu, and download one month of data
for one location at a time. For Tempelhof-Schöneberg that means 900
files and two working days just to get the raw material. Sensors cannot
be compared directly in the portal. Long-term trends are not visible.

This is not an access problem. The Bezirk owns the sensors. It is a
data shape problem.

**The solution:** An automated pipeline that ingests, cleans, and
aggregates the sensor data, stores it in a database, and surfaces it
via an interactive dashboard and a downloadable Excel summary file.

## Stack

Production runs on a managed Kubernetes cluster provided by the CityLAB
Data Hub (https://data-hub.berlin/). Local development uses Docker
Compose to mirror the production environment. In production, service
connections are configured directly on the Kubernetes cluster without
Docker.

* Airflow for orchestration
* MinIO for raw data archiving
* PostgreSQL for cleaned and aggregated data
* Superset for dashboards

## Pipeline (etl/)

1. Ingest from manufacturer portal into MinIO buckets (ddweb*.py)
2. Clean with pandas: deduplication, format standardisation (silver*.py)
3. Compute indicators: modal split, V85, speed distributions (silver*.py)
4. Join location, mission and traffic tables and aggregate (gold*.py)
5. Write to PostgreSQL across bronze, silver and gold layers
6. Surface via Superset dashboard (dashboard.py) and Excel export

## Useful docs

* Data structure: documents/ADR/original_schemas_keys_merging_strategy.md
* Indicator definitions: documents/indicator_def_calc_translation.md

## Reuse

The code is modular. Other Bezirke can adapt it for their own
Dialogdisplay data with minimal changes. If you are interested,
open an issue or get in touch.

## Dev Setup

1. Clone the repo
2. Copy `.env.example` to `.env` and fill in your DDWEB credentials. All other values work as-is for local development.
3. Create a virtual environment: `python3 -m venv venv`
4. Activate: `source venv/bin/activate`
5. Install dependencies: `pip install -r requirements.txt`
6. Start the stack: `docker compose up`

**Fresh start:** If volumes have been wiped, recreate the MinIO bucket before running the pipeline:

`docker exec -it $(docker ps -qf "name=minio") sh -c "mc alias set
local http://localhost:9000 minioadmin minioadmin && mc mb
local/berlin-traffic-raw"`
