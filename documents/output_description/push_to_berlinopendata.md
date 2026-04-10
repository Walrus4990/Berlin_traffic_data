# Data Publishing Pipeline (Final Stage)

**Context:** this task sits at the tail of the data pipeline. the upstream task exports the finalised "gold" dataset as an .xlsx to a MinIO bucket. this task handles the final publishing step: ensuring the dataset is publicly accessible and that the CKAN open data portal reflects the latest update date. no data transformation happens here.

1. Configure MinIO bucket policy to expose the gold .xlsx via a stable public URL (likely config, not code — confirm with infra)
2. Manually register the dataset and resource on the CKAN portal once (human step) — record the resource ID
3. Write an Airflow task that POSTs to https://your-portal.gov/api/3/action/resource_patch with the resource ID and current timestamp
4. Ensure the task checks response["success"] and raises an explicit failure if false (HTTP 200 alone is not sufficient)
5. Store the CKAN API key securely (Airflow secret/variable, not hardcoded)
6. In the Airflow DAG definition, set this task as dependent on the MinIO export task — meaning it only runs if that task completed successfully. This is done with a single line in the DAG: minio_export_task >> ckan_update_task
