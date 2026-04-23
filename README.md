# Berlin_traffic_data
LeWagon final project.

## Useful docs
* Info on raw data structure and final pipeline dataflow: [[documents/data_structure]]
* Info on how the final deliverables look like: [[documents/output_description]]
* Indicator definitions [[documents/cleaning_joining_definitions/indicator_def_calc_translation.md]]


## Working instructions

### GitHub
* Working on **GitHub**: [[documents/git_clone_branch_pull_instructions.md]]

### Virtual Environment
* `requirements.txt` — lists packages we needs (e.g. pandas)
* `compose.yml` — defines & runs the infrastructure our pipeline uses
* Instead of each of us manually installing and configuring Superset, Postgres etc.

### How to use requirements.txt:
        1. Navigate to project folder
        2. Create a virtual environment: python3 -m venv venv
        3. Activate the virtual environment: source venv/bin/activate (if you use python 3.8 use: source .venv38/bin/activate)
        You should now see something like: (venv) your-name@machine:project-folder$
        4. Install dependencies from requirements.txt: pip install -r requirements.txt
        5. Verify installation (optional): pip list
        6. Deactivate when done: deactivate
        7. When dependencies change, whoever adds a package should: `pip install <package>`followed by `pip freeze > requirements.txt`and then commit this
        8. Everyone else pulls requirements.txt and runs `pip install -r requirements.txt

### How to use compose.yml
      1. Ensure you have docker and docker compose installed (`docker --version`). If not, deactivate venv and install Docker (`brew install docker` on Mac)
      2. run `docker compose --profile local up` or if on old version `docker-compose --profile local up`
      3. Docker spins up identical containers for everyone. The first time will take time, after that should be fast.
      Note: the local profile is smaller than the full one. Look at compose.yml to compare

### How to use Docker containers
    **Fresh start:** If volumes have been wiped, recreate the MinIO bucket before running the pipeline:
`docker exec -it $(docker ps -qf "name=minio") sh -c "mc alias set local http://localhost:9000 minioadmin minioadmin && mc mb local/berlin-traffic-raw"`

## Background info
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
