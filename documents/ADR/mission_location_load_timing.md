# ADR — Mission and Location Record Creation & Ingest Strategy
_Date: 2026-05-07_

## Context

We queried `bronze.mission` and `bronze.location` to understand the timing relationship
between mission creation, location creation, and mission start date. This informs
how we should handle ingest and the merge strategy in silver.

## What We Observed

Three patterns in the data:

1. **Mission and location created together** — the large majority of cases. Engineer
   sets up both records in the same portal session, within minutes of each other.
   `location_created_minus_mission_created` is negative by a few minutes, meaning
   location is entered just before mission.

2. **Location pre-exists mission** — e.g. `54814` Goltzstraße: location created 2017,
   mission created 2020. Location record was already in the portal from a prior deployment.

3. **Admin catch-up outliers** — e.g. `90938`: mission created 45 days after start date,
   location created same day as start. Suggests retroactive data entry.

## What We Know

- `mission_id` is required to query the portal for traffic data (`OrderId` in payload).
  Without a `mission_id` there is no way to fetch sensor data.
- Location data is entered by an engineer at or before deployment. It does not change
  through the life of a mission.
- There is no enforced foreign key between mission and location in the portal — the link
  is the human-entered `location_title` field.

## What We Assume (Not Confirmed)

- A mission cannot exist in the portal without a corresponding location record, because
  the engineer must set up the location before or at the same time as the mission.
  This is a reasonable assumption based on the data but not guaranteed by the portal schema.

## Merge Strategy

- Merge direction: mission → location on `location_title`.
- Since location is created at the same time as or before mission, there will always
  be a matching location row when merging from mission.
- Merge is safe without an existence check on location at merge time.

## Ingest Strategy

- Both `bronze.mission` and `bronze.location` are loaded and appended every weekly run,
  unconditionally and independently of each other.
- `new_mission_detected` flag is retained but its only role is to trigger download of
  traffic files for new mission IDs from the portal. It does not gate location fetch.
- Current logic in `ingest_ref` that gates location fetch on `new_mission_detected`
  must be removed.

## Design Decision

- We assume there will be no NULL coords after the merge. The merge runs once per new
  mission, not every weekly run — rerunning on 39M rows every week is not viable.
- This assumption is supported by the observed data: location is always created at the
  same time as or before mission. We accept this as a design constraint and do not
  build a NULL-handling fallback.


### data
- the below looks at teh difference between location and mission creation and mission start date
- the cols are mission_id,location_title, mission_created_at, mission_start_date, location_created_at, mission_created_minus_start, location_created_minus_mission_created, location_created_minus_start

73698	Goethstraße DD 6428 Fr. Ost	2023-06-26 06:21:08.990	2023-04-15 11:00:00.000	2023-05-30 11:59:21.350	71 days 19:21:08.99	-26 days -18:21:47.64	45 days 00:59:21.35
72976	Goethestraße DD 6429 Fr. West	2023-05-30 11:54:01.513	2023-04-29 11:00:00.000	2023-05-30 11:50:42.850	31 days 00:54:01.513	-00:03:18.663	31 days 00:50:42.85
72975	Lessingstraße DD 7208 Fr. West	2023-05-30 11:42:07.330	2023-04-15 09:00:00.000	2023-05-30 11:40:19.308	45 days 02:42:07.33	-00:01:48.022	45 days 02:40:19.308
72973	Lessingstraße DD 7206 Fr. Ost	2023-05-30 10:52:42.811	2023-04-29 11:00:00.000	2023-05-30 10:41:56.499	30 days 23:52:42.811	-00:10:46.312	30 days 23:41:56.499
71078	Koppelweg - Straße 229  DD 6423	2023-03-19 13:10:04.060	2023-03-18 11:00:00.000	2023-03-19 12:49:36.863	1 day 02:10:04.06	-00:20:27.197	1 day 01:49:36.863
71077	Wehnertstraße  DD 5949	2023-03-19 13:05:42.017	2023-03-18 10:10:00.000	2023-03-19 12:56:51.316	1 day 02:55:42.017	-00:08:50.701	1 day 02:46:51.316
69502	Eisenacher Straße DD 7206	2022-12-09 07:36:18.870	2022-12-07 08:00:00.000	2022-12-09 07:33:59.688	1 day 23:36:18.87	-00:02:19.182	1 day 23:33:59.688
69501	Goltzstraße  DD 7208	2022-12-09 07:35:17.176	2022-12-07 08:00:00.000	2022-12-09 07:29:44.647	1 day 23:35:17.176	-00:05:32.529	1 day 23:29:44.647
69481	Manfred-von-Richthofen Straße  Fr. Süd  DD7207	2022-12-08 09:07:53.687	2022-12-07 08:00:00.000	2022-12-08 08:56:10.163	1 day 01:07:53.687	-00:11:43.524	1 day 00:56:10.163
69478	Manfred-von-Richthofen Straße  Fr. Nord  DD7205	2022-12-08 08:50:42.076	2022-12-07 08:00:00.000	2022-12-08 08:46:18.978	1 day 00:50:42.076	-00:04:23.098	1 day 00:46:18.978
43114	Waldsassener Straße DD 6428	2022-03-16 06:55:14.983	2022-03-14 12:22:00.000	2022-03-16 06:54:20.280	1 day 18:33:14.983	-00:00:54.703	1 day 18:32:20.28
40714	Ebersstraße Nr.17  DD 6425	2022-02-28 13:36:37.343	2022-02-26 12:22:00.000	2022-02-28 13:33:55.867	2 days 01:14:37.343	-00:02:41.476	2 days 01:11:55.867
40715	Ebersstraße Nr. 76   DD 6427	2022-02-28 13:27:57.977	2022-02-26 11:00:00.000	2022-02-28 13:24:39.947	2 days 02:27:57.977	-00:03:18.03	2 days 02:24:39.947
40716	Handjerystraße Nr. 6-9 DD 6426	2022-02-28 13:18:51.320	2022-02-26 12:22:00.000	2022-02-28 13:17:23.893	2 days 00:56:51.32	-00:01:27.427	2 days 00:55:23.893
40718	Handjerystraße Nr. 6-9 DD 6424	2022-02-28 13:11:20.297	2022-02-26 14:00:00.000	2022-02-28 13:07:40.020	1 day 23:11:20.297	-00:03:40.277	1 day 23:07:40.02
40688	Friedenstraße DD 6423	2022-02-28 12:52:27.603	2022-02-25 12:00:00.000	2022-02-28 12:51:05.117	3 days 00:52:27.603	-00:01:22.486	3 days 00:51:05.117
40687	Bahnstraße Nr. 10  DD 5949	2022-02-28 12:26:39.890	2022-02-25 13:00:00.000	2022-02-28 12:20:44.233	2 days 23:26:39.89	-00:05:55.657	2 days 23:20:44.233
40671	Albanstraße Nr. 23  DD 6429	2022-02-28 12:23:57.410	2022-01-28 12:00:00.000	2022-02-28 12:22:22.957	31 days 00:23:57.41	-00:01:34.453	31 days 00:22:22.957
40963	Körtingstraße  Nr. 42           DD 5953	2021-11-14 10:37:18.797	2021-11-13 14:00:00.000	2021-11-14 09:49:23.843	20:37:18.797	-00:47:54.954	19:49:23.843
40964	Körtingstraße  Nr. 45           G-Nr.: 5952	2021-11-14 10:36:18.577	2021-11-13 13:00:00.000	2021-11-14 10:08:47.820	21:36:18.577	-00:27:30.757	21:08:47.82
45098	Boelkestraße Nr. 65 Fr. Nord DD 5950	2021-05-05 08:12:33.113	2021-05-04 09:10:00.000	2021-05-05 08:03:45.517	23:02:33.113	-00:08:47.596	22:53:45.517
54814	Goltzstraße Nr. 45       G.-Nr.:  4848	2020-04-15 13:30:36.347	2020-03-18 09:39:00.000	2017-07-25 12:55:44.000	28 days 03:51:36.347	-995 days -00:34:52.347	-966 days -20:43:16
32040	Eisenacher Straße Nr. 106    DD 55	2017-07-25 13:21:45.000	2020-03-23 23:00:00.000	2017-07-25 12:51:31.000	-972 days -09:38:15	-00:30:14	-972 days -10:08:29
