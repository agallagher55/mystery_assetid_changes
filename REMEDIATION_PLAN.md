# HRM GIS Missing ASSETID - Remediation Plan

**Date:** 2026-05-19
**Scope:** Enterprise Geodatabase (SDE) - restoration of features whose ASSETIDs no longer exist in GIS but are still referenced by downstream systems
**Related Task:** TASK0316399
**Status of related items:** AST_tree (83,250) and AST_parking_pay_station (2) already resolved.

---

## 1. Rationale

### What "Missing IDs" Means Here

The QC exports (e.g. `QC_LND_hrm_parcel_ASSETID_no_longer_exists.xlsx`) list ASSETIDs that are referenced by downstream systems such as CityWorks but whose corresponding GIS features no longer exist in the live dataset. The features were at some point in GIS, were assigned ASSETIDs, and have since been removed.

The consequence is **orphaned downstream records** - work orders, inspection histories, or asset management records in CityWorks and other systems that point to an ASSETID with no GIS feature behind it. This is distinct from null ASSETIDs on existing features.

Possible causes per feature:
- Feature was deleted as part of a bulk delete+insert workflow (the delete happened but the re-insert received a new ASSETID, leaving the old one without a current GIS record)
- Feature was intentionally retired or deleted for a legitimate operational reason

The correct response depends on which case applies. For each missing ASSETID: if the feature should still exist, restore it from versioned data. If the deletion was intentional, the downstream record should be retired or flagged in the relevant system (CityWorks, DDE, etc.).

### Why This Matters Downstream

| System | Impact of Orphaned ASSETIDs |
|---|---|
| CityWorks | Work orders and inspection records reference an ASSETID that resolves to nothing in GIS - no location, no asset attributes, no geometry |
| DDE | Feed records for parcels or other assets fail to join to GIS, producing null-attribute outputs in downstream consumers |
| Mobile apps (RoadOperation) | Map queries against orphaned IDs return no results; field crews cannot locate assets |

---

## 2. Outstanding Layers

AST_tree and AST_parking_pay_station have been resolved. The remaining layers:

| Layer | Missing ASSETIDs | QC Export Provided | Primary Downstream System |
|---|---|---|---|
| TRN_transit_shelter | 512 | Yes | CityWorks, RoadOperation/Transit Shelter |
| TRN_sectrav | 201 | Yes | CityWorks Assets, CityWorks Map, HRMBaseData, WinterMaintenance |
| AST_SIGN | 33 | Yes | CityWorks Assets, HRMBaseData, Shared All |
| TRN_traffic_calming_infra | 25 | Yes | AGS Geotab View, AGS Traffic Zone WGS84, TrafficCalming |
| LND_hrm_parcel | 3 | Yes | DDE, HRMBaseData, CityworksMap, AGS Property/GovProperty WGS84 |

---

## 3. Reference Sources Available

| Source | What It Provides |
|---|---|
| QC export files (ticket submitter) | List of ASSETIDs known to be missing from GIS - one file per layer |
| Historical GIS versions (available in SDE) | Feature geometry and attributes as they existed at different points in time - primary restore source |
| SDE archive tables (`<layer>_H`) | Row-level insert/delete history with timestamps - used to confirm when a feature was deleted and what its attributes were |

---

## 4. Pre-Maintenance Investigation Phase

Complete this phase before any edits are made. Output is a per-record decision (restore vs. retire) for every ASSETID in each QC file.

### 4.1 Per-Layer Investigation Steps

For each layer:

**Step A - Compare QC export to current live layer**

Open the QC export and the live feature class in ArcGIS Pro. For each ASSETID in the QC file, confirm it is absent from the live layer.

```python
import arcpy

# Load QC export ASSETIDs
qc_ids = set()
# parse ASSETID column from QC export xlsx

# Query live layer
live_ids = set()
with arcpy.da.SearchCursor("TRN_sectrav", ["ASSETID"]) as cursor:
    for row in cursor:
        if row[0]:
            live_ids.add(row[0])

missing = qc_ids - live_ids
print(f"Confirmed missing from live layer: {len(missing)}")
```

**Step B - Check archive table for deletion record**

For each confirmed missing ASSETID, query the archive table to find when the feature was deleted and what its attributes and geometry were at that time.

```python
import arcpy

# Find the most recent record for each missing ASSETID before it was deleted
with arcpy.da.SearchCursor(
    "TRN_sectrav_H",
    ["ASSETID", "TR_ID", "SHAPE@", "GDB_FROM_DATE", "GDB_TO_DATE"],
    where_clause="ASSETID IN ('TR7141856', 'TR7141857')"  # replace with actual IDs
) as cursor:
    for row in cursor:
        print(row)
```

**Step C - Check historical versions for the feature**

Open the relevant historical version in ArcGIS Pro (Connection Properties > Version). Confirm the feature exists in that version with the expected geometry and attributes. This is the restore source if the feature needs to be brought back.

**Step D - Determine restore vs. retire**

For each missing ASSETID, make a determination:

| Signal | Likely Conclusion |
|---|---|
| Feature exists in a historical version with valid geometry and attributes | Restore - was deleted by mistake or as part of a bulk workflow |
| Feature was deleted around the same timestamp as a known bulk delete+insert event (e.g. 2026-01-08 14:59:41 for TRN_sectrav) | Restore - collateral of the same delete+insert workflow |
| Feature was deleted well before any bulk event; no CityWorks work orders exist against that ASSETID | Retire - likely a legitimate removal |
| Feature geometry was superseded by a split, merge, or realignment (new features cover the same area) | Retire old ASSETID; link downstream records to replacement feature's ASSETID |

Document the decision for every ASSETID before proceeding to the maintenance window.

### 4.2 Per-Layer Notes

**TRN_sectrav (201 records)**
The January 2026 delete+insert event (2026-01-08 14:59:41) deleted 62 features. Many of these 201 missing ASSETIDs likely trace back to this and possibly earlier events of the same type. The historical version from before January 8, 2026 is the most important reference source here.

**TRN_transit_shelter (512 records)**
Largest volume. Confirm with the Transit team whether any shelters were legitimately decommissioned between the reference version date and now. Decommissioned shelters should be retired rather than restored. Coordinate with the RoadOperation/Transit Shelter system admin for any records that will be retired.

**AST_SIGN (33 records)**
The mismatch issue (7 records with wrong IDs) was already resolved. These 33 are a separate set of ASSETIDs that no longer have a GIS feature. Cross-reference against HRMBaseData and the Parks/Roads sign inventory to determine if each sign still physically exists.

**LND_hrm_parcel (3 records)**
Smallest and most tractable. The QC file contains records LND1103, LND2043, and LND146534. These are parcels - check the DDE feed and the property management system to confirm current status before restoring. LND146534 was added relatively recently (2025-02-21), which may make it easier to trace.

**TRN_traffic_calming_infra (25 records)**
No mismatch IDs were found in the earlier review. These are purely features no longer in GIS. Cross-reference against the Geotab/Traffic Zone data and any recent road network changes to identify whether infrastructure was removed or simply re-entered under a new ASSETID.

### 4.3 Pre-Work Time Estimates

| Task | Estimated Effort |
|---|---|
| LND_hrm_parcel investigation (3 records) | 1 hour |
| TRN_traffic_calming_infra investigation (25 records) | 2 hours |
| AST_SIGN investigation (33 records) | 2 hours |
| TRN_sectrav investigation (201 records) | 4 hours |
| TRN_transit_shelter investigation + Transit team coordination (512 records) | 6 hours |
| Documentation of restore/retire decisions (all layers) | 2 hours |
| Script preparation and staging test | 3 hours |
| Stakeholder notifications | 1 hour |
| **Total pre-work** | **21 hours (approx. 3 working days)** |

---

## 5. Maintenance Window Procedure

### 5.1 Prerequisites Checklist

- [ ] Per-record restore/retire decision documented for every ASSETID in every QC file
- [ ] Transit team has confirmed which shelters were legitimately decommissioned (TRN_transit_shelter)
- [ ] Historical version identified and confirmed accessible for each layer
- [ ] ArcPy restore scripts tested on staging
- [ ] Full geodatabase backup confirmed within the last 24 hours
- [ ] Per-layer pre-window row count recorded
- [ ] All downstream system owners notified (CityWorks admin, DDE team, Transit, Winter Ops)
- [ ] Retire list prepared for any ASSETIDs that will not be restored (for CityWorks admin to action post-window)
- [ ] Two GIS staff online (one executing, one reviewing)

### 5.2 Step-by-Step Procedure

---

#### STEP 1 - Pre-Window Row Count Baseline (10 min)

Record the current feature count per layer before any edits.

```python
import arcpy

layers = [
    "TRN_transit_shelter", "TRN_sectrav", "AST_SIGN",
    "TRN_traffic_calming_infra", "LND_hrm_parcel"
]
sde_conn = r"C:\Connections\HRM_Production.sde"

for layer in layers:
    result = arcpy.management.GetCount(f"{sde_conn}\\{layer}")
    print(f"{layer}: {result[0]} features")
```

---

#### STEP 2 - Stop All Affected Services (10-15 min)

| Service | Affected Layers |
|---|---|
| CityWorks integration service | TRN_transit_shelter, TRN_sectrav, AST_SIGN |
| RoadOperation / Transit Shelter | TRN_transit_shelter |
| HRMBaseData | TRN_sectrav, AST_SIGN, LND_hrm_parcel |
| WinterMaintenance | TRN_sectrav |
| DDE feed service | LND_hrm_parcel |
| AGS Geotab View / AGS Traffic Zone WGS84 | TRN_traffic_calming_infra |
| TrafficCalming service | TRN_traffic_calming_infra |
| Shared All | AST_SIGN |
| AGS Property WGS84 / AGS GovProperty WGS84 | LND_hrm_parcel |
| CityworksMap | LND_hrm_parcel |

Confirm all show "Stopped" in ArcGIS Server Manager before proceeding.

---

#### STEP 3 - Disable Editor Tracking on Affected Layers (5-10 min)

Prevents the restoration edits from overwriting the original created/modified timestamps with the maintenance account.

```python
import arcpy

sde_conn = r"C:\Connections\HRM_Production.sde"
restore_layers = [
    "TRN_transit_shelter", "TRN_sectrav", "AST_SIGN",
    "TRN_traffic_calming_infra", "LND_hrm_parcel"
]

for layer in restore_layers:
    arcpy.management.DisableEditorTracking(f"{sde_conn}\\{layer}")
    print(f"Editor tracking disabled: {layer}")
```

---

#### STEP 4 - Disable Attribute Rules on Affected Layers (10-15 min)

Critical: if attribute rules are active during the Append, the Insert trigger will fire on every re-appended feature and assign a brand-new ASSETID from the sequence - defeating the entire purpose of the restore. Disable all calculation rules before appending.

**Save the full rule definitions before disabling.**

```python
import arcpy, json

sde_conn = r"C:\Connections\HRM_Production.sde"
restore_layers = [
    "TRN_transit_shelter", "TRN_sectrav", "AST_SIGN",
    "TRN_traffic_calming_infra", "LND_hrm_parcel"
]
rule_backup = {}

for layer in restore_layers:
    fc_path = f"{sde_conn}\\{layer}"
    rules = arcpy.da.ListRules(fc_path)
    rule_backup[layer] = [dict(r) for r in rules]
    arcpy.management.DisableAttributeRules(fc_path, [r['Name'] for r in rules])
    print(f"Rules disabled: {layer}")

with open(r"C:\Temp\rule_backup.json", "w") as f:
    json.dump(rule_backup, f, default=str)
```

---

#### STEP 5 - Execute Restorations (in order, small to large)

All restorations use ArcPy `Append` from the identified historical version as the source. The where clause must filter only to ASSETIDs in the confirmed restore list - do not append features marked for retirement.

##### 5.1 - LND_hrm_parcel (up to 3 features)

```python
import arcpy

historical_conn = r"C:\Connections\HRM_Historical_[version_name].sde"
target_conn = r"C:\Connections\HRM_Production.sde"

restore_ids = ["LND1103", "LND2043", "LND146534"]  # replace with confirmed list
where = "ASSETID IN ('" + "','".join(restore_ids) + "')"

arcpy.management.MakeFeatureLayer(
    f"{historical_conn}\\LND_hrm_parcel", "restore_lyr", where
)
arcpy.management.Append(
    inputs="restore_lyr",
    target=f"{target_conn}\\LND_hrm_parcel",
    schema_type="NO_TEST"
)
print("LND_hrm_parcel restore complete")
```

Validate immediately: row count should have increased by the number of restored features; no null ASSETIDs.

##### 5.2 - TRN_traffic_calming_infra (up to 25 features)

```python
restore_ids = [...]  # from pre-work decision list
where = "ASSETID IN ('" + "','".join(restore_ids) + "')"
arcpy.management.MakeFeatureLayer(
    f"{historical_conn}\\TRN_traffic_calming_infra", "restore_lyr", where
)
arcpy.management.Append(
    "restore_lyr", f"{target_conn}\\TRN_traffic_calming_infra", "NO_TEST"
)
```

##### 5.3 - AST_SIGN (up to 33 features)

```python
restore_ids = [...]
where = "ASSETID IN ('" + "','".join(restore_ids) + "')"
arcpy.management.MakeFeatureLayer(
    f"{historical_conn}\\AST_SIGN", "restore_lyr", where
)
arcpy.management.Append(
    "restore_lyr", f"{target_conn}\\AST_SIGN", "NO_TEST"
)
```

##### 5.4 - TRN_sectrav (up to 201 features)

```python
restore_ids = [...]
where = "ASSETID IN ('" + "','".join(restore_ids) + "')"
arcpy.management.MakeFeatureLayer(
    f"{historical_conn}\\TRN_sectrav", "restore_lyr", where
)
arcpy.management.Append(
    "restore_lyr", f"{target_conn}\\TRN_sectrav", "NO_TEST"
)
```

##### 5.5 - TRN_transit_shelter (up to 512 features, minus confirmed decommissions)

```python
restore_ids = [...]  # pre-work list, excluding confirmed decommissions
where = "ASSETID IN ('" + "','".join(restore_ids) + "')"
arcpy.management.MakeFeatureLayer(
    f"{historical_conn}\\TRN_transit_shelter", "restore_lyr", where
)
arcpy.management.Append(
    "restore_lyr", f"{target_conn}\\TRN_transit_shelter", "NO_TEST"
)
```

---

#### STEP 6 - Post-Edit Validation (15-20 min)

```python
import arcpy

sde_conn = r"C:\Connections\HRM_Production.sde"

for layer in restore_layers:
    result = arcpy.management.GetCount(f"{sde_conn}\\{layer}")
    print(f"{layer}: {result[0]} features (compare to baseline)")

    with arcpy.da.SearchCursor(
        f"{sde_conn}\\{layer}", ["ASSETID"],
        where_clause="ASSETID IS NULL OR ASSETID = ''"
    ) as cursor:
        nulls = sum(1 for _ in cursor)
    print(f"  Null ASSETIDs: {nulls} (expected 0)")
```

All layers must show: zero null ASSETIDs, row count increased by expected number, all restore-list ASSETIDs now present.

---

#### STEP 7 - Re-Enable Attribute Rules (10-15 min)

```python
import arcpy, json

with open(r"C:\Temp\rule_backup.json") as f:
    rule_backup = json.load(f)

sde_conn = r"C:\Connections\HRM_Production.sde"
for layer, rules in rule_backup.items():
    fc_path = f"{sde_conn}\\{layer}"
    arcpy.management.EnableAttributeRules(fc_path, [r['Name'] for r in rules])
    print(f"Rules re-enabled: {layer}")
```

Verify each rule shows "Enabled" in ArcGIS Pro (Feature Class Properties > Attribute Rules) before proceeding.

---

#### STEP 8 - Re-Enable Editor Tracking (5 min)

```python
import arcpy

sde_conn = r"C:\Connections\HRM_Production.sde"
for layer in restore_layers:
    arcpy.management.EnableEditorTracking(
        f"{sde_conn}\\{layer}",
        creator_field="created_user",
        creation_date_field="created_date",
        last_editor_field="last_edited_user",
        last_edit_date_field="last_edited_date",
        add_fields="NO_ADD_FIELDS",
        record_dates_in="UTC"
    )
    print(f"Editor tracking re-enabled: {layer}")
```

---

#### STEP 9 - Restart Services (10-15 min)

Start in dependency order:

1. HRMBaseData
2. DDE feed service
3. AGS Property WGS84 / AGS GovProperty WGS84
4. AGS Geotab View / AGS Traffic Zone WGS84
5. TrafficCalming service
6. RoadOperation / Transit Shelter service
7. WinterMaintenance service
8. Shared All
9. CityworksMap
10. CityWorks integration service (last)

---

#### STEP 10 - Post-Restart Smoke Tests (20-30 min)

- **CityWorks:** Query a sample of restored ASSETIDs from each layer. Confirm they resolve to GIS features with geometry and attributes. Attempt to open an existing work order linked to one restored ASSETID.
- **DDE:** Trigger a manual sync or check the feed log. Confirm LND_hrm_parcel records flow through without null-join errors.
- **WinterMaintenance:** Confirm restored TRN_sectrav segments appear in the maintenance layer.
- **Shared All:** Confirm restored AST_SIGN features are visible and queryable.
- **ArcGIS Pro spot check:** For each restored layer, run Select By Attributes with `ASSETID IN (restored list)` and confirm all features are found.

---

#### STEP 11 - Retire List Hand-Off (same day, post-window)

For any ASSETIDs determined to be intentional deletions (not restored), prepare a retire list per downstream system:

- **CityWorks admin:** List of ASSETIDs per layer to be retired/closed in CityWorks. Work orders against these IDs should be reviewed before closing.
- **DDE team:** List of parcel or asset IDs that no longer have a GIS record and should be flagged in the DDE feed.
- **Transit (if applicable):** Decommissioned shelter IDs to be marked inactive in RoadOperation.

---

## 6. Time Estimate Breakdown

### Pre-Maintenance Window

| Phase | Estimated Duration |
|---|---|
| LND_hrm_parcel investigation (3 records) | 1 hour |
| TRN_traffic_calming_infra investigation (25 records) | 2 hours |
| AST_SIGN investigation (33 records) | 2 hours |
| TRN_sectrav investigation (201 records) | 4 hours |
| TRN_transit_shelter investigation + Transit team coordination (512 records) | 6 hours |
| Documentation of restore/retire decisions | 2 hours |
| ArcPy script preparation and staging test | 3 hours |
| Stakeholder notifications | 1 hour |
| **Total pre-work** | **21 hours (approx. 3 working days)** |

### Maintenance Window

| Step | Activity | Estimated Duration |
|---|---|---|
| 1 | Pre-window row count baseline | 10 min |
| 2 | Stop all services | 15 min |
| 3 | Disable editor tracking | 10 min |
| 4 | Disable attribute rules (save definitions) | 15 min |
| 5.1 | LND_hrm_parcel restore + validate (3 features) | 10 min |
| 5.2 | TRN_traffic_calming_infra restore + validate (25) | 15 min |
| 5.3 | AST_SIGN restore + validate (33) | 15 min |
| 5.4 | TRN_sectrav restore + validate (201) | 20 min |
| 5.5 | TRN_transit_shelter restore + validate (up to 512) | 25 min |
| 6 | Post-edit validation | 15 min |
| 7 | Re-enable attribute rules | 15 min |
| 8 | Re-enable editor tracking | 5 min |
| 9 | Restart services in order | 15 min |
| 10 | Post-restart smoke tests | 25 min |
| Buffer | Unexpected issues / rollback time | 30 min |
| **Total maintenance window** | | **3.5 to 4 hours** |

**Recommended window to book: 5 hours.**

---

## 7. Impact of Performing This During Working Hours

The procedure requires stopping all services listed in Step 2 for the full duration of the maintenance window (3.5-4 hours minimum). The following are the explicit reasons why this must not be done during business hours.

### Reasons to Perform Outside Business Hours

**1. CityWorks field crews cannot access work orders.**
CityWorks is the primary asset management system for field operations. Stopping the CityWorks integration service and CityworksMap means field crews cannot view, create, update, or close work orders against any of the affected asset types (transit shelters, trail segments, signs, traffic calming infrastructure, parcels). During business hours this directly interrupts active field operations.

**2. HRMBaseData is a widely shared dependency.**
HRMBaseData is not just used by the affected layers - it underpins many map viewers and applications across the organization. Stopping it during business hours causes a broad, visible outage that extends well beyond the teams involved in this work. Any application that references HRMBaseData as a base layer will lose map content for the duration of the window.

**3. DDE feeds are interrupted and downstream systems receive stale data.**
The DDE feed service syncs LND_hrm_parcel data to downstream consumers. Stopping it mid-business-day breaks the feed for however long the window runs. Downstream consumers that poll on a schedule during business hours will either fail or consume a previous cycle's data, with no indication that the data is stale.

**4. Transit operations lose live shelter data.**
The RoadOperation/Transit Shelter service supports Transit operations staff who need live shelter location and condition data during their operating hours. Stopping this service during business hours removes that visibility for the duration of the window.

**5. WinterMaintenance route data becomes unavailable.**
TRN_sectrav is the backbone of WinterMaintenance routing. During active winter operations (November-March), stopping the WinterMaintenance service during a shift is operationally unacceptable - it removes route segment data from operators in the field. Even outside peak winter season, a daytime outage is disruptive to planning and dispatch.

**6. Shared All affects inter-departmental and potentially public-facing services.**
AST_SIGN data is consumed by the Shared All service. Stopping it during business hours removes AST_SIGN layer access for any inter-departmental or public-facing viewers that depend on it.

**7. Traffic engineering and fleet management lose access to traffic calming and zone data.**
AGS Geotab View, AGS Traffic Zone WGS84, and the TrafficCalming service are used by traffic engineering and fleet management teams during the work day. Stopping them removes visibility into traffic calming infrastructure and zone boundaries for the duration of the window.

**8. The window must be long enough to allow for rollback.**
The recommended window is 5 hours to accommodate a potential rollback. Starting a 5-hour window during business hours would push the end time deep into active operating hours and leave no option to extend without further disruption. Outside business hours there is more room to absorb unexpected delays.

**9. Concurrent editing increases the risk of conflicts and data integrity issues.**
If staff are actively editing any of the affected feature classes during the window - for example, a GIS editor making routine updates in ArcGIS Pro - their edits could conflict with the Append operations or complicate the validation results. Performing the work outside business hours eliminates this risk.

### Summary

| Downstream System | Affected User Groups | Impact During Window |
|---|---|---|
| CityWorks | Field crews, work order admins, inspectors | Work orders linked to transit shelters, sectrav segments, signs cannot be accessed or actioned |
| RoadOperation / Transit Shelter | Transit operations | No live shelter location/condition data |
| WinterMaintenance | Winter operations staff | TRN_sectrav-based route segments unavailable (critical Nov-Mar) |
| DDE | Downstream property/parcel consumers | LND_hrm_parcel feed interrupted; downstream systems see stale parcel data |
| Shared All | Inter-departmental / public-facing viewers | AST_SIGN layer unavailable |
| HRMBaseData | Any map viewer referencing this service | Broad base layer outage affecting many teams |
| AGS Geotab View / Traffic Zone / TrafficCalming | Traffic engineering, fleet management | Traffic calming infrastructure and zone data unavailable |

**Preferred window: Saturday or Sunday, 6:00-7:00 AM start.** CityWorks field crew activity is minimal on weekends. DDE feeds resync naturally after services restart. Enough lead time exists before normal Monday operations resume if the window runs long.

**Weeknight fallback (after 6:00 PM):** Acceptable if a weekend is not available. A 5-hour window starting at 7:00 PM ends at midnight; tight if rollback is needed but workable.

**WinterMaintenance note:** If a storm event is forecast within 48 hours of the scheduled window, defer - TRN_sectrav downtime during active winter operations is operationally significant.

---

## 8. Risks and Rollback

### Risk 1 - Append Introduces Duplicates

If features have already been partially restored in a previous session or re-entered manually, the Append will create duplicate features with the same ASSETID.

**Mitigation:** Re-run the absence check (Step A of Section 4.1) immediately before each Append in Step 5 to confirm the ASSETID is still absent from the live layer.

**Detection:** Post-edit validation checks for duplicate ASSETIDs. Halt if any found.

**Rollback:** Delete the duplicate features (the newly appended ones will have the highest OBJECTIDs) using a versioned delete in ArcGIS Pro. Resolve before proceeding to Step 7.

### Risk 2 - Attribute Rule Fires on Append Despite Being Disabled

If rules are set to enabled at the database level rather than the geodatabase level, disabling via ArcPy may not prevent them from firing during an Append.

**Mitigation:** After disabling in Step 4, confirm each rule shows "Disabled" in ArcGIS Pro > Feature Class Properties > Attribute Rules. Run a test Append of one feature in a child version first and confirm the ASSETID was not overwritten before running on production.

**Detection:** Post-edit validation in Step 6 checks that restored ASSETIDs match the expected values from the restore list.

**Rollback:** Delete the incorrectly-appended features by OBJECTID, fix the rule disable method, and retry.

### Risk 3 - Historical Version Does Not Contain the Expected Features

If the historical version was snapshotted after the deletion event rather than before, the missing features will not be in it.

**Mitigation:** During pre-work, confirm the version date is prior to the archive table deletion timestamps for the features in question. Verify at least one missing ASSETID is visible in the historical version before scripting the restore.

**Detection:** The `MakeFeatureLayer` in Step 5 returns 0 features for the where clause.

**Recovery:** Identify an earlier version that predates the deletion, or use the SDE archive table (`_H`) directly as the restore source, filtered to the correct state using `GDB_TO_DATE`.

### Risk 4 - Retire List Not Actioned Before CityWorks Users Resume

If the retire list is not handed off before field crews start their day, users may continue to see and create work orders against ASSETIDs confirmed as intentionally deleted.

**Mitigation:** Complete Step 11 immediately after the window closes. Brief the CityWorks admin before the window so they are ready to act as soon as the list is produced.

---

## 9. Summary Action Items Before Scheduling the Window

| Priority | Action | Owner |
|---|---|---|
| HIGH | Complete per-record restore/retire decisions for all 5 layers | GIS Analyst |
| HIGH | Confirm historical version dates predate deletion events for each layer | GIS Admin |
| HIGH | Coordinate with Transit team on decommissioned shelters (TRN_transit_shelter) | GIS Lead |
| HIGH | Test ArcPy Append restore scripts on staging geodatabase | GIS Admin |
| MEDIUM | Notify CityWorks admin, DDE admin, Transit Ops, Winter Ops | GIS Lead |
| MEDIUM | Book weekend maintenance window with IT/GIS ops (5 hours) | GIS Lead |
| MEDIUM | Prepare retire list template for CityWorks and DDE hand-off | GIS Analyst |
| LOW | Document editor tracking field names per layer (needed for Step 8) | GIS Analyst |
