import json
import urllib.request
import urllib.error
import urllib.parse
import os
import sys

BASE_URL = "http://127.0.0.1:8000"

dev_token = ""
env_file = os.path.join(os.path.dirname(__file__), "..", "..", ".dev-auth.env")
if os.path.exists(env_file):
    with open(env_file, "r", encoding="utf-8-sig") as f:
        for line in f:
            if line.startswith("HYDROGUARD_DEV_API_TOKEN="):
                dev_token = line.split("=", 1)[1].strip()
                break

dev_headers = {
    "X-HydroGuard-Development-Token": dev_token,
    "X-HydroGuard-Development-Role": "STUDENT",
    "X-HydroGuard-Development-Uid": "demo.student@hydroguard.local"
}

def get(path, headers=None):
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, resp.read().decode('utf-8')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8')
    except Exception as e:
        return 0, str(e)

def post(path, data=None, headers=None):
    url = f"{BASE_URL}{path}"
    body = json.dumps(data).encode('utf-8') if data is not None else b"{}"
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=body, headers=h)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, resp.read().decode('utf-8')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8')
    except Exception as e:
        return 0, str(e)

print("=== 1. Health Status ===")
status, body = get("/api/v1/health")
print(f"Health: status={status}")

print("\n=== 2. ThingSpeak Latest Reading ===")
status, body = get("/api/v1/thingspeak/latest", headers=dev_headers)
print(f"ThingSpeak Latest: status={status}")
if status == 200:
    data = json.loads(body)
    print("  Entry ID:", data.get("entry_id"))
    print("  Values:", data.get("values"))
    print("  RGB:", data.get("rgb"))
    print("  Timestamp:", data.get("timestamp"))

print("\n=== 3. ThingSpeak Forecast Generation ===")
status, body = get("/api/v1/thingspeak/forecast", headers=dev_headers)
print(f"ThingSpeak Forecast: status={status}")
if status == 200:
    data = json.loads(body)
    print("  Keys:", list(data.keys()))
    if "forecast" in data:
        fc = data["forecast"]
        print("  Forecast model:", fc.get("model_name"))
        print("  Points count:", len(fc.get("points", [])))
        if fc.get("points"):
            print("  First point:", fc.get("points")[0])
    elif "detail" in data:
        print("  Detail:", data.get("detail"))
    else:
        print("  Raw:", str(data)[:200])

print("\n=== 4. Notices (Authenticated) ===")
status, body = get("/api/v1/hostel/notices", headers=dev_headers)
print(f"Notices: status={status}")
if status == 200:
    data = json.loads(body)
    count = len(data) if isinstance(data, list) else len(data.get("notices", []))
    print("  Count:", count)

print("\n=== 5. Issue Submission ===")
issue_payload = {
    "category": "Water",
    "location": "Hostel Block B, 3rd floor",
    "description": "Pressure dropped significantly during evening hours.",
    "severity": "MEDIUM"
}
status, body = post("/api/v1/hostel/issues", issue_payload, headers=dev_headers)
print(f"Issue Submission: status={status}")
if status in (200, 201):
    issue_data = json.loads(body)
    created_issue_id = issue_data.get("id")
    print("  Created issue id:", created_issue_id)
    print("  Status:", issue_data.get("status"))
    print("  Severity:", issue_data.get("severity"))
else:
    print("  Error:", body)

print("\n=== 6. My Issues List ===")
status, body = get("/api/v1/hostel/issues", headers=dev_headers)
print(f"My Issues: status={status}")
if status == 200:
    issues = json.loads(body)
    print("  User issues count:", len(issues) if isinstance(issues, list) else "unknown")

print("\n=== 7. Hostel Feedback Submission ===")
feedback_payload = {
    "rating": 5,
    "category": "Water",
    "comment": "Water clarity and taste have improved noticeably this week."
}
status, body = post("/api/v1/hostel/feedback", feedback_payload, headers=dev_headers)
print(f"Feedback Submission: status={status}")
if status in (200, 201):
    print("  Feedback recorded id:", json.loads(body).get("id"))
else:
    print("  Error:", body)

print("\n=== 8. Lost and Found Photo Upload & Item Creation ===")
# 1x1 transparent PNG bytes
png_1x1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
    b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)
url = f"{BASE_URL}/api/v1/hostel/lost-found/photos"
req = urllib.request.Request(url, data=png_1x1, headers={"Content-Type": "image/png", **dev_headers})
photo_url = None
try:
    with urllib.request.urlopen(req) as resp:
        print(f"Photo Upload: status={resp.status}")
        upload_res = json.loads(resp.read().decode('utf-8'))
        photo_url = upload_res.get("image_url")
        print("  Photo URL:", photo_url)
except urllib.error.HTTPError as e:
    print(f"Photo Upload Error: status={e.code}, body={e.read().decode('utf-8')}")
except Exception as e:
    print(f"Photo Upload Exception: {e}")

if photo_url:
    lf_payload = {
        "kind": "LOST",
        "title": "Water bottle left near cooler",
        "description": "Blue stainless steel bottle left on the 2nd floor cooler ledge.",
        "category": "Other",
        "image_url": photo_url,
        "location": "Block B 2nd floor water cooler",
        "item_date": "2026-10-17T10:00:00Z"
    }
    status, body = post("/api/v1/hostel/lost-found", lf_payload, headers=dev_headers)
    print(f"Lost & Found Item Creation: status={status}")
    if status in (200, 201):
        item_data = json.loads(body)
        print("  Created item ID:", item_data.get("id"))
        print("  Title:", item_data.get("title"))
    else:
        print("  Error:", body)

print("\n=== 9. Node Listing ===")
status, body = get("/api/v1/nodes", headers=dev_headers)
print(f"Nodes: status={status}")
first_node_id = None
if status == 200:
    nodes_data = json.loads(body)
    nodes = nodes_data.get("nodes", []) if isinstance(nodes_data, dict) else nodes_data
    print("  Nodes count:", len(nodes))
    for n in nodes:
        print(f"    Node: id={n.get('node_id')}, name={n.get('name')}, status={n.get('status')}")
    if nodes:
        first_node_id = nodes[0].get("node_id")

print("\n=== 10. Thresholds ===")
status, body = get("/api/v1/thresholds", headers=dev_headers)
print(f"Thresholds: status={status}")
if status == 200:
    th = json.loads(body)
    print("  Thresholds keys:", list(th.keys()) if isinstance(th, dict) else len(th))

target_node = first_node_id or "tank_main"
print(f"\n=== 11. Alerts for {target_node} ===")
status, body = get(f"/api/v1/nodes/{target_node}/alerts", headers=dev_headers)
print(f"Alerts for {target_node}: status={status}")
if status == 200:
    al = json.loads(body)
    print("  Alerts count:", len(al) if isinstance(al, list) else len(al.get("alerts", [])))

print("\n=== 12. Research CSV Export (Admin) ===")
admin_headers = {
    "X-HydroGuard-Development-Token": dev_token,
    "X-HydroGuard-Development-Role": "ADMIN",
    "X-HydroGuard-Development-Uid": "demo.admin@hydroguard.local"
}
status, body = get("/api/v1/research/export.csv", headers=admin_headers)
print(f"Research CSV Export: status={status}")
if status == 200:
    lines = body.strip().split("\n")
    print(f"  CSV Header: {lines[0][:80]}...")
    print(f"  Total CSV lines: {len(lines)}")
else:
    print("  Error:", body[:200])
