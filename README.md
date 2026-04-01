# Berlin_traffic_data
LeWagon final project.

**The problem:** Berlin local authority has traffic sensor data it is not using.  

**Goal:**  build infrastructure to make data useable (agg dataset & dashboard). The local authority needs info on Modal split, average speed by vehicle type, V85, hourly flow per direction, and time-series trend lines. They currently uses the sensors  for traffic calming, school route safety, bicycle street assessments, and responding to citizen complaints about rat-running.

**The data**: sensors are commercial off-the-shelf vehicle counters (27-41 units) that record vehicle counts, speeds, and type splits (car/truck) at hourly resolution, roughly 2.5M rows/month total.

The sensors are mobile, not fixed. They get moved around. Each device has a permanent ID but can appear at different locations over time. Typically two devices per location (one per direction), except on one-way streets. 

**Stack:** 
The local authority relies on a central city stack. Hosted on a managed Kubernetes cluster provided by a public-sector innovation lab.  (https://data-hub.berlin/). Need to use tools in that stack.
* Airflow for orchestration, 
* MinIO for raw data archiving, 
* PostgreSQL for cleaned/aggregated data, 
* Superset for dashboards. 

**Our work/the pipeline**
Need to build sandbox environemnt to mirror gvt stack. Use `.env` switching to achive zero code changes on deployment.

**Pipeline steps:** 
1. ingest (method TBD — biggest gap, worst case from folder)
2. archive raw to MinIO
3. clean with pandas
4. join location, deployment & traffic tables (maybe write to SQL DB?)
5. compute indicators (modal split, V85, speed distributions, flow by hour)
6. write to PostgreSQL
7. export to open data portal https://daten.berlin.de/datensaetze
8. alert email on failure.
