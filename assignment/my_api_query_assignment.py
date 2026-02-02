from urllib import request
from urllib import parse
import os
from dotenv import load_dotenv

# --- Load credentials from environment ---
load_dotenv()  # Load .env file so os.getenv() can read CLOCK_USER and CLOCK_PASS
USER = os.getenv("CLOCK_USER")
PASS = os.getenv("CLOCK_PASS")
FID  = "453"

# First Authenticate to receive token:
req = request.urlopen(
    "https://portal.c-lockinc.com/api/login",
    bytes('user=' + USER + '&pass=' + PASS, 'ascii')
)
TOK = req.read().decode('ascii').strip()

# Now get data using the login token
URL = "https://portal.c-lockinc.com/api/workbook?d=list&fids=453"
Headers = {
    "Header": "WorkbookID,SystemIDs,Filename,FileSize,AddedTime,StartDate,StopDate,Days,Status,Permanent"
}
req_obj = request.Request(
    URL,
    data=bytes('token=' + TOK, 'ascii'),
    headers=Headers
)
req = request.urlopen(req_obj)
data = req.read()
data_str = data.decode("ascii")

# Output the data
print(data_str)

# Save to CSV in the same folder as this script
script_dir = os.path.dirname(os.path.abspath(__file__))
output_path = os.path.join(script_dir, "workbook_data.csv")
with open(output_path, "w", encoding="utf-8", newline="") as f:
    f.write(data_str)
print(f"\nData saved to {output_path}")
