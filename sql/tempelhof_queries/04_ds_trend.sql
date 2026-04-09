SELECT
  datum_iso,
  SUM(kfz) AS kfz_day,
  SUM(fahrrad) AS fahrrad_day,
  SUM(pkw) AS pkw_day
FROM traffic_berlin
GROUP BY datum_iso
ORDER BY datum_iso ASC