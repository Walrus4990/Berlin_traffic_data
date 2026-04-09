SELECT
  standort,
  CASE
    WHEN standort='Handjerystraße' AND datum_iso < '2024-05-01' THEN '1_Vorher'
    WHEN standort='Handjerystraße' AND datum_iso >= '2024-05-01' THEN '3_Nachher'
    WHEN standort='Boelckestraße' AND datum_iso < '2023-09-01' THEN '1_Vorher'
    WHEN standort='Boelckestraße' AND datum_iso >= '2023-09-01'
      AND datum_iso < '2024-04-01' THEN '2_Bauzeit'
    WHEN standort='Boelckestraße' AND datum_iso >= '2024-04-01' THEN '3_Nachher'
    ELSE NULL
  END AS phase,
  ROUND(AVG(v85)::numeric, 1) AS v85_avg,
  ROUND(AVG(v_pkw)::numeric, 1) AS v_pkw_avg,
  ROUND(AVG(kfz)::numeric, 0) AS avg_kfz,
  ROUND((AVG(fahrrad)*100.0 / NULLIF(AVG(kfz)+AVG(fahrrad),0))::numeric, 1) AS anteil_rad_pct
FROM traffic_berlin
WHERE standort IN ('Handjerystraße','Boelckestraße')
GROUP BY standort, phase
ORDER BY standort, phase