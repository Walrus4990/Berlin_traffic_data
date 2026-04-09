SELECT
  'PKW (Auto)' AS fahrzeug, SUM(pkw) AS anzahl
FROM traffic_berlin
UNION ALL
SELECT 'Fahrrad', SUM(fahrrad) FROM traffic_berlin
UNION ALL
SELECT 'LKW', SUM(lkw) FROM traffic_berlin
UNION ALL
SELECT 'Krad', SUM(krad) FROM traffic_berlin
UNION ALL
SELECT 'LFW (Van)', SUM(lfw) FROM traffic_berlin