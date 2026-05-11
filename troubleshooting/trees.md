# AST_tree — AssetID Remediation

## Problem

`SDEADM.AST_tree` (~80,000 records) underwent a truncate-and-load without first disabling or deleting the attribute rules that fire sequences on insert. As a result, every re-inserted record received a new `ASSETID` instead of retaining its original value. Related records in a linked table now have broken foreign key references.

A lookup table (`QC_AST_tree_AssetIds_To_Restore - 20260331.csv`) exists that maps each **Current AssetID → Original AssetID**.

---

## Why the Original Workflow Failed

The attempted fix (delete rules → disable editor tracking → join lookup table → Calculate Field) ran for **2 hours 2 minutes** before failing with:

```
ERROR 160370: The version has been redefined to a new database state.
```

This error occurs in a versioned geodatabase when another user posts or reconciles changes to the parent version while a long-running edit session is open. A single 2-hour Calculate Field transaction is highly vulnerable to this because any concurrent activity invalidates the version state mid-operation.

---

## Recommended Fix

### Option A — ArcPy UpdateCursor with Batched Commits (Recommended)

This approach loads the entire lookup into memory as a Python dictionary (eliminating join overhead), then iterates rows and commits in small batches. No single transaction runs long enough to trigger `ERROR_160370`.

**Pre-conditions:**
- Attribute rules on `ASSETID` already deleted
- Editor tracking already disabled
- No other users actively posting to Default during the run (coordinate a maintenance window or run after hours)
- Reconcile your edit version against Default and compress the geodatabase before starting

```python
import arcpy
import csv

# ── Configuration ────────────────────────────────────────────────────────────
CSV_PATH  = r'C:\GIS\QC_AST_tree_AssetIds_To_Restore - 20260331.csv'
FC        = r'Database Connections\your_connection.sde\SDEADM.AST_tree'
WORKSPACE = r'Database Connections\your_connection.sde'
BATCH     = 2000   # rows per commit; tune down if state errors persist
# ─────────────────────────────────────────────────────────────────────────────

# Load lookup into memory: {current_assetid: original_assetid}
lookup = {}
with open(CSV_PATH, newline='') as f:
    for row in csv.DictReader(f):
        lookup[row['Current AssetID'].strip()] = row['Original AssetID'].strip()

print(f"Loaded {len(lookup)} lookup entries.")

edit = arcpy.da.Editor(WORKSPACE)
edit.startEditing(False, True)   # no undo, versioned
edit.startOperation()

count = 0
skipped = 0

with arcpy.da.UpdateCursor(FC, ['ASSETID']) as cursor:
    for row in cursor:
        current = row[0]
        if current in lookup:
            row[0] = lookup[current]
            cursor.updateRow(row)
            count += 1
            if count % BATCH == 0:
                edit.stopOperation()
                edit.saveEdits()
                edit.startOperation()
                print(f"  Committed {count} rows...")
        else:
            skipped += 1

edit.stopOperation()
edit.saveEdits()
edit.stopEditing(True)

print(f"Done. Updated: {count} | Skipped (no match): {skipped}")
```

**Why this is faster than Calculate Field + join:**
- The dictionary lookup is O(1) per row — no join evaluation overhead
- `saveEdits()` every 2,000 rows keeps individual transactions short (seconds each)
- If a version state change does occur, only the current in-flight batch is at risk; all prior batches are already committed

---

### Option B — Direct T-SQL UPDATE (Fastest — seconds, not hours)

If you have a direct SQL Server connection (not routed through the SDE/ArcGIS stack), a set-based UPDATE runs almost instantly. This completely bypasses versioning and the `ERROR_160370` issue.

**When this is safe:**
- The feature class is **unversioned**, OR
- All child versions have been reconciled, posted, and compressed — so the physical base table in Default reflects all current data
- Attribute rules are already deleted (so the SQL engine won't trigger them)

```sql
-- 1. Stage the lookup data
CREATE TABLE #id_restore (
    CurrentAssetID  NVARCHAR(50),
    OriginalAssetID NVARCHAR(50)
);

-- Bulk-insert your CSV into #id_restore here (use SSMS Import, BULK INSERT, etc.)

-- 2. Preview the update before committing
SELECT
    t.ASSETID        AS CurrentAssetID,
    r.OriginalAssetID
FROM SDEADM.AST_tree AS t
INNER JOIN #id_restore AS r
    ON t.ASSETID = r.CurrentAssetID;

-- 3. Apply the update
BEGIN TRANSACTION;

UPDATE t
SET    t.ASSETID = r.OriginalAssetID
FROM   SDEADM.AST_tree AS t
INNER JOIN #id_restore AS r
    ON t.ASSETID = r.CurrentAssetID;

-- Verify row count matches expectation, then:
COMMIT;
-- Or ROLLBACK if counts look wrong.

DROP TABLE #id_restore;
```

~80k rows with an index on `ASSETID` will typically complete in under a second.

---

### Option C — Unregister from Versioning, Update, Re-register

Most invasive but entirely eliminates version-state concerns.

1. Reconcile and post all child versions; compress the geodatabase
2. Confirm no active edit sessions
3. In ArcGIS Pro Catalog: right-click `AST_tree` → **Manage** → **Unregister as Versioned**
4. Run the T-SQL UPDATE from Option B
5. Re-register as versioned: right-click → **Manage** → **Register as Versioned**

> **Risk:** Any edits that existed only in child versions (not yet posted to Default) are lost. Only use during a coordinated maintenance window.

---

## Decision Guide

| Situation | Recommended option |
|---|---|
| No direct SQL Server access; must use ArcGIS tools | **Option A** |
| Direct SQL Server access; all versions reconciled/compressed | **Option B** |
| Cannot coordinate a maintenance window; other users active | **Option A** (small batch size, off-peak hours) |
| Willing to temporarily unregister versioning | **Option C** |

---

## After the Update

1. Verify counts: confirm updated row count matches the lookup table record count.
2. Spot-check a sample of `ASSETID` values against the lookup CSV.
3. Test the related table join to confirm broken foreign key references are now resolved.
4. Re-enable editor tracking if it was in use before the incident.
5. Re-create attribute rules if they were deleted as part of remediation.
6. Reconcile and post to Default; compress the geodatabase.
7. Document the completion date and method in this file and in the project issue log.
