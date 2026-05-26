import os, requests

base = "http://localhost:8089"
session = requests.Session()

# login
r = session.post(f"{base}/api/v1/security/login", json={
    "username": "admin",
    "password": "admin",
    "provider": "db"
})
token = r.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# csrf
csrf = session.get(f"{base}/api/v1/security/csrf_token/", headers=headers)
headers["X-CSRFToken"] = csrf.json()["result"]
headers["Referer"] = base

# import with overwrite
with open("dashboard/dashboard_export.zip", "rb") as f:
    resp = session.post(
        f"{base}/api/v1/dashboard/import/",
        headers=headers,
        files={"formData": f},
        data={"overwrite": "true"}
    )
    print(resp.status_code, resp.json())
