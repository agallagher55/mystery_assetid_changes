# Troubleshooting Plan: Changing Asset IDs in `[GISRW01].[sdeadm].[TRN_SECTRAV]`

**Prepared:** 2026-03-05  
**Issue:** `TR_ID` and `ASSETID` fields are changing on existing features after consultant data is reconciled back into the enterprise geodatabase.  
**Database:** `[GISRW01].[sdeadm].[TRN_SECTRAV]` (archiving enabled)

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
-- Archive table typically named TRN_SECTRAV_H
SELECT COUNT(*) AS archive_count FROM sdeadm.TRN_SECTRAV_H;
```

> **What to look for:** A disproportionately large archive table compared to the live table suggests many features have been deleted and re-inserted over time.

### 2.3 Find Features with Changed IDs Using the Archive

```sql
-- Find ObjectIDs where TR_ID appears more than once in archive history
SELECT OBJECTID, TR_ID, ASSETID, gdb_from_date, gdb_to_date, gdb_is_delete
FROM sdeadm.TRN_SECTRAV_H
WHERE TR_ID IN (
    'TR1001088','TR1001095','TR1001096'  -- paste known original IDs
)
ORDER BY OBJECTID, gdb_from_date;
```

> **What to look for:** Whether the old TR_ID was flagged `gdb_is_delete = 1` before the new ID appeared. If yes, a delete happened. Check whether the `gdb_to_date` of the deletion and `gdb_from_date` of the new insert are the same timestamp — this would confirm a simultaneous delete+insert operation.

### 2.4 Check for Duplicate Geometries with Different IDs

```sql
-- Look for spatially identical features with different TR_IDs
-- (Adapt geometry column name as needed)
SELECT a.TR_ID AS id_a, b.TR_ID AS id_b, a.SHAPE.STAsText() AS geom
FROM sdeadm.TRN_SECTRAV a
JOIN sdeadm.TRN_SECTRAV b
  ON a.SHAPE.STEquals(b.SHAPE) = 1
 AND a.TR_ID <> b.TR_ID;
```

> **What to look for:** Duplicate geometries with different IDs confirm that old features were deleted and new ones were added in their place.

### 2.5 Inspect Edit History via Attribute Rules Batch Log

```sql
-- If batch attribute rule logging is enabled
SELECT * FROM sde.GDB_ITEMS
WHERE definition LIKE '%sectravid%';
```

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
| Field Maps / Feature Service edits | Possibly | Depends on service config |

**Action:** Ask Kirk and the reconciliation team exactly which tool/script is being used to integrate consultant data.

### 3.2 Check Versioning Configuration

```sql
-- List all versions and their owners
SELECT version_name, owner, creation_time, modified_time
FROM sde.SDE_VERSIONS
ORDER BY modified_time DESC;
```

> **What to look for:** Are consultants editing in a named version? Is reconcile/post happening correctly? A common error is to reconcile and post using `Append` rather than `Post`.

### 3.3 Review ArcGIS Pro / Python Scripts Used for Loading

Request access to any scripts used in the reconciliation workflow. Look specifically for:

- `arcpy.Append_management()` — will trigger Insert rules
- `arcpy.TruncateTable_management()` followed by an insert — will trigger Insert rules for ALL records
- `InsertCursor` — will trigger Insert rules
- Any `DELETE FROM` + `INSERT INTO` SQL operations

---

## 4. Sequence Integrity Check

### 4.1 Determine How Many Times the Sequence Has Been Called

```sql
-- Total features ever inserted = current_sequence_value - start_value
-- If start was 1 and current is 7,141,900+, then ~7.1M inserts have occurred
-- But if only ~10,000 features exist, something is wrong

SELECT 
    (SELECT COUNT(*) FROM sdeadm.TRN_SECTRAV) AS live_rows,
    (SELECT COUNT(*) FROM sdeadm.TRN_SECTRAV_H) AS archive_rows,
    (SELECT current_value FROM sde.sde_sequences WHERE sequence_name = 'sectravid') AS seq_current;
```

### 4.2 Check Whether the Sequence Was Manually Altered

```sql
-- Review DDL history if available (SQL Server example)
SELECT TOP 100 *
FROM sys.dm_exec_query_stats
-- Or review sde log tables for sequence changes
```

Check with the DBA whether the sequence `sdeadm.sectravid` was ever manually reset, incremented, or recreated.

---

## 5. Reproduce the Issue in a Test Environment

Once the suspected method is identified, reproduce it in a test/staging geodatabase:

1. Copy a small set of TRN_SECTRAV features to a test FGDB
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
│   ├── YES → Check reconciliation tool (Append, Load, script)
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
              → Likely a Truncate+Load or Append All operation
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

### 7.2 If Using Append: Enable Field Mapping to Preserve TR_ID/ASSETID

If Append is unavoidable:

- Use the `field_mapping` parameter in `arcpy.Append_management()` to explicitly map `TR_ID` and `ASSETID` from the source
- **AND** temporarily disable the attribute rules before the Append, then re-enable them:

```python
import arcpy

fc = r"[GISRW01].[sdeadm].[TRN_SECTRAV]"

# Disable rules before append
arcpy.management.DisableAttributeRules(fc, ["TRN_sectrav - TR_ID - Generate ID",
                                             "TRN_sectrav - ASSETID - Generate ID"])

arcpy.management.Append(
    inputs=r"path\to\consultant_data",
    target=fc,
    schema_type="NO_TEST",
    field_mapping=...  # map TR_ID and ASSETID explicitly
)

# Re-enable rules after
arcpy.management.EnableAttributeRules(fc, ["TRN_sectrav - TR_ID - Generate ID",
                                            "TRN_sectrav - ASSETID - Generate ID"])
```

> ⚠️ **Warning:** Disabling rules requires careful procedure — new features genuinely added by the consultant still need IDs assigned. Only existing features should have their IDs preserved.

### 7.3 If Full Reloads Are Happening: Stop Them

If someone is running truncate+reload on TRN_SECTRAV, this must stop immediately. Instruct staff that:

- TRN_SECTRAV features must be **updated in place**, never truncated and reloaded
- Any new features (genuinely new trail segments) can be inserted normally — the Insert rule will assign them new IDs, which is correct
- The consultant's export file must be used as a **source for attribute updates only**, merged back using OBJECTID or GlobalID as the join key

### 7.4 Long-Term: Add a Constraint Rule to Prevent ID Changes

Add a **Constraint Rule** to make TR_ID and ASSETID immutable after creation:

```arcade
// Constraint Rule: Prevent TR_ID from changing
// Trigger: Update
$originalFeature.TR_ID == $feature.TR_ID
```

This will throw an error if any workflow attempts to change TR_ID on an update, making the problem visible before it silently corrupts data.

---

## 8. Data Remediation (After Root Cause is Fixed)

Once the root cause is confirmed and the workflow is corrected, use the ID mapping table (Original_ID → New_ID as documented by Kirk) to remediate data:

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

If the archive table confirms what the original IDs were:

```sql
-- Restore original TR_ID values (requires edit session)
UPDATE sdeadm.TRN_SECTRAV
SET TR_ID = h.TR_ID,
    ASSETID = h.ASSETID
FROM sdeadm.TRN_SECTRAV_H h
WHERE sdeadm.TRN_SECTRAV.OBJECTID = h.OBJECTID
  AND h.gdb_is_delete = 0
  AND h.TR_ID LIKE 'TR1%';  -- original ID format
```

> ⚠️ Perform this in a versioned edit session and review before posting to Default.

---

## 9. Preventative Measures Going Forward

| Action | Priority | Owner |
|--------|----------|-------|
| Document and enforce standard consultant data submission workflow | High | GIS Manager |
| Add Constraint Rule to block TR_ID/ASSETID changes on Update | High | GIS Admin |
| Add a field `CREATED_DATE` with Insert-only rule to audit insertions | Medium | GIS Admin |
| Set up monitoring query to alert when ID gap in sequence is abnormally large | Medium | DBA |
| Train all staff on the difference between Append and versioned editing | High | GIS Manager |
| Lock TR_ID and ASSETID fields as non-editable in Field Maps / editing templates | Medium | GIS Admin |

---

## 10. Open Questions to Resolve Before Proceeding

Before starting remediation, confirm the following:

1. **What exact tool/script is used to load consultant data back into the GDB?** (Append? Python script? Manual edit? Replica sync?)
2. **Was the sequence `sdeadm.sectravid` ever manually altered?** (Ask DBA)
3. **Do consultants edit in a named geodatabase version, or do they work on exported flat files only?**
4. **Are there any scheduled tasks (Python scripts, FME workspaces, ETL jobs) that touch TRN_SECTRAV?**
5. **Are Bus Pads and other affected layers using the same sequence, or a different one?**
6. **Is the ID mapping table (Image 3) exhaustive, or are there more affected features not yet identified?**

---

*Document prepared for: Justin Chang, Marcela Soto Trujillo, Alex Gallagher*  
*Related ticket: Missing Asset IDs in TRN Sectrav (raised by Kirk, March 4, 2026)*
