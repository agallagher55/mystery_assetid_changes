# mystery_assetid_changes

Investigation into unexpectedly changing Asset IDs in the `[GISRW01].[sdeadm].[TRN_SECTRAV]` enterprise geodatabase feature class at Halifax Regional Municipality (HRM).

---

## Background

On March 4, 2026, Kirk brought to the attention of the GIS team that trail segment `ASSETID` and `TR_ID` values were changing after consultant data was reconciled back into the enterprise geodatabase. The issue affects **TRN_SECTRAV** (trail segments) and has also been observed on Bus Pads and other layers.

The problem manifests as:
- Features that were exported to consultant (Eagle) with one ID (e.g., `TR1001088`) are returned bearing a completely different ID (e.g., `TR7141890`).
- The sequence `sdeadm.sectravid` has advanced to the 7-million range despite far fewer live features existing.
- A mapping of 30+ known Original_ID → New_ID pairs has been compiled by Kirk.

---

## How IDs Are Generated

Two Insert-only attribute rules govern ID assignment:

| Rule | Field | Expression |
|------|-------|------------|
| TRN_sectrav - TR_ID - Generate ID | `TR_ID` | `'TR' + NextSequenceValue('sdeadm.sectravid')` |
| TRN_sectrav - ASSETID - Generate ID | `ASSETID` | `$feature.TR_ID` |

Because both rules fire **on Insert only**, IDs should never change on an existing feature. The fact that they are changing means features are being **deleted and re-inserted** somewhere in the reconciliation workflow, rather than being updated in place.

---

## Repository Contents

| File | Description |
|------|-------------|
| `TROUBLESHOOTING.md` | Full diagnostic and remediation plan — start here |
| `CLAUDE.md` | AI assistant context: domain glossary, table names, conventions |
| `Monthly Submission Comments - 20260227.xlsx` | Known ID mapping table and submission notes |

---

## Quick Start

1. **Read `TROUBLESHOOTING.md`** for the full investigation plan, SQL diagnostic queries, and recommended fixes.
2. **Answer the open questions** in Section 10 of the troubleshooting doc — particularly confirming the exact reconciliation method (Append? Python script? FME? Replica check-in?).
3. **Run the diagnostic queries** in Section 2 against the enterprise GDB to establish facts before making any changes.
4. **Do not attempt data remediation** (Section 8) until the root cause is confirmed and the workflow is corrected.

---

## Suspected Root Cause

The reconciliation workflow is most likely using `arcpy.Append_management()`, a truncate+reload, or a disconnected replica check-in — all of which perform a delete+insert rather than an in-place update. This causes the Insert-only attribute rules to fire and assign new IDs from the sequence.

**Preferred fix:** Switch to a proper geodatabase versioning workflow (child version → Reconcile & Post to Default) so that feature updates never trigger the Insert rules.

---

## Contacts

| Name | Role |
|------|------|
| Justin Chang | GIS — investigation lead |
| Marcela Soto Trujillo | GIS |
| Alex Gallagher | GIS |
| Kirk | Field/data — identified the issue |
| Eagle (consultant) | External data collector |
