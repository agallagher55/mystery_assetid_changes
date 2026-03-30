# HRM GIS Scripts — Operational Reference

This document describes the standard patterns for logging, error handling, configuration, and environment setup used across HRM GIS ETL scripts. Intended as a quick-start reference when onboarding new repos or scripts into this ecosystem.

---

## Environment Requirements

All scripts run on **Windows only** with a licensed ArcGIS Desktop or ArcGIS Server installation. There is no Docker, no virtual environment, and no `requirements.txt` — all dependencies (arcpy, pandas, numpy, arcgis) are bundled with ArcGIS.

| Resource | Path |
|----------|------|
| Scripts root | `E:\HRM\Scripts\Python\` |
| SDE connections | `E:\HRM\Scripts\SDE\*.sde` |
| Config file | `E:\HRM\Scripts\Python\config.ini` |
| Logs | Configured per module via `config.ini` `[LOGGING]` → `logDir` |
| Scheduler | Windows Task Scheduler (not defined in repo) |
| Email relay | `mailer.halifax.ca` |
| Portal | `https://gisapp-int.halifax.ca/portal` |
| DB (RW) | `ms-gis-sql-p21/GISRW01` |
| DB (RO) | `ms-gis-sql-p22/GISRO01` |

---

## Configuration

Credentials and environment paths live in `config.ini` on the server — they are **not committed to the repo**.

```ini
[LOGGING]
logDir = D:\Projects\...
serverName = <server-hostname>

[SDEADM_RW]
sdeFile = E:\HRM\Scripts\SDE\prod_RW_sdeadm.sde

[SDEADM_RO]
sdeFile = E:\HRM\Scripts\SDE\prod_RO_sdeadm.sde

[HRM_STG]
sdeFile = ...        # Data Warehouse staging

[HRM_DM]
sdeFile = ...        # Data Mart

[HWADM_RW]
sdeFile = ...        # Halifax Water RW

[HWADM_RO]
sdeFile = ...        # Halifax Water RO

[IMSUSER]
sdeFile = ...        # IMS system

[EMAIL]
recipients = user@halifax.ca,user2@halifax.ca
```

Reading config at the top of every script:

```python
from configparser import ConfigParser

config = ConfigParser()
config.read("E:\\HRM\\Scripts\\Python\\config.ini")

SDEADM_RW = config.get('SDEADM_RW', 'sdeFile')
SDEADM_RO = config.get('SDEADM_RO', 'sdeFile')
```

**Never hardcode credentials or paths that vary by environment.**

---

## Standard Script Header

Every script follows this initialization block, in order:

```python
import sys
import os
import datetime
import time
import traceback
import logging
import arcpy
from configparser import ConfigParser
from HRMutils import setupLog, send_mail, create_fgdb

# --- Directory setup ---
WORKING_DIR = os.path.dirname(sys.path[0])
WD_FOLDER_NAME = os.path.basename(WORKING_DIR)
FILE_NAME = os.path.basename(__file__)
FILE_NAME_BASE = os.path.splitext(FILE_NAME)[0]
SCRATCH_DIR = os.path.join(WORKING_DIR, "Scratch")

# --- Config ---
config = ConfigParser()
config.read("E:\\HRM\\Scripts\\Python\\config.ini")

# --- Logging ---
log_file = os.path.join(
    config.get('LOGGING', 'logDir'),
    WD_FOLDER_NAME,
    f"{str(datetime.date.today())}_{FILE_NAME_BASE}.log"
)
logger = setupLog(log_file)
log_server = config.get('LOGGING', 'serverName')

console_handler = logging.StreamHandler()
log_formatter = logging.Formatter(
    '%(asctime)s | %(levelname)s | FUNCTION: %(funcName)s | Msgs: %(message)s',
    datefmt='%d-%b-%y %H:%M:%S'
)
console_handler.setFormatter(log_formatter)
logger.addHandler(console_handler)

# --- ArcPy environment ---
arcpy.SetLogHistory(False)
arcpy.env.overwriteOutput = True

# --- SDE connections ---
SDEADM_RW = config.get('SDEADM_RW', 'sdeFile')
SDEADM_RO = config.get('SDEADM_RO', 'sdeFile')
```

---

## Logging

Logging is set up via `HRMutils.setupLog()`, which returns a `logging.Logger` writing to a date-stamped file:

```
<logDir>/<module-folder>/<YYYY-MM-DD>_<ScriptName>.log
```

Log entries are written to both the file and the console (via `StreamHandler`).

**Log format:**
```
25-Mar-26 14:03:01 | INFO | FUNCTION: main | Msgs: Processing started
```

**Usage:**
```python
logger.info("Processing started")
logger.warning("No records found for permit type X")
logger.error("Failed to connect to SDE", exc_info=True)
```

Bookend each run with start/end timestamps:

```python
start_time = time.asctime(time.localtime(time.time()))
logger.info(f"Start: {start_time}")

# ... processing ...

end_time = time.asctime(time.localtime(time.time()))
logger.info("-----------------------")
logger.info(f"End: {end_time}")
```

---

## Error Handling

All scripts wrap the main execution body in a bare `except` block that:
1. Captures the full traceback via `sys.exc_info()`
2. Logs the error
3. Sends an email alert
4. Exits

```python
try:
    main()

except:
    tb = sys.exc_info()[2]
    tbinfo = traceback.format_tb(tb)[0]
    pymsg = (
        "PYTHON ERRORS:\nTraceback Info:\n" + tbinfo +
        "\nError Info:\n    " +
        str(sys.exc_info()[0]) + ": " + str(sys.exc_info()[1]) + "\n"
    )
    logger.error(pymsg)

    send_mail(
        to=str(config.get('EMAIL', 'recipients')).split(','),
        subject=f'ERROR - {FILE_NAME_BASE} Failed',
        text=f'{log_server} / {FILE_NAME} \n\n{pymsg}'
    )

    sys.exit()
```

The email subject and body always include the server name and script filename so operators can trace the failure without opening logs.

---

## Email Notifications (`send_mail`)

Provided by `HRMutils.send_mail()`. Sends via unauthenticated SMTP relay at `mailer.halifax.ca`.

```python
send_mail(
    to=["recipient@halifax.ca"],        # list of strings
    subject="Subject line",
    text="Body text",
    files=[],                           # optional list of file paths to attach
    cc=[],
    bcc=[]
)
```

Recipients are stored in `config.ini` under `[EMAIL]` → `recipients` (comma-separated), parsed at runtime:

```python
recipients = str(config.get('EMAIL', 'recipients')).split(',')
```

---

## ArcPy Workspace Pattern

Use `arcpy.EnvManager` as a context manager rather than setting `arcpy.env.workspace` globally:

```python
with arcpy.EnvManager(workspace=SDEADM_RW):
    arcpy.analysis.SpatialJoin(...)
    arcpy.management.Append(...)
```

This prevents the workspace leaking across functions. Always set at module level:

```python
arcpy.SetLogHistory(False)       # Reduces log noise from ArcGIS
arcpy.env.overwriteOutput = True
# arcpy.env.preserveGlobalIds = True  # Only when GlobalIDs must be preserved
```

**Never write to a `_RO` SDE connection.** Read-only replicas are used only as a load target via a controlled truncate/load step.

---

## Shared Utilities (`HRMutils.py`)

Import from the root-level `HRMutils.py`:

```python
from HRMutils import setupLog, send_mail, create_fgdb, remove_duplicates_from_csv
```

| Function | Signature | Purpose |
|----------|-----------|---------|
| `setupLog` | `setupLog(file_name: str) -> Logger` | Creates a file logger with standard formatter |
| `send_mail` | `send_mail(to, subject, text, files=[], cc=[], bcc=[])` | Sends email via SMTP relay |
| `create_fgdb` | `create_fgdb(path, name)` | Creates a file geodatabase |
| `remove_duplicates_from_csv` | `remove_duplicates_from_csv(path)` | De-duplicates a CSV file in place |

> Modules under `node_2/` may carry a local copy of `HRMutils.py` with a subset of these functions. Check the local copy before assuming all utilities are available.

---

## Module Structure Convention

New domain scripts go under `node_2/<domain>/scripts/`. Each module should be self-contained:

```
node_2/<domain>/
└── scripts/
    ├── main_script.py
    ├── HRMutils.py          # copy if shared utils are needed locally
    └── config/
        ├── config.ini       # local overrides / additional sections
        └── config.json      # domain-specific scoring/mapping definitions (if needed)
```

The `config.ini` at `E:\HRM\Scripts\Python\config.ini` is the authoritative source for SDE connections and logging paths. Module-level `config.ini` files extend it with script-specific settings.

---

## QA/QC

There is no automated test suite. Verification is done by:

1. Checking the date-stamped log file for `ERROR` or `WARNING` entries
2. Inspecting `QA_QC/` CSV exports for failed/unlocated records
3. Spot-checking feature class attribute tables in ArcGIS Pro/Desktop

Failed locates and geocoding misses are written to CSV reports in `Reports/` or a shared network path (e.g. `\\msfs202.hrm.halifax.ca\common\...`) depending on the module.

---

## Key Constraints

| Constraint | Detail |
|-----------|--------|
| SQL `IN` clause limit | Max ~2100 items (SQL Server). Chunk larger lists into batches. |
| Workspace globals | Always use `arcpy.EnvManager`, never set `arcpy.env.workspace` without resetting |
| String comparisons | Use `=` not `LIKE` for known exact values |
| Join strategy | Use `JoinField_management` or `SpatialJoin_analysis` — do not simulate joins by iterating cursors |
| Membership checks | Use `set` for O(1) lookup, not `list` |
| Credentials | Always read from `config.ini` — never hardcode |
