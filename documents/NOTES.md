# NOTES

## To Dos 14 April:
* Please start documenting design decisions in ARD files (see example [[publishing_pipeline_ard]]). LLM can help you with that.
* DAG: we need 2 DAGS,
    1. one for the initial bulk download, it's a one off to get the data into eth city pipeline
    2. TO ORCHESTRATE THE ONGOING PIPELINE:
       1. fetch_missions → compare to bronze_mission in D
       2. Branch A — new mission detected:
          1. Update bronze_mission
          2. fetch_locations → update bronze_location
          3. Update silver_active_mission with new sensor locations
          4. Download new traffic chunks → append to bronze_traffic
          5. Full clean + merge location → append to silver_traffic
          6. Rerun gold aggregations & launch dashboard
       3. Branch B — no new mission:
          1. Download new traffic chunks → append to bronze_traffic
          2. Lookup location from silver_active_mission
          3. Reduced clean + merge → append to silver_traffic
          4. Rerun gold aggregations & launch dashboard


## To Dos 9 April:

* please put all data in the `data` folder, even mock data. Try to follow the bronze, silver, gold structure. : `documents/data_structure/pipeline_data_flow.md`

* please move `notebooks`into `common`, happy to rename `common`into `transformations`
* please split the sensor data files from the two reference files into two different folders (maybe call them sensor_data and reference)


## Suggestion from Lorcan:
* composite key - that links: device, timeframe (from-to), location
