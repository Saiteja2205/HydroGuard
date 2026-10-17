import sqlite3
from pathlib import Path

backend_root = Path(__file__).resolve().parents[1]
db_path = backend_root / "data" / "hydroguard.db"

conn = sqlite3.connect(str(db_path))
c = conn.cursor()

print("=== NODES ===")
c.execute("SELECT node_id, status FROM nodes ORDER BY node_id")
for r in c.fetchall():
    print(r)

print("\n=== READINGS BY NODE AND SOURCE ===")
c.execute("SELECT node_id, source, COUNT(*) FROM sensor_readings GROUP BY node_id, source ORDER BY node_id, source")
for r in c.fetchall():
    print(r)

print("\n=== SIMULATED READINGS PER NODE ===")
c.execute("SELECT node_id, source, COUNT(*) FROM sensor_readings WHERE source LIKE '%SIMULATED%' GROUP BY node_id")
for r in c.fetchall():
    print(r)

print("\n=== node_overhead_a READINGS ===")
c.execute("SELECT node_id, timestamp, ph, tds, turbidity, temperature, source FROM sensor_readings WHERE node_id = 'node_overhead_a' ORDER BY timestamp DESC LIMIT 3")
for r in c.fetchall():
    print(r)

print("\n=== node_overhead_a SOURCES ===")
c.execute("SELECT DISTINCT source FROM sensor_readings WHERE node_id = 'node_overhead_a'")
for r in c.fetchall():
    print(r)

conn.close()
