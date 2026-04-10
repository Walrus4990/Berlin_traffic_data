SELECT
  standort, geraet_id,
  ROUND(AVG(v85)::numeric, 1) AS v85_avg,
  ROUND(AVG(v_pkw)::numeric, 1) AS v_pkw_avg,
  SUM(kfz) AS kfz_total,
  ROUND((SUM(kfz)::numeric / COUNT(DISTINCT datum_iso)), 0) AS kfz_pro_tag,
  ROUND((SUM(fahrrad)*100.0 / NULLIF(SUM(kfz)+SUM(fahrrad),0))::numeric, 1) AS anteil_rad_pct
FROM traffic_berlin
GROUP BY standort, geraet_id
ORDER BY v85_avg DESC