from etl.ddweb_auth import DDWebSession

session = DDWebSession()
session.ensure_authenticated()

response = session.session.post("https://ddweb.topo-web.com/Mission/ReadDataAjax")
print(response.status_code)
print(response.text[:500])
