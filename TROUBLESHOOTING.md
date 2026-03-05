# Troubleshooting Plan: Changing Asset IDs in `[GISRW01].[sdeadm].[TRN_SECTRAV]`

**Prepared:** 2026-03-05
**Issue:** `TR_ID` and `ASSETID` fields are changing on existing features after consultant data is reconciled back into the enterprise geodatabase.
**Database:** `[GISRW01].[sdeadm].[TRN_SECTRAV]` (archiving enabled) — SQL Server enterprise geodatabase, read-write connection
**GIS Client:** ArcGIS Pro 3.3.5
**Also affected:** Bus pads and other layers using the same or similar attribute rules (see Section 11)

---

## 1. Understanding the System Before Debugging

### 1.1 Attribute Rule Summary

| Rule | Field | Expression | Trigger |
|------|-------|------------|---------|
| TRN_sectrav - TR_ID - Generate ID | `TR_ID` | `'TR' + NextSequenceValue('sdeadm.sectravid')` | Insert only |
| TRN_sectrav - ASSETID - Generate ID | `ASSETID` | `$feature.TR_ID` | Insert only |

**Critical observation:** Both rules fire on **INSERT only**. This means `TR_ID` and `ASSETID` should never change on an existing row — unless a row is being **deleted and re-inserted** instead of updated. The fact that IDs are changing strongly implies a delete + re-insert is occurring somewhere in the workflow.

**Secondary observation:** The ID range jumped from `TR100xxxx` → `TR714xxxx`. This is a gap of ~6 million sequence increments, suggesting either:
- The sequence was manually altered or reset, OR
- A very large number of features have been inserted and deleted (each insert increments the sequence even on rollback/deletion), OR
- A batch operation fired the Insert rule en masse

**GlobalID consideration:** If `GlobalID` is present on the feature class, it is also regenerated on every delete+insert. Any related tables or replica configurations that use `GlobalID` as a relationship key will also be affected. Confirm whether TRN_SECTRAV has a `GlobalID` column and whether anything joins to it.

### 1.2 Known Workflow

```
Export TRN_SECTRAV → Consultant (Eagle) receives shapefile/FGDB
→ Consultant collects field data
→ Consultant submits data back
→ HRM reconciles/loads into enterprise GDB
```

The vulnerability window is at the **submission/reconciliation step**.

---

## 2. Immediate Diagnostic Queries

Run these SQL queries against the enterprise geodatabase first to establish facts.

### 2.1 Check the Sequence Current Value

```sql
-- Check current sequence value
SELECT current_value, increment_by, min_value, max_value
FROM sde.sde_sequences
WHERE sequence_name = 'sectravid';
```

> **What to look for:** If the current value is in the 7,000,000+ range, it confirms the sequence has been called many more times than there are features in the table — pointing to repeated inserts and deletes.

### 2.2 Compare Live vs. Archive Row Counts

```sql
-- Count of current (live) features
SELECT COUNT(*) AS live_count FROM sdeadm.TRN_SECTRAV;

-- Count of archived (deleted/modified) versions
-- Archive table is named with _H suffix by default
SELECT COUNT(*) AS archive_count FROM sdeadm.TRN_SECTRAV_H;
```

> **What to look for:** A disproportionately large archive table compared to the live table suggests many features have been deleted and re-inserted over time.

### 2.3 Find Features with Changed IDs Using the Archive

> **Important:** Do NOT join archive rows back to the live table on `OBJECTID`. If a feature was deleted and re-inserted, the new row has a **different OBJECTID**. Use the known ID mapping table (Original_ID → New_ID) as your anchor, or use spatial coincidence (Section 2.4).

```sql
-- Step 1: Load known original IDs from mapping table into a temp table
-- (populate with the full Original_ID list, not just a few examples)
CREATE TABLE #id_map (original_id VARCHAR(20), new_id VARCHAR(20));
INSERT INTO #id_map VALUES
  ('TR1001088', 'TR7141890'),
  ('TR1001095', 'TR7141892'),
  -- ... add all known pairs ...
  ('TR7126644', 'TR7141895');

-- Step 2: Find the deletion event for each original ID
SELECT h.OBJECTID, h.TR_ID, h.ASSETID, h.gdb_from_date, h.gdb_to_date, h.gdb_is_delete
FROM sdeadm.TRN_SECTRAV_H h
JOIN #id_map m ON h.TR_ID = m.original_id
ORDER BY h.TR_ID, h.gdb_from_date;
```

> **What to look for:** Rows where `gdb_is_delete = 1` confirm a deletion occurred. Compare the `gdb_to_date` of the deletion event with the `gdb_from_date` of the new ID — if they are identical timestamps, a simultaneous delete+insert operation (e.g., Append or script reload) is the cause.

### 2.4 Check for Duplicate Geometries with Different IDs

> **Performance note:** This is a spatial self-join and can be slow on large feature classes. Run during off-hours or add a `TABLESAMPLE` clause, or limit to the bounding box of your known affected features first.

```sql
-- Look for spatially identical features with different TR_IDs
SELECT a.TR_ID AS id_a, b.TR_ID AS id_b, a.SHAPE.STAsText() AS geom
FROM sdeadm.TRN_SECTRAV a
JOIN sdeadm.TRN_SECTRAV b
  ON a.SHAPE.STEquals(b.SHAPE) = 1
 AND a.TR_ID <> b.TR_ID;
```

> **What to look for:** Duplicate geometries with different IDs confirm that old features were deleted and new ones were added in their place. If the new IDs all follow the `TR714xxxx` pattern, this confirms the batch event.

### 2.5 Inspect Attribute Rule and Sequence Definitions

```sql
-- Find the sequence definition item in the geodatabase item registry
SELECT name, definition
FROM sde.GDB_ITEMS
WHERE definition LIKE '%sectravid%';

-- Find attribute rule definitions for TRN_SECTRAV
-- (GDB_ITEMS stores rules as XML; look for items of type attribute rule)
SELECT i.name, i.definition
FROM sde.GDB_ITEMS i
JOIN sde.GDB_ITEMTYPES it ON i.type = it.uuid
WHERE it.name = 'Attribute Rule'
  AND i.name LIKE '%sectrav%';
```

> **Note:** `sde.GDB_ITEMS` stores metadata and definitions, not execution logs. To review whether batch attribute rule logging is enabled and to access execution history, check the **Attribute Rule Error table** (if configured) and the ArcGIS Server/Pro logs from the time of the suspect reconciliation event.

### 2.6 Check for Offline Replica / Disconnected Checkout

```sql
-- List any replicas defined on the database
SELECT replica_name, owner, creation_date, replica_type, access_type
FROM sde.SDE_REPLICAS;

-- Check replica datasets
SELECT * FROM sde.SDE_REPLICADATASETS
WHERE table_name LIKE '%SECTRAV%';
```

> **What to look for:** A disconnected (checkout) replica that was checked back in can trigger ID changes if the check-in process resolves conflicts by replacing rows. Two-way replica syncs can also delete and re-insert features depending on the conflict resolution policy.

---

## 3. Workflow Investigation

### 3.1 Identify the Exact Reconciliation Method

Interview or document the process used when the consultant submits data back. Determine which of the following is being used:

| Method | Does It Trigger Insert Rules? | Notes |
|--------|-------------------------------|-------|
| Geodatabase versioning (Post to Default) | No (update, not insert) | Safest method |
| Append tool (ArcGIS Pro/ArcMap) | **Yes** – new OBJECTIDs + new sequence values | Common mistake |
| Delete All + Load | **Yes** – all features are re-inserted | Very destructive |
| `arcpy.da.InsertCursor` | **Yes** | Depends on script |
| Replica Sync (two-way) | Possibly, if conflicts resolved as delete+insert | Check conflict policy |
| Replica Check-in (disconnected) | **Yes**, if conflict resolution replaces rows | Check replica settings |
| Field Maps / Feature Service edits | Possibly | Depends on service config |
| FME workspace | **Yes**, if writing via Insert | Check FME log |

**Action:** Ask Kirk and the reconciliation team exactly which tool/script is being used to integrate consultant data. Request the actual script or FME workspace if one exists.

### 3.2 Check Versioning Configuration

```sql
-- List all versions and their owners
SELECT version_name, owner, creation_time, modified_time, parent_name
FROM sde.SDE_VERSIONS
ORDER BY modified_time DESC;
```

> **What to look for:** Are consultants editing in a named version? Is reconcile/post happening correctly? A common error is to reconcile and post using `Append` rather than `Post`.

> **Branch versioning note:** If the geodatabase uses **branch versioning** (ArcGIS Enterprise feature service-based), the versioning mechanics differ from traditional SDE versioning. Branch versions are managed server-side and conflicts are resolved differently. Confirm whether TRN_SECTRAV is registered as branch versioned or traditional versioned.

```sql
-- Check if TRN_SECTRAV is registered as branch versioned
SELECT registration_id, table_name, owner, rowid_column, mv_view_name,
       object_flags
FROM sde.table_registry
WHERE table_name = 'TRN_SECTRAV' AND owner = 'sdeadm';
-- object_flags value indicates versioning type
```

### 3.3 Review ArcGIS Pro / Python / FME Scripts Used for Loading

Request access to any scripts used in the reconciliation workflow. Look specifically for:

- `arcpy.Append_management()` — will trigger Insert rules
- `arcpy.TruncateTable_management()` followed by an insert — will trigger Insert rules for **all** records
- `InsertCursor` — will trigger Insert rules
- Any `DELETE FROM` + `INSERT INTO` SQL operations
- FME workspaces writing to the feature class via the Esri Geodatabase writer
- Any ETL job (Task Scheduler, SQL Agent) that touches TRN_SECTRAV

---

## 4. Sequence Integrity Check

### 4.1 Determine How Many Times the Sequence Has Been Called

```sql
-- Total features ever inserted (approx) = current_sequence_value - start_value
-- If start was 1 and current is 7,141,900+, then ~7.1M inserts have occurred
-- But if only ~10,000 features exist, something is wrong

SELECT
    (SELECT COUNT(*) FROM sdeadm.TRN_SECTRAV) AS live_rows,
    (SELECT COUNT(*) FROM sdeadm.TRN_SECTRAV_H) AS archive_rows,
    (SELECT current_value FROM sde.sde_sequences WHERE sequence_name = 'sectravid') AS seq_current;
```

### 4.2 Check Whether the Sequence Was Manually Altered

The `sys.dm_exec_query_stats` DMV does **not** show DDL history. To audit sequence changes use one of the following approaches:

```sql
-- Option A: SQL Server Default Trace (captures DDL events if not disabled)
SELECT te.name AS event_type, t.StartTime, t.ApplicationName, t.LoginName,
       t.TextData, t.DatabaseName
FROM sys.fn_trace_gettable(
    (SELECT REVERSE(SUBSTRING(REVERSE(path), CHARINDEX('\', REVERSE(path)), 260)) +
     'log.trc'
     FROM sys.traces WHERE is_default = 1), DEFAULT) t
JOIN sys.trace_events te ON t.EventClass = te.trace_event_id
WHERE te.name IN ('Object:Altered','Object:Created','Object:Deleted')
  AND t.TextData LIKE '%sectravid%'
ORDER BY t.StartTime DESC;

-- Option B: If SQL Server Audit is configured
-- Check audit logs via sys.fn_get_audit_file for DDL_DATABASE_LEVEL_EVENTS
```

> If neither is available, ask the DBA to check whether the sequence `sdeadm.sectravid` was ever manually reset, incremented, or recreated, and review any change tickets or deployment records.

---

## 5. Reproduce the Issue in a Test Environment

Once the suspected method is identified, reproduce it in a test/staging geodatabase:

1. Copy a small set of TRN_SECTRAV features to a test FGDB or staging enterprise GDB
2. Simulate the consultant workflow (modify attributes, add features)
3. Run the reconciliation method currently in use
4. Check whether TR_IDs changed on unmodified features

This will confirm the root cause before any changes are made to production.

---

## 6. Root Cause Decision Tree

```
IDs changed on existing features
│
├── Were features deleted and re-inserted?
│   ├── YES → Check reconciliation tool (Append, Load, script, FME, replica check-in)
│   │         → Move to Section 7.1 (Fix: Use Update instead of Insert)
│   │
│   └── NO  → Were Insert rules accidentally triggered on Update?
│             ├── YES → Check attribute rule trigger settings (currently Insert-only ✓)
│             │         → Possible rule was recently changed — check audit log
│             └── NO  → Check sequence for manual alteration (Section 4.2)
│
└── Are IDs changing only on features that the consultant modified?
    ├── YES → Consultant's tool is deleting + re-inserting modified features
    │         → Section 7.2 (Fix: Preserve GlobalID / OBJECTID on edit)
    └── NO  → IDs changing on untouched features too
              → Likely a Truncate+Load, Append All, or disconnected replica check-in
              → Section 7.3 (Fix: Stop full reloads)
```

---

## 7. Recommended Fixes

### 7.1 Switch Reconciliation to Geodatabase Versioning (Preferred Fix)

The cleanest solution is a proper versioned editing workflow:

1. Consultants are given access to a **named child version** of the geodatabase
2. They edit in that version (geometry/attribute changes only, no delete+insert)
3. GIS staff **Reconcile and Post** the version to Default
4. Because features are updated (not re-inserted), attribute rules do NOT fire

### 7.2 If Using Append: Two-Pass Strategy to Preserve Existing IDs

A simple disable/re-enable of the attribute rules is not sufficient on its own — genuinely new features added by the consultant still need IDs assigned. Use a two-pass approach:

**Pass 1 — Update existing features (no rules needed):**

```python
import arcpy

fc = r"[GISRW01].[sdeadm].[TRN_SECTRAV]"
source = r"path\to\consultant_data"

# Disable rules before updating existing features
arcpy.management.DisableAttributeRules(fc, [
    "TRN_sectrav - TR_ID - Generate ID",
    "TRN_sectrav - ASSETID - Generate ID"
])

# Use UpdateCursor or a field-mapped Append with EXISTING rows only
# Join on a stable business key (e.g., original TR_ID or GlobalID if preserved)
# Update geometry and attribute fields — do NOT touch TR_ID or ASSETID
# ...

# Re-enable rules
arcpy.management.EnableAttributeRules(fc, [
    "TRN_sectrav - TR_ID - Generate ID",
    "TRN_sectrav - ASSETID - Generate ID"
])
```

**Pass 2 — Insert genuinely new features (rules fire normally):**

```python
# With rules re-enabled, Append only the features that are
# confirmed NEW (not present in the live database)
# The Insert rule will correctly assign them new IDs
arcpy.management.Append(
    inputs=new_features_only_layer,
    target=fc,
    schema_type="NO_TEST"
)
```

> **Prerequisite:** You must be able to reliably distinguish existing features from new ones. A stable join key (e.g., a `CONSULTANT_ID` field, or preserved `GlobalID`) is required. If no stable key exists, this is a process gap that must be closed first.

### 7.3 If Full Reloads Are Happening: Stop Them

If someone is running truncate+reload on TRN_SECTRAV, this must stop immediately. Instruct staff that:

- TRN_SECTRAV features must be **updated in place**, never truncated and reloaded
- Any new features (genuinely new trail segments) can be inserted normally — the Insert rule will assign them new IDs, which is correct
- The consultant's export file must be used as a **source for attribute updates only**, merged back using a stable key (GlobalID, TR_ID, or geometry) — not OBJECTID, which changes on re-insert

### 7.4 Long-Term: Add a Constraint Rule to Prevent ID Changes

Add a **Constraint Rule** to make TR_ID and ASSETID immutable after creation:

```arcade
// Constraint Rule: Prevent TR_ID from changing on Update
// Trigger: Update
$originalFeature.TR_ID == $feature.TR_ID
```

```arcade
// Constraint Rule: Prevent ASSETID from changing on Update
// Trigger: Update
$originalFeature.ASSETID == $feature.ASSETID
```

This will throw an error if any workflow attempts to change TR_ID or ASSETID on an update, making the problem visible before it silently corrupts data.

---

## 8. Data Remediation (After Root Cause is Fixed)

Once the root cause is confirmed and the workflow is corrected, use the ID mapping table (Original_ID → New_ID as documented by Kirk) to remediate data.

### 8.1 Update Related Tables

Any table that references `TR_ID` or `ASSETID` as a foreign key will need to be updated:

```sql
-- Example: update a related condition table
UPDATE sdeadm.TRN_SECTRAV_CONDITION
SET ASSETID = map.new_id
FROM id_mapping_table map
WHERE sdeadm.TRN_SECTRAV_CONDITION.ASSETID = map.original_id;
```

### 8.2 Restore Original IDs if Possible

> **Critical:** Do NOT join on `OBJECTID` for this operation. If features were deleted and re-inserted, the new row has a **different OBJECTID** from the original. Use the known ID mapping table (Kirk's list) or spatial geometry as the join key.

**Option A — Use the known mapping table (preferred if the list is complete):**

```sql
-- Restore original TR_ID and ASSETID using Kirk's mapping table
-- Run inside a versioned edit session; review before posting to Default
UPDATE live
SET live.TR_ID   = map.original_id,
    live.ASSETID = map.original_id   -- ASSETID mirrors TR_ID per the rule
FROM sdeadm.TRN_SECTRAV live
JOIN id_mapping_table map ON live.TR_ID = map.new_id;
```

**Option B — Use the archive table and spatial coincidence (if mapping table is incomplete):**

```sql
-- Find archive rows with original IDs that spatially match current live features
SELECT
    live.TR_ID          AS current_id,
    hist.TR_ID          AS original_id,
    hist.gdb_to_date    AS deletion_date
FROM sdeadm.TRN_SECTRAV live
JOIN sdeadm.TRN_SECTRAV_H hist
  ON live.SHAPE.STEquals(hist.SHAPE) = 1
 AND hist.gdb_is_delete = 1
 AND hist.TR_ID LIKE 'TR1%'        -- original ID format
 AND live.TR_ID  LIKE 'TR7141%'    -- new ID format
ORDER BY live.TR_ID;
```

> After validation, apply the ID updates in a versioned edit session and reconcile/post to Default.

---

## 9. Preventative Measures Going Forward

| Action | Priority | Owner |
|--------|----------|-------|
| Document and enforce standard consultant data submission workflow | High | GIS Manager |
| Add Constraint Rules to block TR_ID/ASSETID changes on Update | High | GIS Admin |
| Add a field `CREATED_DATE` with Insert-only rule to audit insertions | Medium | GIS Admin |
| Lock TR_ID and ASSETID fields as non-editable in Field Maps / editing templates | Medium | GIS Admin |
| Train all staff on the difference between Append and versioned editing | High | GIS Manager |
| Confirm GlobalID usage in related tables and replicas; document impact | High | GIS Admin / DBA |
| Set up monitoring query (below) to alert when sequence gap is abnormally large | Medium | DBA |
| Audit Bus Pads and other affected layers using the same pattern (see Section 11) | High | GIS Admin |

### 9.1 Sequence Monitoring Query

Schedule this query (e.g., via SQL Server Agent) to run after every reconciliation event. Alert if the ratio exceeds a threshold:

```sql
SELECT
    seq.current_value                                  AS seq_value,
    COUNT(live.OBJECTID)                               AS live_count,
    (SELECT COUNT(*) FROM sdeadm.TRN_SECTRAV_H)        AS archive_count,
    seq.current_value - COUNT(live.OBJECTID)           AS phantom_increment_count,
    CAST(seq.current_value AS FLOAT) /
        NULLIF(COUNT(live.OBJECTID), 0)                AS seq_to_live_ratio
FROM sdeadm.TRN_SECTRAV live
CROSS JOIN (
    SELECT current_value FROM sde.sde_sequences
    WHERE sequence_name = 'sectravid'
) seq
GROUP BY seq.current_value;
-- Alert if seq_to_live_ratio > 10 (i.e., sequence advanced 10x more than live rows exist)
```

---

## 10. Open Questions to Resolve Before Proceeding

Before starting remediation, confirm the following:

1. **What exact tool/script is used to load consultant data back into the GDB?** (Append? Python script? Manual edit? Replica sync? FME?)
2. **Was the sequence `sdeadm.sectravid` ever manually altered?** (Ask DBA, check default trace)
3. **Do consultants edit in a named geodatabase version, or do they work on exported flat files only?**
4. **Are there any scheduled tasks (Python scripts, FME workspaces, ETL jobs, SQL Agent jobs) that touch TRN_SECTRAV?**
5. **Is TRN_SECTRAV registered as traditional versioned or branch versioned?**
6. **Does TRN_SECTRAV have a `GlobalID` column? If so, are any related tables or replicas joining on it?**
7. **Are Bus Pads and other affected layers using the same sequence (`sectravid`), or a different one?**
8. **Is the ID mapping table (Kirk's list) exhaustive, or are there more affected features not yet identified?**
9. **Are there any disconnected replicas (checkout/check-in) configured for TRN_SECTRAV or related layers?**

---

## 11. Other Affected Layers (Bus Pads, etc.)

The original issue report references Bus pads and potentially other layers. Before closing this investigation, audit each affected layer for the same pattern:

```sql
-- Template: replace <TABLE>, <ARCHIVE_TABLE>, <SEQUENCE_NAME> for each layer
SELECT
    (SELECT COUNT(*) FROM sdeadm.<TABLE>)     AS live_rows,
    (SELECT COUNT(*) FROM sdeadm.<ARCHIVE_TABLE>) AS archive_rows,
    (SELECT current_value FROM sde.sde_sequences
     WHERE sequence_name = '<SEQUENCE_NAME>')  AS seq_current;
```

For each layer, answer:
- Does it have Insert-only attribute rules that generate IDs?
- Has the sequence advanced far beyond the live row count?
- Are IDs from the same batches changing?

Apply the same diagnostic and remediation steps from this document to each affected layer.

---

*Document prepared for: Justin Chang, Marcela Soto Trujillo, Alex Gallagher*
*Related ticket: Missing Asset IDs in TRN Sectrav (raised by Kirk, March 4, 2026)*
*Last updated: 2026-03-05*
