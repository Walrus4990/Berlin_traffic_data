shared_pipeline/
├── common/
│   ├── ingest.py          ← functions to pull raw data from sources
│   ├── clean.ipynb        ← data cleaning functions
│   ├── transform.py       ← merge, aggregate, and feature transformations
│   ├── analyze.py         ← compute metrics for dashboards or reports
│   └── publish.py         ← push final tables to DB
│
├── dags/
│   └── dag_tempelhof.py   ← Airflow DAG orchestrating the pipeline
│
├── dashboard/
│   └── ts_dashboard_export.zip   ← Superset dashboard export
│
├── sql/
│   └── ts_queries/
│
├── tests/
│   ├── test_ingest.py
│   ├── test_clean.py
│   └── test_transform.py
│
├── docker-compose.yml
├── .env.example            ← environment template
├── requirements.txt
└── README.md
