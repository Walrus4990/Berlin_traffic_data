# ARD: Data Publishing Pipeline — Final Stage

## 1. Linked resource (MinIO) vs managed resource (CKAN filestore)
**Context:** The city's CKAN instance does not host data, just links to it.
**Decision:** CityLab hosts the file in a MinIO bucket; CKAN holds only a pointer URL.
**Consequences:** CKAN cannot verify file integrity or serve download stats; MinIO is the authoritative store.

## 2. Metadata updated once, not weekly
**Context:** All descriptive metadata (title, owner, license etc.) is set at first registration and does not change.
**Decision:** Only `last_modified` is patched weekly; all other fields remain static.
**Consequences:** Any metadata correction requires a manual intervention on the Berlin Open Data portal.

## 3. No validation at publish step
**Context:** Data quality is enforced by upstream pipeline tasks.
**Decision:** This task assumes a valid file if the MinIO export task succeeded.
**Consequences:** A corrupted but successfully written file would be published without detection.

## 4. Airflow task chaining for sequencing
**Context:** The CKAN update must only fire after a successful MinIO write.
**Decision:** Standard Airflow upstream dependency (`>>`) rather than explicit file checks.
**Consequences:** Simple and maintainable; failure handling delegated to Airflow's retry mechanism.

## 5. `resource_patch` over `resource_update`
**Context:** Only one field changes weekly.
**Decision:** Use `resource_patch` to send only the updated date field.
**Consequences:** Reduces risk of accidentally overwriting static metadata fields; simpler payload.
