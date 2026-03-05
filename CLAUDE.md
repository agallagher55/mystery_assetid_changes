# CLAUDE.md — AI Assistant Context for mystery_assetid_changes

This file provides context for AI assistants (Claude and others) working in this repository.

---

## Project Summary

This repository documents a GIS data quality investigation into unexpectedly changing Asset IDs (`TR_ID`, `ASSETID`) in the enterprise geodatabase feature class `[GISRW01].[sdeadm].[TRN_SECTRAV]` (Trails/Sectrav) at Halifax Regional Municipality (HRM).

The same problem has been observed on Bus Pads and potentially other layers.

---

## Repository Contents

| File | Purpose |
|------|---------|
| `TROUBLESHOOTING.md` | Primary investigation and remediation plan |
| `README.md` | Project overview and quick-start guide |
| `Monthly Submission Comments - 20260227.xlsx` | Supporting data: ID mapping table (Original_ID → New_ID) and submission notes |

---

## Domain Context

### Technology Stack

- **GIS Client:** ArcGIS Pro 3.3.5
- **Database:** SQL Server enterprise geodatabase (read-write connection), managed via Esri ArcGIS Enterprise (SDE)
- **Feature Class:** `[GISRW01].[sdeadm].[TRN_SECTRAV]` — trail segments with archiving enabled
- **Sequence:** `sdeadm.sectravid` — generates numeric portion of TR_ID values
- **Attribute Rules:** Arcade-based, Insert-only, auto-generate `TR_ID` and `ASSETID`

### Key Tables

| Table | Description |
|-------|-------------|
| `sdeadm.TRN_SECTRAV` | Live trail segment features |
| `sdeadm.TRN_SECTRAV_H` | Archive history table (auto-maintained by ArcGIS archiving) |
| `sde.sde_sequences` | SDE sequence registry (holds current value for `sectravid`) |
| `sde.SDE_VERSIONS` | Geodatabase version registry |
| `sde.SDE_REPLICAS` | Replica/checkout registry |
| `sde.GDB_ITEMS` | Geodatabase item registry (attribute rules, sequences, domains) |
| `sde.table_registry` | Feature class registration info (versioning type, row ID column) |

### Key Fields

| Field | Description |
|-------|-------------|
| `TR_ID` | Primary business key (e.g., `TR7141890`). Auto-generated on Insert by attribute rule. |
| `ASSETID` | Asset management key — mirrors `TR_ID` at time of insert. |
| `OBJECTID` | Database row ID. Changes on every delete+insert — **not a stable join key**. |
| `GlobalID` | GUID — also regenerated on delete+insert. Check if used in related tables. |

---

## Investigation Status

- **Root cause hypothesis:** Consultant reconciliation workflow is performing delete+insert (e.g., via `Append` tool or full reload) rather than in-place updates, causing Insert-only attribute rules to fire and assign new IDs.
- **Evidence:** ID gap of ~6 million sequence increments; archive table shows deletions; known mapping of 30+ affected features.
- **Status:** Active investigation — root cause not yet confirmed. See `TROUBLESHOOTING.md` for next steps.

---

## Working Conventions for AI Assistants

- All SQL in this repo targets **SQL Server** (T-SQL syntax).
- Arcade expressions follow **ArcGIS Arcade** syntax (Esri's expression language).
- Python scripts use **ArcPy** (ArcGIS Pro 3.3.5).
- When suggesting queries, use the table/schema names above exactly (`sdeadm.TRN_SECTRAV`, etc.).
- Do not recommend truncate+reload or Append-based workflows for this feature class.
- `OBJECTID` is NOT a stable join key across delete+insert cycles; prefer `TR_ID`, `GlobalID`, or spatial geometry.
- All remediation scripts should be run inside a versioned edit session and reviewed before posting to the Default version.
