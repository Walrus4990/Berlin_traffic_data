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

**What the data shows:** On one residential street converted to a 
Fahrradstraße in late 2024, cycling increased by 53 percent in absolute 
numbers after the conversion. Car traffic decreased by 3 percent. The 
cycling share of total traffic rose from 64 to 74 percent.

## Stack

Hosted on a managed Kubernetes cluster provided by the CityLAB Data Hub
(https://data-hub.berlin/).

* Airflow for orchestration
* MinIO for raw data archiving
* PostgreSQL for cleaned and aggregated data
* Superset for dashboards

## Pipeline

1. Ingest from manufacturer portal into MinIO buckets
2. Archive raw data to MinIO
3. Clean with pandas (deduplication, format standardisation, 
   GPS coordinates added)
4. Join location, deployment and traffic tables
5. Compute indicators (modal split, V85, speed distributions, 
   flow by hour and weekday)
6. Write to PostgreSQL
7. Surface via Superset dashboard and Excel export

## Useful docs

* Data structure and pipeline dataflow: 
  documents/indicator_def_calc_translation.md
* GitHub working instructions: 
  documents/git_clone_branch_pull_instructions.md

## Reuse

The code is modular. Other Bezirke can adapt it for their own 
Dialogdisplay data with minimal changes. If you are interested, 
open an issue or get in touch.
