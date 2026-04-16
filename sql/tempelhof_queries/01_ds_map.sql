SELECT
  datum_iso,
  stunde,
  geraet_id,
  standort,
  AVG(latitude)  AS lat,
  AVG(longitude) AS lon,
  ROUND(AVG(v85)::numeric, 1)    AS v85_avg,
  ROUND(SUM(kfz)::numeric / COUNT(DISTINCT datum_iso), 0) AS kfz_pro_tag,
  ROUND((AVG(fahrrad)*100.0 / NULLIF(AVG(kfz)+AVG(fahrrad),0))::numeric, 1) AS anteil_rad
FROM traffic_berlin
GROUP BY datum_iso, stunde, geraet_id, standort