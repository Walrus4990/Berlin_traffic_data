SELECT
  standort,
  AVG(latitude) AS latitude,
  AVG(longitude) AS longitude,
  SUM(kfz) AS motorised_total,
  SUM(fahrrad) AS bike_total,
  AVG(v85) AS avg_v85
FROM tempelhof_traffic_hourly
GROUP BY standort