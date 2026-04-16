SELECT
  datum_iso,
  standort,
  stunde,
  'PKW (Auto)'  AS fahrzeug, SUM(pkw)     AS anzahl
FROM traffic_berlin
GROUP BY datum_iso, standort, stunde

UNION ALL
SELECT datum_iso, standort, stunde, 'Fahrrad',   SUM(fahrrad) FROM traffic_berlin GROUP BY datum_iso, standort, stunde
UNION ALL
SELECT datum_iso, standort, stunde, 'LKW',       SUM(lkw)     FROM traffic_berlin GROUP BY datum_iso, standort, stunde
UNION ALL
SELECT datum_iso, standort, stunde, 'Krad',      SUM(krad)    FROM traffic_berlin GROUP BY datum_iso, standort, stunde
UNION ALL
SELECT datum_iso, standort, stunde, 'LFW (Van)', SUM(lfw)     FROM traffic_berlin GROUP BY datum_iso, standort, stunde