-- Berlin Traffic Pipeline Schema
-- Superset Dashboard view

------ map
SELECT
  date,
  mission_id,
  streetnr,
  lat,
  lon,
  ROUND(AVG(v85)::numeric, 0)    AS "V85",
  ROUND(AVG(car)::numeric, 0) AS "Autos pro Tag",
  ROUND((AVG(bicycle)::numeric, 0) AS "Fahrräder"
FROM gold.dashboard
GROUP BY date, mission_id, streetnr

------ v85 displayed when

CREATE OR REPLACE VIEW gold.big_number_v85 AS
SELECT
    mission_id,
    streetnr,
    date,
    v85
FROM gold.dashboard


------ Modalsplit - needs wide format tabel for Superset display

CREATE OR REPLACE VIEW gold.modalsplit AS
SELECT date, mission_id, streetnr, 'Auto' AS metric, car AS value FROM gold.dashboard
UNION ALL
SELECT date, mission_id, streetnr, 'Fahrrad' AS metric, bicycle AS value FROM gold.dashboard
UNION ALL
SELECT date, mission_id, streetnr, 'LKW' AS metric, lorry AS value FROM gold.dashboard
UNION ALL
SELECT date, mission_id, streetnr, 'Motorrad' AS metric, motorbike AS value FROM gold.dashboard
UNION ALL
SELECT date, mission_id, streetnr, 'Lieferwagen' AS metric, delivery_van AS value FROM gold.dashboard
UNION ALL
SELECT date, mission_id, streetnr, 'Sonstige' AS metric, other AS value FROM gold.dashboard;

---------- overview table
-- Converts wide table to long format for table chart
-- Includes daily average and speed per vehicle type where available

CREATE OR REPLACE VIEW gold.summary_table AS
SELECT 1 AS sort_order, 'Auto' AS "Fahrzeug", SUM(car) AS "insgesamt", AVG(car) AS "Durchschnitt (tgl.)", AVG(v_car) AS "Geschwindigkeit" FROM gold.dashboard WHERE 1=1
UNION ALL
SELECT 2, 'Fahrrad', SUM(bicycle), AVG(bicycle), NULL AS "Geschwindigkeit" FROM gold.dashboard WHERE 1=1
UNION ALL
SELECT 3, 'Lieferwagen', SUM(delivery_van), AVG(delivery_van), AVG(v_delivery_van) FROM gold.dashboard WHERE 1=1
UNION ALL
SELECT 4, 'LKW', SUM(lorry), AVG(lorry), AVG(v_lorry) FROM gold.dashboard WHERE 1=1
UNION ALL
SELECT 5, 'Motorrad', SUM(motorbike), AVG(motorbike), AVG(v_motorbike) FROM gold.dashboard WHERE 1=1
UNION ALL
SELECT 6, 'Sonstige', SUM(other), AVG(other), AVG(v_other) FROM gold.dashboard WHERE 1=1
ORDER BY sort_order;


-----Ganglinien - bar chart average number count for in each hour

CREATE OR REPLACE VIEW gold.ganglinie AS
SELECT
    hour,
    AVG(bicycle) as "Fahrrad",
    AVG(car) AS "Auto",
    AVG(lorry) AS "LKW",
    AVG(motorbike) AS "Motorrad",
    AVG(delivery_van) AS "Lieferwagen"
FROM gold.export
WHERE date >= [filter_start] AND date <= [filter_end]
GROUP BY hour
