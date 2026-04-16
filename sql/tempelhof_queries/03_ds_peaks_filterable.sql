SELECT
  datum_iso,
  standort,
  stunde,
  ROUND(AVG(fahrrad)::numeric, 0) AS avg_fahrrad,
  ROUND(AVG(pkw)::numeric, 0)     AS avg_pkw,
  ROUND(AVG(lkw)::numeric, 0)     AS avg_lkw,
  ROUND(AVG(krad)::numeric, 0)    AS avg_krad,
  ROUND(AVG(kfz)::numeric, 0)     AS avg_kfz
FROM traffic_berlin
GROUP BY datum_iso, standort, stunde
ORDER BY stunde ASC