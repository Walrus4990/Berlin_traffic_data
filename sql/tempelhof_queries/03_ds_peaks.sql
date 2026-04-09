SELECT
  stunde,
  ROUND(AVG(fahrrad)::numeric, 0) AS avg_fahrrad,
  ROUND(AVG(pkw)::numeric, 0) AS avg_pkw,
  ROUND(AVG(lkw)::numeric, 0) AS avg_lkw,
  ROUND(AVG(kfz)::numeric, 0) AS avg_kfz
FROM traffic_berlin
GROUP BY stunde
ORDER BY stunde ASC