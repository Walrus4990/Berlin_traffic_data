SELECT 'Bike' AS vehicle,
       SUM(fahrrad) AS total,
       ROUND(AVG(fahrrad), 1) AS average_number_per_hour,
       NULL AS average_speed_kmh
FROM tempelhof_traffic_hourly
UNION ALL
SELECT 'Car',
       SUM(pkw),
       ROUND(AVG(pkw), 1),
       ROUND(AVG(v_pkw), 1)
FROM tempelhof_traffic_hourly
UNION ALL
SELECT 'Motorbike',
       SUM(krad),
       ROUND(AVG(krad), 1),
       ROUND(AVG(v_kfz), 1)
FROM tempelhof_traffic_hourly
UNION ALL
SELECT 'Van or bigger',
       SUM(van_or_bigger),
       ROUND(AVG(van_or_bigger), 1),
       ROUND(AVG(v_lkw), 1)
FROM tempelhof_traffic_hourly