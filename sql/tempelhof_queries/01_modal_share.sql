SELECT 'Bike' AS mode, SUM(fahrrad) AS total FROM tempelhof_traffic_hourly
UNION ALL
SELECT 'Car' AS mode, SUM(pkw) AS total FROM tempelhof_traffic_hourly
UNION ALL
SELECT 'Motorbike' AS mode, SUM(krad) AS total FROM tempelhof_traffic_hourly
UNION ALL
SELECT 'Van or bigger' AS mode, SUM(van_or_bigger) AS total FROM tempelhof_traffic_hourly