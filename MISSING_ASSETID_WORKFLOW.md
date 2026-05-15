# Missing ASSETID Remediation Workflow

**Task:** TASK0316399 (parent) / TASK0320812, TASK0319535 (related)
**Created:** 2026-05-15
**Priority:** High | **Total Time Estimate:** ~4–5 hrs (7 known FCs: ~3–3.5 hrs | TBD FCs + overhead: ~1–1.5 hrs)

---

## Quick Reference — Point-Form Workflow

1. Identify which workflow type applies (Type A or Type B) using the feature class table below.
2. Notify stakeholders of scheduled maintenance window and planned service downtime.
3. Create a backup copy of the feature class in the geodatabase.
4. Stop all associated ArcGIS services.
5. Disable editor tracking on the feature class.
6. Export existing attribute rules to a JSON file.
7. Delete attribute rules from the feature class.
8. Run field calculation to populate NULL ASSETIDs from the correct source field.
9. *(Type B only)* Update/reconfigure exported attribute rules so the primary ID sequence equals ASSETID.
10. Import attribute rules back to the feature class.
11. Re-enable editor tracking.
12. Restart all associated services.
13. Verify ASSETID counts and spot-check values.
14. Document changes and close ticket.

---

## Feature Class Summary

Two attribute rule scenarios exist. Confirm which applies before starting work.

| Feature Class | Missing ASSETIDs | Rule Type | Source Field for ASSETID | Associated Services | Est. Time |
|---|---|---|---|---|---|
| `AST_tree` | 83,250 | **Type A** — rules already unified | Primary ID field | CityWorks | ~56–61 min |
| `TRN_transit_shelter` | 512 | **Type B** — SHELTERID must equal ASSETID | `SHELTERID` | Cityworks, AGS Transit WGS84 (Bus/Transit Shelter), RoadOperation/Transit Shelter | ~25–29 min |
| `TRN_sectrav` | 201 | **Type A** — rules already unified | `TR_ID` | AGS Land Sectrav WGS84, Cityworks Assets, Cityworks Map, DDE, HRMBaseData, WinterMaintenance | ~19–22 min |
| `AST_SIGN` | 33 | **Type B** — primary ID must equal ASSETID | Primary ID field | Cityworks Assets, HRMBaseData, Shared All, ParksRec Mobile | ~23–25 min |
| `TRN_traffic_calming_infra` | 25 | **Type B** — primary ID must equal ASSETID | Primary ID field | AGS Geotab View, AGS Traffic Zone WGS84 | ~23–25 min |
| `LND_hrm_parcel` | 3 | **Type A** — rules already unified | Primary ID field | DDE, HRMBaseData, CityworksMap, AGS Property WGS84, AGS GovProperty WGS84 | ~18–20 min |
| `AST_parking_pay_station` | 2 | **Type B** — primary ID must equal ASSETID | Primary ID field | Cityworks Assets, Cityworks Map, DDE, HRMBaseData | ~23–25 min |
| `Streets` | TBD | TBD (see TASK0320812) | TBD | TBD | TBD |
| `AST_tree_vaults` | TBD | TBD (see TASK0319535) | TBD | TBD | TBD |
| `LND_outdoor_req_equip_point` | TBD | TBD (see TASK0319535) | TBD | TBD | TBD |
| `TRN_bus_pad` | TBD | TBD (see TASK0319535) | TBD | TBD | TBD |
| `BLD_electrical` | TBD | TBD (see TASK0319535) | TBD | TBD | TBD |
| `BLD_exterior` | TBD | TBD (see TASK0319535) | TBD | TBD | TBD |
| `BLD_mechanical` | TBD | TBD (see TASK0319535) | TBD | TBD | TBD |

> **Ordering note:** Feature classes are sorted by estimated effort/impact, not alphabetically. Work AST_tree first (largest volume) and AST_parking_pay_station last.

> **Type A** — Attribute rules already use a single unified sequence. ASSETID just needs to be backfilled from the existing primary ID field. No rule changes required.
>
> **Type B** — The sequence that generates the primary ID and the sequence that generates ASSETID are currently different. Both the backfill calculation AND an attribute rule update are required so future inserts stay in sync.

---

## Time Estimate Breakdown

The table below summarises the estimated time per feature class. Service stop/start is ~2 min regardless of service count. Field calc time scales with record count. Type B rule work is split into Arcade editing (human analysis) and the mechanical import + test.

| Feature Class | Step 1 Backup | Steps 2+9 Services | Steps 3–5 Tracking+Rules | Step 6 Field Calc | Step 7a Edit Arcade (Type B only) | Step 7b Rule Import | Step 10 Verify | **Total** |
|---|---|---|---|---|---|---|---|---|
| `AST_tree` | 10–15 min | 4 min | 5 min | ~30 min | N/A (Type A) | 2 min | 5 min | **~56–61 min** |
| `TRN_transit_shelter` | 2–3 min | 4 min | 5 min | 2–5 min | 5 min | 2 min | 5 min | **~25–29 min** |
| `TRN_sectrav` | 2–3 min | 4 min | 5 min | 1–3 min | N/A (Type A) | 2 min | 5 min | **~19–22 min** |
| `AST_SIGN` | 2–3 min | 4 min | 5 min | < 1 min | 5 min | 2 min | 5 min | **~23–25 min** |
| `TRN_traffic_calming_infra` | 2–3 min | 4 min | 5 min | < 1 min | 5 min | 2 min | 5 min | **~23–25 min** |
| `LND_hrm_parcel` | 2–3 min | 4 min | 5 min | < 1 min | N/A (Type A) | 2 min | 5 min | **~18–20 min** |
| `AST_parking_pay_station` | 2–3 min | 4 min | 5 min | < 1 min | 5 min | 2 min | 5 min | **~23–25 min** |
| **Known FC Subtotal** | | | | | | | | **~187–207 min (~3–3.5 hrs)** |
| TBD FCs + overhead | | | | | | | | ~1–1.5 hrs |
| **Grand Total** | | | | | | | | **~4–5 hrs** |

> Times assume a single operator working sequentially. The main time driver is AST_tree's field calculation (~30 min on 83k rows over SDE). All other feature classes are under 30 min each.

---

## Prerequisites

Before beginning work on any feature class:

- [ ] Confirm the source/primary ID field name for the feature class (check existing attribute rules or schema).
- [ ] Run a pre-work count query to confirm the number of NULL/empty ASSETIDs matches the expected figure above.
- [ ] Confirm a maintenance window with stakeholders — services will be down during field calculation.
- [ ] Ensure you have **sde admin** or equivalent write access to the geodatabase.
- [ ] All edits must be performed in a **versioned edit session** (Default version or an approved child version promoted to Default after review).
- [ ] Do not use the Append-with-truncate / delete+insert workflow on these feature classes.

### Pre-Work Verification Query

Run the following T-SQL to confirm null counts before starting. Repeat after completing to verify results:

```sql
-- Replace schema and table name as appropriate for each feature class
SELECT COUNT(*) AS missing_assetid_count
FROM [GISRW01].[sdeadm].[<FEATURE_CLASS_NAME>]
WHERE ASSETID IS NULL OR ASSETID = '';
```

---

## Detailed Workflow

Work through each feature class individually. Complete all steps for one feature class before starting the next. Prioritise by impact: highest missing count first (AST_tree → TRN_transit_shelter → TRN_sectrav → AST_SIGN → TRN_traffic_calming_infra → LND_hrm_parcel → AST_parking_pay_station).

---

### Step 1 — Create a Backup Copy of the Feature Class `⏱ 5–15 min`

**Tool:** ArcGIS Pro (Geoprocessing) or ArcCatalog

1. In ArcGIS Pro, open the **Copy Features** tool (Data Management > Features > Copy Features).
2. Set **Input Features** to the target feature class (e.g., `[GISRW01].[sdeadm].[AST_tree]`).
3. Set **Output Feature Class** to a clearly named backup in a safe location, e.g.:
   ```
   [GISRW01].[sdeadm].[AST_tree_BACKUP_20260515]
   ```
4. Run and confirm the row count of the backup matches the source.
5. Record the backup name and row count in your notes.

> The backup copy is a safety net. Do not delete it until the fix has been verified and the ticket closed.

---

### Step 2 — Stop Associated Services `⏱ ~2 min`

**Tool:** ArcGIS Server Manager

1. Log in to ArcGIS Server Manager.
2. Navigate to **Services**.
3. Stop each service associated with the feature class (refer to the table above).
4. Confirm each service shows **Stopped** status before proceeding.
5. Note the time services were stopped for the change log.

> Stopping services prevents new edits or reads from interfering with the field calculation and avoids cache inconsistencies when services restart.

---

### Step 3 — Disable Editor Tracking `⏱ 1–2 min`

**Tool:** ArcGIS Pro (Feature Class Properties) or Python/ArcPy

1. In ArcGIS Pro, right-click the feature class in the Catalog pane → **Properties**.
2. Navigate to the **Editor Tracking** tab.
3. Uncheck **Enable Editor Tracking**.
4. Click **OK**.

Alternatively, using ArcPy:

```python
import arcpy

fc = r"Database Connections\GISRW01.sde\sdeadm.AST_tree"
arcpy.DisableEditorTracking_management(fc)
```

> Editor tracking must be disabled so the field calculation does not stamp every row with the current editor/timestamp, which would create a misleading audit trail.

---

### Step 4 — Export Existing Attribute Rules `⏱ 1–2 min`

**Tool:** ArcGIS Pro (Geoprocessing) or ArcPy

1. Open the **Export Attribute Rules** tool (Data Management > Attribute Rules > Export Attribute Rules).
2. Set **Input Table** to the target feature class.
3. Set **Output CSV File** to a clearly named file, e.g.:
   ```
   C:\GIS\AttributeRules\AST_tree_rules_export_20260515.csv
   ```
4. Run the tool and confirm the CSV contains the expected rules.
5. Open and review the CSV — note the rule names, triggering events, and Arcade expressions before making any changes.

> Keep the exported CSV. It is your rollback point if rule re-import fails.

---

### Step 5 — Delete Attribute Rules `⏱ 1–2 min`

**Tool:** ArcGIS Pro (Geoprocessing) or ArcPy

1. Open the **Delete Attribute Rules** tool (Data Management > Attribute Rules > Delete Attribute Rules).
2. Set **Input Table** to the target feature class.
3. Select all rules to delete (or target only the ASSETID/sequence-related rules if others are unrelated).
4. Run the tool.
5. In the feature class properties, confirm no attribute rules remain.

```python
import arcpy

fc = r"Database Connections\GISRW01.sde\sdeadm.AST_tree"
rules = [r.name for r in arcpy.da.ListAttributeRules(fc)]
arcpy.DeleteAttributeRules_management(fc, rules)
```

> Attribute rules must be removed before the field calculation. Insert-type rules would fire on any row touched by an update if left active, potentially overwriting the values you are trying to set.

---

### Step 6 — Run Field Calculation to Fix ASSETIDs `⏱ < 1–30 min (varies by record count)`

**Tool:** ArcGIS Pro (Field Calculator) or ArcPy Update Cursor

This step differs slightly between Type A and Type B. Field calculation time scales with record count:

| Feature Class | Records to Update | Estimated Calculation Time |
|---|---|---|
| `AST_tree` | 83,250 | ~30 min |
| `TRN_transit_shelter` | 512 | 2–5 min |
| `TRN_sectrav` | 201 | 1–3 min |
| `AST_SIGN` | 33 | < 1 min |
| `TRN_traffic_calming_infra` | 25 | < 1 min |
| `LND_hrm_parcel` | 3 | < 1 min |
| `AST_parking_pay_station` | 2 | < 1 min |

#### Type A — Rules Already Unified (AST_tree, TRN_sectrav, LND_hrm_parcel)

ASSETID is NULL but the primary ID field already holds the correct value. Calculate ASSETID directly from the primary ID field, targeting only NULL rows.

```python
import arcpy

fc = r"Database Connections\GISRW01.sde\sdeadm.TRN_sectrav"
primary_id_field = "TR_ID"   # confirm correct field name for each feature class

with arcpy.da.UpdateCursor(fc, [primary_id_field, "ASSETID"],
                           where_clause="ASSETID IS NULL OR ASSETID = ''") as cursor:
    for row in cursor:
        row[1] = row[0]   # set ASSETID = primary ID
        cursor.updateRow(row)

print("Done. Re-run count query to verify.")
```

#### Type B — Sequence Rules Are Different (TRN_transit_shelter, AST_SIGN, TRN_traffic_calming_infra, AST_parking_pay_station)

The primary ID field (e.g., `SHELTERID`) holds the correct stable identifier. Set ASSETID equal to that field for all NULL rows, and then reconfigure the attribute rule (Step 7) so future inserts keep them in sync.

```python
import arcpy

fc = r"Database Connections\GISRW01.sde\sdeadm.TRN_transit_shelter"
source_field = "SHELTERID"   # replace with correct primary ID field per feature class

with arcpy.da.UpdateCursor(fc, [source_field, "ASSETID"],
                           where_clause="ASSETID IS NULL OR ASSETID = ''") as cursor:
    for row in cursor:
        row[1] = row[0]
        cursor.updateRow(row)

print("Done. Re-run count query to verify.")
```

After running, execute the pre-work verification query again and confirm the NULL count is 0.

---

### Step 7 — Re-Import Attribute Rules

#### Type A — No Rule Changes Required `⏱ ~5 min`

The exported CSV rules can be re-imported as-is. No Arcade editing needed.

1. Open the **Import Attribute Rules** tool (Data Management > Attribute Rules > Import Attribute Rules).
2. Set **Input Table** to the target feature class.
3. Set **Input CSV File** to the exported CSV from Step 4.
4. Run the tool.
5. Verify in feature class properties that rules are listed and active.

#### Type B — Step 7a: Edit Arcade Expression `⏱ ~5 min`

The ASSETID rule must be updated so it copies from the primary ID field rather than its own separate sequence. This is the human analysis portion — read the exported CSV, understand the current rule structure, and write the corrected expression before importing.

1. Open the exported CSV in a text editor.
2. Locate the attribute rule that populates `ASSETID`.
3. Update the Arcade expression so ASSETID is assigned from the same source as the primary ID field. Pattern:

   **Before (two separate sequences — incorrect):**
   ```arcade
   // ASSETID rule using its own sequence
   var id = NextSequenceValue("assetid_seq");
   return "ASSET" + Text(id, "00000000");
   ```

   **After (copy from primary ID — correct):**
   ```arcade
   // ASSETID copies the value already assigned to the primary ID field
   return $feature.SHELTERID;   // or TR_ID, SIGNID, etc. — confirm per feature class
   ```

   > Options include: (a) using a single sequence for both fields in one rule, (b) setting ASSETID = primary ID in a second calculation rule at Insert, or (c) an Update rule that fires when the primary ID is set. Confirm the approach with the team before committing.

4. Save the updated CSV.

#### Type B — Step 7b: Import `⏱ ~2 min`

1. Open the **Import Attribute Rules** tool and import the updated CSV.
2. Verify in feature class properties that rules are listed and active.

---

### Step 8 — Re-Enable Editor Tracking `⏱ 1–2 min`

**Tool:** ArcGIS Pro or ArcPy

1. In ArcGIS Pro, right-click the feature class → **Properties** → **Editor Tracking** tab.
2. Check **Enable Editor Tracking**.
3. Confirm the correct fields are mapped (created by, created date, last edited by, last edited date).
4. Click **OK**.

```python
import arcpy

fc = r"Database Connections\GISRW01.sde\sdeadm.AST_tree"
arcpy.EnableEditorTracking_management(
    fc,
    creator_field="CREATED_BY",
    creation_date_field="CREATED_DATE",
    last_editor_field="LAST_EDITED_BY",
    last_edit_date_field="LAST_EDITED_DATE",
    add_fields="NO_ADD_FIELDS",
    record_dates_in="UTC"
)
```

> Adjust field names to match the actual schema of each feature class.

---

### Step 9 — Restart Associated Services `⏱ ~2 min`

**Tool:** ArcGIS Server Manager

1. Log in to ArcGIS Server Manager.
2. Navigate to **Services**.
3. Start each service that was stopped in Step 2.
4. Confirm each service shows **Started** status.
5. Open a test map/application and confirm features are visible and ASSETID values appear correctly.
6. Note the time services were restarted in the change log.

---

### Step 10 — Verification and Sign-Off `⏱ ~5 min`

**All feature classes — confirm the backfill was correct:**

- [ ] Re-run the pre-work count query and confirm `missing_assetid_count = 0`.
- [ ] Confirm no duplicates were introduced:

```sql
-- Remaining NULLs (should be 0)
SELECT COUNT(*) AS still_null
FROM [GISRW01].[sdeadm].[<FEATURE_CLASS_NAME>]
WHERE ASSETID IS NULL OR ASSETID = '';

-- Duplicate ASSETIDs (should return no rows)
SELECT ASSETID, COUNT(*) AS cnt
FROM [GISRW01].[sdeadm].[<FEATURE_CLASS_NAME>]
GROUP BY ASSETID
HAVING COUNT(*) > 1;
```

- [ ] Spot-check 3–5 records and confirm ASSETID matches the primary ID field.

**Type B only — confirm the updated attribute rule works for future inserts:**

- [ ] Insert a single test feature in a child version and confirm ASSETID is auto-populated and equals the primary ID field.
- [ ] Discard the test version without posting.

**All feature classes — close out:**

- [ ] Update the ticket status to **Complete** and note: date/time, number of records updated, backup copy name, and any deviations from this workflow.

---

## Rollback Plan

If any step fails or produces unexpected results:

1. Stop all associated services immediately.
2. Delete attribute rules (if partially re-imported).
3. Use the **Append** tool (no truncate) or a versioned reconcile to restore from the backup copy created in Step 1.
4. Re-import the original (unmodified) exported attribute rules CSV.
5. Re-enable editor tracking.
6. Restart services.
7. Raise a new ticket documenting what failed and why.

---

## Notes

- **`TRN_sectrav`** is the feature class where the root-cause delete+insert issue was already confirmed (2026-01-08). The 201 missing ASSETIDs here are likely from that same event. Cross-reference with `Monthly Submission Comments - 20260227.xlsx` ID mapping table before calculating.
- **`Streets` (TASK0320812)** and the **TASK0319535 group** (AST_tree_vaults, LND_outdoor_req_equip_point, TRN_bus_pad, BLD_electrical, BLD_exterior, BLD_mechanical) are listed as related tasks but no missing ID counts or rule types are documented in the source PDF. Investigate and add detail to this document before scheduling work on those feature classes.
- Do **not** use truncate+reload or Append-based workflows on any of these feature classes going forward.
- `OBJECTID` is not a stable join key across delete+insert cycles. Always use `TR_ID`, `ASSETID`, `GlobalID`, or spatial geometry for joins.
