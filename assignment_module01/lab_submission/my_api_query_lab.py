from urllib import request
import os
from datetime import datetime
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
URL = "https://portal.c-lockinc.com/api/getemissions?d=visits&fids=453&st=2025-08-01_00:00:00&et=2025-11-01_12:00:00"
Headers = {"Header":("(OwnerID,)FeederID,AnimalName,RFID,StartTime,EndTime,GoodDataDuration,"
"CO2GramsPerDay,CH4GramsPerDay,O2GramsPerDay,H2GramsPerDay,H2SGramsPerDay,"
"AirflowLitersPerSec,AirflowCf,WindSpeedMetersPerSec,WindDirDeg,WindCf,"
"WasInterrupted,InterruptingTags,TempPipeDegreesCelsius,IsPreliminary,RunTime")}
req_obj = request.Request(
    URL,
    data=bytes('token=' + TOK, 'ascii'),
    headers=Headers
)
req = request.urlopen(req_obj)
data = req.read()
data_str = data.decode("ascii")

# Create "downloaded GF files" folder and save raw response as-is
script_dir = os.path.dirname(os.path.abspath(__file__))
output_dir = os.path.join(script_dir, "downloaded GF files")
os.makedirs(output_dir, exist_ok=True)

# Save the raw queried data as-is (no parsing or conversion)
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
filename = f"emissions_visits_fid{FID}_{timestamp}.csv"
output_path = os.path.join(output_dir, filename)
with open(output_path, "w", encoding="ascii") as f:
    f.write(data_str)

print(f"Data saved to: {output_path}")
