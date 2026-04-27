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
| TRN_sectrav - ASSETID - Generate ID | `ASSETID` | `'TR' + NextSequenceValue('sdeadm.<assetid_sequence>')` |

> **Note:** Both rules draw from their own independent sequences. This means the two fields can drift out of sync — see Problem 2 below.

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

## OBJECTID Behaviour and Gaps

### How SDE manages OBJECTIDs on SQL Server

In a versioned SDE enterprise geodatabase on SQL Server, OBJECTIDs are **not** managed by a native SQL Server SEQUENCE object. Instead, ArcSDE maintains a single-row table that it increments by a fixed block size — typically **200 or 400** — and then assigns the individual values within that block in-memory itself. This is more efficient than hitting the database for every individual insert.

The practical consequence: when a connection begins inserting rows, it claims an entire block of 200 or 400 OBJECTIDs upfront. Any values in that block that go unused (because the operation completed early, was cancelled, or the connection dropped) are permanently lost on SQL Server. Unlike Oracle — which can recover unused block values via a DBMS_PIPE — SQL Server has no equivalent mechanism.

Because OBJECTIDs only need to be unique and positive for ArcGIS to function correctly, this is by design and not an error. See: [ObjectID of an ArcSDE feature class skipping values (Esri Community, 2011)](https://community.esri.com/t5/data-management-questions/objectid-of-an-arcsde-feature-class-skipping/td-p/707335)

> **Note on two separate gap mechanisms:** The block allocation described here (200–400 values, SDE-managed) is distinct from the 50-value cache used by Arcade attribute rule sequences (`sdeadm.sectravid`, etc.). Both can independently produce gaps in their respective counters, through different mechanisms.

### OBJECTIDs are not reused

When a row is deleted its OBJECTID is permanently retired — it will never be assigned to a new row through normal operations. This means gaps accumulate over the lifetime of the feature class and are expected.

> **File geodatabase exception:** The "Compact" operation on a file GDB *will* defragment and reuse OBJECTIDs, which is why OBJECTIDs are unreliable join keys in file GDB workflows. In an enterprise SDE geodatabase this is not a concern.

### What causes large OBJECTID jumps

| Cause | Notes |
|-------|-------|
| **SDE block allocation — single connection** | Each insert session claims a block of 200 or 400 OBJECTIDs. If the operation uses fewer rows than the block size, the remainder is discarded. A single small insert can produce a forward jump of up to 400. |
| **SDE block allocation — multiple simultaneous connections** | Each concurrent connection claims its own independent 200/400 block. A busy multi-editor session or a bulk load using parallel connections produces multiple non-contiguous blocks and leaves correspondingly larger gaps. |
| **Rows deleted via the Delete Rows GP tool** | Each deleted row permanently retires its OBJECTID. A batch delete of N rows leaves a gap of N at that position in the sequence. |
| **Delete + insert cycle (the root cause of this investigation)** | A submission workflow that deletes all features and re-inserts them claims a fresh SDE block at re-insert time, producing a forward jump equal to the block size plus the count of deleted rows. The gap of exactly 400 in `BLD_electrical` (2431 → 2831) is consistent with one abandoned SDE block. |
| **Versioned edits abandoned without posting** | SDE allocates OBJECTIDs at insert time in the child version, not at reconcile/post time. If a child version is deleted without being posted, those OBJECTIDs are consumed but never appear in the DEFAULT version. |
| **Rolled-back or failed transactions** | The SDE block has already been claimed before the transaction commits. A rollback returns no rows to the table but the block is not reclaimed — the IDs are gone. |

### What does NOT cause jumps in this environment

- **TRUNCATE TABLE** — not used here. All deletions go through the Delete Rows GP tool or versioned edit sessions, which retire OBJECTIDs individually rather than resetting the sequence.
- **Compress** — geodatabase compress moves delta table records to the base table but does not alter OBJECTID values or reset the sequence.

### Maximum OBJECTID value

The OBJECTID field is a 32-bit signed integer with a maximum value of **2,147,483,647 (2^31 − 1)**. For a feature class with far fewer than 20–50 million live rows, reaching this limit through normal use — even with repeated delete+insert cycles — is practically very unlikely. It is worth monitoring if bulk reload workflows run repeatedly over many years.

### Diagnostic value

A sudden OBJECTID jump at a specific timestamp (visible in the archive history table via `GDB_FROM_DATE` / `GDB_TO_DATE`) is strong circumstantial evidence that a bulk delete+insert occurred at that moment. It is not proof by itself, but combined with archive table row counts and timestamps it corroborates the delete+insert pattern confirmed for `TRN_SECTRAV`. A gap of exactly 200 or 400 is especially diagnostic, as it matches one unclaimed SDE block.

---

## Known Problems

Two distinct problems have been observed. They can occur independently and have different root causes.

### Problem 1 — IDs change entirely after reconciliation (delete + insert)

Features exported to the consultant with one ID (e.g., `TR1001088`) come back with a completely different ID (e.g., `TR7141890`). This is caused by the consultant's submission workflow performing a **delete + insert** (Append with truncate, or equivalent full reload) rather than in-place updates. Because the attribute rules are Insert-only, they fire on re-insert and assign brand-new sequence values. The original IDs are permanently overwritten.

Root cause confirmed — see `TROUBLESHOOTING.md` Section 3.

### Problem 2 — TR_ID and ASSETID become out of sync after a bulk Append

Records are inserted with `TR_ID` and `ASSETID` holding **different values** from each other. Both fields have their own Insert-only attribute rule, and each rule draws from its own independent sequence. This is the root of the problem: **two separate sequences cannot be guaranteed to stay in sync.**

The sequences may have started at matching values, but any event that advances one sequence's cache differently from the other will create a permanent numeric offset between them:

- A server restart discards the remaining cached values for whichever sequences were active — if both sequences were at different points in their 50-value cache blocks, they resume at different offsets
- A bulk Append may cross a cache boundary for one sequence but not the other (depending on where each sequence sat in its cache cycle when the load started), permanently shifting them apart
- Any other operation that consumes values from one sequence but not the other has the same effect

Once the offset exists, **every subsequent insert produces a TR_ID and ASSETID that don't match**, because the two counters are now independently tracking different positions.

This is a design-level problem. The only reliable fix is to remove the independent sequence from the ASSETID rule and instead have ASSETID copy `$feature.TR_ID` directly. Two separate sequences have no mechanism to stay aligned — they will always drift eventually.

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
