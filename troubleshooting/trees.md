The core problem is that a 2-hour single-transaction edit session is vulnerable to any concurrent version state change. The fix is to eliminate the long transaction, either by batching commits or bypassing versioning entirely.

Here are the approaches in order of preference:

Option A: ArcPy UpdateCursor with dictionary + batched commits (recommended)
This is much faster than Calculate Field + join, and chunked commits mean no single transaction runs long enough to hit ERROR_160370.

import arcpy
import csv

# Load lookup into memory once: {current_assetid: original_assetid}
lookup = {}
with open(r'C:\path\to\QC_AST_tree_AssetIds_To_Restore - 20260331.csv', newline='') as f:
    for row in csv.DictReader(f):
        lookup[row['Current AssetID'].strip()] = row['Original AssetID'].strip()

fc = r'Database Connections\yourconnection.sde\SDEADM.AST_tree'
workspace = r'Database Connections\yourconnection.sde'

edit = arcpy.da.Editor(workspace)
edit.startEditing(False, True)   # no undo, versioned
edit.startOperation()

count = 0
BATCH = 2000

with arcpy.da.UpdateCursor(fc, ['ASSETID']) as cursor:
    for row in cursor:
        if row[0] in lookup:
            row[0] = lookup[row[0]]
            cursor.updateRow(row)
            count += 1
            if count % BATCH == 0:
                edit.stopOperation()
                edit.saveEdits()          # commits each batch
                edit.startOperation()
                print(f"Committed {count} rows")

edit.stopOperation()
edit.saveEdits()
edit.stopEditing(True)
print(f"Done. Total updated: {count}")
Key differences from your current approach:

Dictionary lookup = no join table overhead
saveEdits() every 2000 rows = no single multi-hour transaction
Each commit is independent; a version state change only affects the current batch, not all prior work
Option B: Direct T-SQL UPDATE (fastest — seconds, not hours)
If you can get a direct SQL Server connection (not through SDE/ArcGIS), a set-based UPDATE completes almost instantly. This bypasses versioning entirely, so it only works cleanly if:

The feature class is unversioned, OR
You're working on the physical base table in Default after compressing and reconciling all versions
-- Stage your lookup table first
CREATE TABLE #id_restore (
    CurrentAssetID NVARCHAR(50),
    OriginalAssetID NVARCHAR(50)
);

-- Bulk insert your CSV into #id_restore here, then:

UPDATE t
SET t.ASSETID = r.OriginalAssetID
FROM SDEADM.AST_tree AS t
INNER JOIN #id_restore AS r
    ON t.ASSETID = r.CurrentAssetID;
~80k rows with an index on ASSETID will run in under a second. If attribute rules and editor tracking are already disabled/deleted, this is the cleanest path — but confirm the versioning state first.

Option C: Unregister from versioning → SQL update → re-register
Most invasive but avoids all version state issues:

Ensure all versions are reconciled/posted and compressed
Unregister the feature class from versioning in ArcGIS Pro (right-click in Catalog → Manage → Unregister as Versioned)
Run the T-SQL UPDATE above
Re-register as versioned
Risk: any in-flight edits in child versions are lost. Only viable during a maintenance window.

Practical recommendation
Go with Option A (batched UpdateCursor) unless you have direct SQL Server access with appropriate permissions, in which case Option B is trivially faster. In either case:

Run during off-hours or coordinate with other editors so no one is posting to Default during the operation
Reconcile your edit version against Default and compress the geodatabase before starting, to minimize state churn
The ERROR_160370 you hit is almost certainly because another user posted to the parent version during your 2-hour window — batching eliminates that exposure
