# Mystery Asset ID Changes

Investigation into unexpectedly changing Asset IDs in the `[GISRW01].[sdeadm].[TRN_SECTRAV]` enterprise geodatabase feature class at Halifax Regional Municipality (HRM).

---

## Background

On March 4, 2026, Kirk brought to the attention of the GIS team that trail segment `ASSETID` and `TR_ID` values were changing after consultant data was reconciled back into the enterprise geodatabase. The issue affects **TRN_SECTRAV** (trail segments) and has also been observed on Bus Pads and other layers.

The problem manifests as:
- Features that were exported to consultant (Eagle) with one ID (e.g., `TR1001088`) are returned bearing a completely different ID (e.g., `TR7141890`).
- The sequence `sdeadm.sectravid` has advanced to the 7-million range despite far fewer live features existing.
- A mapping of 30+ known Original_ID → New_ID pairs has been compiled by Kirk.

---

## Editing Methods

Features in the enterprise geodatabase can be edited through two routes:

- **ArcGIS Pro (desktop)** — direct connection to the SDE geodatabase. Edits happen inside a versioned edit session and are reconciled/posted back to the Default version. Attribute rules fire normally on insert.
- **Online service (ArcGIS Enterprise / Feature Service)** — features are edited through a hosted feature service backed by the same SDE data. This route may behave differently with respect to attribute rules, sequence consumption, and how edits are committed — and is a candidate factor in the ID skipping and mismatch issues.

Understanding which editing method was used for a given batch of records is key to diagnosing both the sequence-skipping (Issue B) and any duplicate/mismatch behaviour.

---

## How IDs Are Generated

Two Insert-only attribute rules govern ID assignment:

| Rule | Field | Expression |
|------|-------|------------|
| TRN_sectrav - TR_ID - Generate ID | `TR_ID` | `'TR' + NextSequenceValue('sdeadm.sectravid')` |
| TRN_sectrav - ASSETID - Generate ID | `ASSETID` | `$feature.TR_ID` |

Because both rules fire **on Insert only**, IDs should never change on an existing feature. The fact that they are changing means features are being **deleted and re-inserted** somewhere in the reconciliation workflow, rather than being updated in place.

### Sequence Cache and ID Gaps

The `sdeadm.sectravid` sequence (and all other sequences in the geodatabase) uses SQL Server's **default cache size of 50**. This means SQL Server pre-allocates the next 50 sequence values in memory at once rather than hitting disk for every insert.

**Implication for this investigation:** If the server restarts or the sequence cache is flushed for any reason, up to 49 pre-allocated but unused values are permanently discarded, and the sequence jumps to the next uncached block. This is the normal explanation for non-consecutive TR_ID numbers — gaps in the sequence do **not** by themselves indicate missing features or a problem.

However, this also means the sequence advancing into the 7-million range (despite far fewer live features) is consistent with repeated cycles of bulk inserts consuming large blocks of cached values — especially if the delete+insert workflow has been run multiple times across different layers (Bus Pads, TRN_SECTRAV, etc.).

### Multiple Sequences Per Feature: Independent Cache States

If a feature class has two attribute rules each drawing from a **different** sequence, those sequences maintain completely independent cache states. Each has its own current position within its 50-value block, and neither is aware of the other.

During a bulk load this matters because:

- Sequence A might be near the **end** of its current cache block (e.g., position 48 of 50) when the bulk insert starts. After just 2 rows it exhausts the block, discards any remaining values, and fetches the next block of 50 — creating an apparent gap.
- Sequence B might be near the **start** of its cache block (e.g., position 3 of 50) at the same moment. The same bulk insert of, say, 10 rows doesn't push it past the cache boundary at all — no gap.

So **yes, it is entirely normal for one sequence to skip values during a bulk load while another does not.** It simply depends on where each sequence happened to be sitting in its cache cycle at the moment the inserts began — which is essentially random from the perspective of any given operation.

The practical takeaway: if you observe that `TR_ID` values jumped but a corresponding field from a second sequence did not (or vice versa), that asymmetry is expected behavior and does not indicate a deeper problem with one sequence over the other. It is not a useful diagnostic signal for determining whether a delete+insert occurred — the archive table timestamps remain the most reliable evidence for that.

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
