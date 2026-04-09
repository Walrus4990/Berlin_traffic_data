SELECT
  stunde,
  SUM(fahrrad) AS bike,
  SUM(pkw) AS car,
  SUM(krad) AS motorbike,
  SUM(van_or_bigger) AS van_or_bigger
FROM tempelhof_traffic_hourly
GROUP BY stunde
ORDER BY stunde