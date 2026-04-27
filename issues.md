# Issue Summary

_Based on Kirk's email and subsequent discussion._

---

## A. 'Reassigned' Asset Identifiers

**Key clarification:** There are no technical issues with ASSETIDs being 'reassigned' autonomously. Reassignments only occur when a feature is deleted and then re-created — the attribute rule fires on insert and assigns a new ASSETID. An existing, undeleted feature will never have its ASSETID changed.

### AST_tree
Around this time, Franke Jacobs was struggling to perform a high volume of edits in the Asset Registry, causing wider DB performance issues. ArcGIS Pro was introduced to do the edits more efficiently, but all trees were accidentally deleted. The feature class had to be truncated and reloaded. The Attribute Rule that fires the sequence was not deleted before the reload, which caused new IDs to be assigned on re-insert. This was discussed and highlighted in a subsequent meeting as a lesson learned.

### TRN_sectrav
This was flagged when reviewing sidewalks in `TRN_SECTRAV` that were decommissioned or closed for construction (around Cogswell and elsewhere) and then reconstructed nearby. Kirk's analysis counted these as the same feature and classified them as 'reassignments', but they are legitimate delete + re-create operations for physically relocated infrastructure. This was understood and discussed with Justin in the meeting.

### TRN_transit_shelter
Same situation as `AST_tree` — bulk truncate and reload with the sequence-firing Attribute Rule still in place.

---

## B. Asset-Specific ID and ASSETID Mismatch

**Issue:** Both `ASSETID` and the asset-specific ID field (e.g., `TR_ID`) are populated by separate Attribute Rules, each tied to its own database sequence. On occasion — likely due to memory/caching behaviour — a sequence skips a value (+2 instead of +1). Because the two sequences can skip independently, the two fields fall out of sync.

**Fix:** Replace one field's Attribute Rule + sequence with a rule that simply sets `Field 2 = Field 1`. This means only one sequence fires, and any skipped numbers only affect one counter — the two fields stay in sync. Note: where one field carries a prefix (e.g., `TR_`) and the other is a plain integer, the rule needs to account for that formatting difference.

### AST_ped_ramp
A unique sub-case: approximately 8 features appear to have been reloaded, but only one of the two Attribute Rules was deleted before the reload. This explains the observed offset between the two ID fields for those features.

---

## C. (To Be Determined)

Details not yet confirmed.
