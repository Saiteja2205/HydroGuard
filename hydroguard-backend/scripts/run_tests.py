import subprocess
import sys
from pathlib import Path

backend_root = Path(__file__).resolve().parents[1]

result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests", "-q"],
    cwd=str(backend_root),
    capture_output=True,
    text=True,
)

print("STDOUT:", result.stdout)
print("STDERR:", result.stderr[:500] if result.stderr else "")
print("Return code:", result.returncode)
sys.exit(result.returncode)
