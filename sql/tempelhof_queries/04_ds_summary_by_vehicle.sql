SELECT
  datum_iso,
  standort,
  stunde,
  'PKW (Auto)'  AS fahrzeug,
  SUM(pkw)      AS gesamt,
  ROUND(SUM(pkw)::numeric / COUNT(DISTINCT datum_iso), 0) AS tagesdurchschnitt,
  ROUND(AVG(v_pkw)::numeric, 1) AS durchschnittsgeschwindigkeit
FROM traffic_berlin
GROUP BY datum_iso, standort, stunde

UNION ALL
SELECT datum_iso, standort, stunde, 'Fahrrad',
  SUM(fahrrad),
  ROUND(SUM(fahrrad)::numeric / COUNT(DISTINCT datum_iso), 0),
  NULL
FROM traffic_berlin GROUP BY datum_iso, standort, stunde

UNION ALL
SELECT datum_iso, standort, stunde, 'LKW',
  SUM(lkw),
  ROUND(SUM(lkw)::numeric / COUNT(DISTINCT datum_iso), 0),
  ROUND(AVG(v_lkw)::numeric, 1)
FROM traffic_berlin GROUP BY datum_iso, standort, stunde

UNION ALL
SELECT datum_iso, standort, stunde, 'Krad',
  SUM(krad),
  ROUND(SUM(krad)::numeric / COUNT(DISTINCT datum_iso), 0),
  NULL
FROM traffic_berlin GROUP BY datum_iso, standort, stunde

UNION ALL
SELECT datum_iso, standort, stunde, 'LFW (Van)',
  SUM(lfw),
  ROUND(SUM(lfw)::numeric / COUNT(DISTINCT datum_iso), 0),
  NULL
FROM traffic_berlin GROUP BY datum_iso, standort, stunde