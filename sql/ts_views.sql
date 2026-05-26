-- Berlin Traffic Pipeline Schema
-- Superset Dashboard view

------ v85 displayed when
SQL_V85 = """
CREATE OR REPLACE VIEW gold.big_number_v85 AS
SELECT
    mission_id,
    streetnr,
    date,
    v85
FROM gold.dashboard
"""

------ Modalsplit - needs wide format tabel for Superset display
SQL_MODALSPLIT = """
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
"""

SQL_UEBERSICHT = """
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
"""


--- Simpler ganglinie — bar chart with raw hourly sums (date filter applied by Superset)
SQL_GANGLINIE = """
CREATE OR REPLACE VIEW gold.ganglinie AS
SELECT
    date,
    hour,
    mission_id,
    bicycle,
    car,
    lorry,
    motorbike,
    delivery_van
FROM gold.export
"""
