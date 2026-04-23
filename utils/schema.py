# All schema info in one place

# Column mapping: ingest file field names → bronze schema
#
# The DDweb ingest scripts return the raw portal API field names.
MISSION_RENAME = {
    "Id":            "mission_id",
    "Created":       "created_at",
    "FromDate":      "start_date",
    "ToDate":        "end_date",
    "Description":   "description",
    "LocationTitle": "location_title", # join key
    "City":          "city",
    "Street":        "street",
    "StreetNumber":  "street_number",
    "Zipcode":       "zipcode",
    "DeviceNumber":  "device_id",      # primary identifier
    "DeviceType":    "device_type",
}

LOCATION_RENAME = {
    "Id":                "location_id",
    "Created":           "created_at",
    "Description":       "description",
    "LocationTitle":     "location_title", # join key
    "Street":            "street",
    "StreetNumber":      "street_number",
    "Zipcode":           "zipcode",
    "City":              "city",
    "DrivingDirection":  "driving_direction",
    "OppositeDirection": "opposite_direction",
    "PosUserLat":        "lat",
    "PosUserLng":        "lon",
}

# Traffic Excel columns that are always zero — dropped before loading to bronze.
TRAFFIC_COLS_DROP = [
    "Schall (dB)", "Abstand (cm)", "Fahrspur",
    "Geschwindigkeit (km/h)", "Richtung",
]

TRAFFIC_RENAME = {
    "Geräte-ID":                        "device_id",
    "Datum":                            "date_raw",
    "Eintrittsgeschwindigkeit (km/h)":  "speed_entry",
    "Austrittsgeschwindigkeit (km/h)":  "speed_exit",
    "Länge (dm)":                       "length_dm",
    "Klasse":                           "vehicle_class",
    "Fahrzeugklassen-Bezeichnung":      "vehicle_class_label",
}
