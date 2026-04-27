# Email Thread: For April 27 Meeting — Upcoming Asset Identifier Meeting

---

## Kirk's Email

**From:** Mills, Kirk  
**To:** Landry, Jillian  
**CC:** White, Allen  
**Date:** Thursday, April 23, 2026  
**Subject:** Upcoming Asset Identifier Meeting

Kirk's email is the source document for the three issues documented in `issues.md`. It was written ahead of the April 27 meeting with AMO and GIS to align on asset identifier behaviour and remediation options.

See `issues.md` for the full breakdown of Issues A, B, and C.

---

## Lisa's Email

**From:** O'Toole, Lisa  
**To:** Landry, Jillian; Marvin, Tristan; Chang, Justin; Gallagher, Alex; Akyol, Reyhan; Potter, Michael  
**Date:** Friday, April 25, 2026 (before the April 27 meeting)  
**Subject:** RE: For April 27 meeting — Upcoming Asset Identifier Meeting

### Summary

Lisa forwarded findings from Justin Chang's investigation of the **Building Component** tables, adding her own high-level observations. She was off on Friday and sent this ahead of the Monday meeting so Alex and Mike could review before it started.

### Key Observations

- **Earliest known occurrence:** 2026-02-09
- **Two categories of tables behave differently:**
  - `BLD_ELECTRICAL` and `BLD_EXTERIOR`: mismatches appear only in records **appended directly to the table**; records added through the Asset Registry Editor are fine.
  - `BLD_LIFESAFETY` and `BLD_MECHANICAL`: mismatches appear in records added through **both** the Asset Registry Editor and direct appends — a wider problem.
- **ASSETID / asset-specific ID out of sync** for appended records across all four tables; in some tables this also affects records added through the Asset Registry Editor.
- **Significant, irregular jumps in Object IDs** throughout the tables — suggesting bulk inserts or sequence resets at specific dates.
- In some tables, Object IDs are **not in chronological order** for records added through the Asset Registry, which is unexpected.

### Table-by-Table Detail (from Justin Chang's report, forwarded by Lisa)

| Table | Records affected | Method | Notes |
|-------|-----------------|--------|-------|
| `BLD_electrical` | ~3 | Direct append (2026-03-09) | OBJECTID jumped 2431 → 2831; ElectricalID jumped ELC2287 → ELC2318; AssetID jumped to ELC2326 — out of sync with ElectricalID |
| `BLD_exterior` | ~3 | Direct append (2026-03-09) | AssetID out of sync for appended records only; OBJECTID did not jump on append but did jump for Asset Registry records (2024-07-15/16); Exterior IDs not sequential relative to ObjectIDs |
| `BLD_lifesafety` | 1 | Asset Registry Editor (2026-03-25) | Significant jump in both ObjectID and LifeSafetyID; AssetID out of sync |
| `BLD_mechanical` | ~15 | Asset Registry Editor (2026-02-09, 2026-03-06) + direct append (2026-03-09) | ObjectID jumped ~400 multiple times via Asset Registry Editor, then ~412 via append; AssetID drifts progressively further out of sync as ObjectIDs increase; inconsistent with other BLD tables |

### Open Question

Justin asked whether **different attribute rules apply for appended records vs. records added through the Asset Registry Editor** — this is the crux of why behaviour differs between the two methods and between tables.
