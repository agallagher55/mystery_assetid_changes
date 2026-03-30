"""
audit_attribute_rules_id_sync.py

Audits all sdeadm feature classes for attribute rules that use database sequences,
identifies feature classes with two ID-type fields (one sequence-generated, one mirror),
and reports records where those two ID fields are out of sync.

Outputs:
    - Dated log file (file + console)
    - <logDir>/<module>/YYYY-MM-DD_<script>_rules.csv  -- one row per matching rule
    - <logDir>/<module>/YYYY-MM-DD_<script>_sync.csv   -- one row per FC checked for sync
"""

import sys
import os
import re
import csv
import datetime
import time
import traceback
import logging
import arcpy

from collections import defaultdict
from configparser import ConfigParser

from HRMutils import setupLog, send_mail

# ---------------------------------------------------------------------------
# Directory / file setup
# ---------------------------------------------------------------------------
WORKING_DIR = os.path.dirname(sys.path[0])
WD_FOLDER_NAME = os.path.basename(WORKING_DIR)
FILE_NAME = os.path.basename(__file__)
FILE_NAME_BASE = os.path.splitext(FILE_NAME)[0]
SCRATCH_DIR = os.path.join(WORKING_DIR, "Scratch")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
config = ConfigParser()
config.read("config.ini")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
log_dir = os.getcwd()
os.makedirs(log_dir, exist_ok=True)

log_file = os.path.join(log_dir, f"{str(datetime.date.today())}_{FILE_NAME_BASE}.log")
logger = setupLog(log_file)

console_handler = logging.StreamHandler()
log_formatter = logging.Formatter(
    "%(asctime)s | %(levelname)s | FUNCTION: %(funcName)s | Msgs: %(message)s",
    datefmt="%d-%b-%y %H:%M:%S",
)
console_handler.setFormatter(log_formatter)
logger.addHandler(console_handler)

arcpy.SetLogHistory(False)
arcpy.env.overwriteOutput = True

# ---------------------------------------------------------------------------
# SDE connections
# ---------------------------------------------------------------------------
SDEADM_RW = config.get("SERVER", "qa_rw")
# SDEADM_RW = config.get("SERVER", "prod_rw")

# ---------------------------------------------------------------------------
# CSV output paths
# ---------------------------------------------------------------------------
today = str(datetime.date.today())
RULES_CSV = os.path.join(log_dir, f"{today}_{FILE_NAME_BASE}_rules.csv")
SYNC_CSV = os.path.join(log_dir, f"{today}_{FILE_NAME_BASE}_sync.csv")

# Regex helpers
_RE_SEQUENCE = re.compile(r"NextSequenceValue\s*\(\s*'([^']+)'\s*\)", re.IGNORECASE)
_RE_MIRROR = re.compile(r"\$feature\.(\w+)", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Helper: extract numeric portion of an ID value for sorting/comparison
# ---------------------------------------------------------------------------
def _numeric_part(value):

    """Return the integer portion of an ID string (e.g. 'TR7141890' -> 7141890)."""
    if value is None:
        return -1

    digits = re.sub(r"[^0-9]", "", str(value))

    return int(digits) if digits else -1


# ---------------------------------------------------------------------------
# Function 1: get_attribute_rules
# ---------------------------------------------------------------------------
def get_attribute_rules(sde_conn):

    """
    Walk all feature classes in the sdeadm workspace and collect attribute rules
    that reference a database sequence (NextSequenceValue) or mirror another field
    ($feature.<FIELD>).

    Returns:
        list[dict] -- one dict per matching rule with keys:
            feature_class, rule_name, rule_type, triggering_events, field,
            script_expression, is_sequence_rule, is_mirror_rule,
            sequence_name, mirror_source_field, id_rule_count_for_fc
    """

    logger.info("=" * 60)
    logger.info("STEP 1 — Scanning sdeadm feature classes for attribute ...")
    logger.info("=" * 60)

    all_rules = []
    fc_scanned = 0
    fc_with_rules = 0

    for dirpath, _datasets, fcs in arcpy.da.Walk(sde_conn, datatype="FeatureClass"):

        for feature_name in fcs:
            print(feature_name)

            if "AST_ped_ramp" not in feature_name:
                continue

            fc_path = os.path.join(dirpath, feature_name)
            fc_scanned += 1

            try:
                desc = arcpy.Describe(fc_path)

            except Exception:
                logger.warning(f"Could not describe {feature_name} — skipping")
                continue

            # attributeRules returns an empty list if none are defined
            rules = getattr(desc, "attributeRules", [])
            if not rules:
                continue

            matching_rules = []

            for rule in rules:

                expr = getattr(rule, "scriptExpression", "") or ""

                is_sequence = bool(_RE_SEQUENCE.search(expr))
                is_mirror = bool(_RE_MIRROR.search(expr))

                if not (is_sequence or is_mirror):
                    continue

                seq_match = _RE_SEQUENCE.search(expr)
                mir_match = _RE_MIRROR.search(expr)

                triggering = getattr(rule, "triggeringEvents", [])

                if isinstance(triggering, (list, tuple)):
                    triggering_str = "|".join(triggering)

                else:
                    triggering_str = str(triggering)

                field_name = getattr(rule, "fieldName", "")
                rule_name = getattr(rule, "name", "")
                rule_type = getattr(rule, "type", "")

                matching_rules.append({
                    "feature_class": feature_name,
                    "rule_name": rule_name,
                    "rule_type": rule_type,
                    "triggering_events": triggering_str,
                    "field": field_name,
                    "script_expression": expr,
                    "is_sequence_rule": is_sequence,
                    "is_mirror_rule": is_mirror,
                    "sequence_name": seq_match.group(1) if seq_match else "",
                    "mirror_source_field": mir_match.group(1) if mir_match else "",
                })

            if not matching_rules:
                continue

            # Count ID-type rules per FC and attach to each rule row
            id_rule_count = len(matching_rules)
            for r in matching_rules:
                r["id_rule_count_for_fc"] = id_rule_count

            seq_count = sum(1 for r in matching_rules if r["is_sequence_rule"])
            mir_count = sum(1 for r in matching_rules if r["is_mirror_rule"])
            logger.info(
                f"  {feature_name}: {id_rule_count} ID rule(s) found "
                f"[sequence={seq_count}, mirror={mir_count}]"
            )

            all_rules.extend(matching_rules)
            fc_with_rules += 1

    logger.info("-" * 60)
    logger.info(f"Scanned {fc_scanned} feature class(es)")
    logger.info(f"  {fc_with_rules} have sequence/mirror attribute rules")
    logger.info(
        f"  {sum(1 for r in all_rules if r['is_sequence_rule'] and r['is_mirror_rule'] == False)} "
        "sequence rules total"
    )
    logger.info(
        f"  {sum(1 for r in all_rules if r['is_mirror_rule'])} mirror rules total"
    )

    dual_id_fcs = {
        fc
        for fc, rules in _group_by_fc(all_rules).items()
        if any(r["is_sequence_rule"] for r in rules)
        and any(r["is_mirror_rule"] for r in rules)
    }
    logger.info(f"  {len(dual_id_fcs)} feature class(es) have BOTH sequence + mirror rules (dual-ID pattern)")

    return all_rules


def _group_by_fc(rules):
    """Group a flat list of rule dicts by feature_class."""
    grouped = defaultdict(list)
    for r in rules:
        grouped[r["feature_class"]].append(r)
    return grouped


def check_id_sync(sde_conn, fc_rules):
    """
    For each feature class that has both a sequence rule and a mirror rule,
    compare the two ID fields and report records where they are out of sync.

    Args:
        sde_conn (str): path to read-only SDE connection file
        fc_rules (list[dict]): output from get_attribute_rules()

    Returns:
        list[dict] -- one dict per FC checked with keys:
            feature_class, primary_field, secondary_field, is_versioned,
            total_records, mismatch_count, latest_primary_id,
            pct_in_sync
    """

    logger.info("=" * 60)
    logger.info("STEP 2 — Checking ID field sync for dual-ID feature classes")
    logger.info("=" * 60)

    grouped = _group_by_fc(fc_rules)
    sync_results = []

    for fc_name, rules in grouped.items():

        seq_rules = [r for r in rules if r["is_sequence_rule"]]
        mirror_rules = [r for r in rules if r["is_mirror_rule"]]

        # Case 1: two sequence rules — compare them directly
        if len(seq_rules) >= 2 and not mirror_rules:
            if len(seq_rules) > 2:
                logger.warning(
                    f"  {fc_name}: {len(seq_rules)} sequence rules found — "
                    "using the first two; review manually if unexpected"
                )
            primary_field = seq_rules[0]["field"]
            secondary_field = seq_rules[1]["field"]

        # Case 2: one sequence rule + one mirror rule — original pattern
        elif seq_rules and mirror_rules:
            if len(seq_rules) > 1:
                logger.warning(
                    f"  {fc_name}: {len(seq_rules)} sequence rules found — "
                    "using the first one; review manually if unexpected"
                )
            if len(mirror_rules) > 1:
                logger.warning(
                    f"  {fc_name}: {len(mirror_rules)} mirror rules found — "
                    "using the first one; review manually if unexpected"
                )
            primary_field = seq_rules[0]["field"]
            secondary_field = mirror_rules[0]["field"]

        else:
            logger.info(f"  {fc_name}: skipped — needs either two sequence rules or one sequence + one mirror rule")
            continue

        # Build the cursor target — use _evw view for versioned FCs
        try:
            fc_path = os.path.join(sde_conn, fc_name)
            is_versioned = arcpy.Describe(fc_path).isVersioned

        except Exception:
            logger.warning(f"  {fc_name}: could not determine versioning — using base FC path")
            is_versioned = False

        cursor_target = (fc_path + "_evw") if is_versioned else fc_path

        total = 0
        mismatches = 0
        mismatch_ids = []
        max_numeric = -1
        latest_primary_id = None

        try:

            with arcpy.da.SearchCursor(cursor_target, [primary_field, secondary_field]) as cur:

                for row in cur:
                    primary_val, secondary_val = row
                    total += 1

                    # Track latest (highest) primary ID
                    numeric = _numeric_part(primary_val)
                    if numeric > max_numeric:
                        max_numeric = numeric
                        latest_primary_id = primary_val

                    # Compare; treat None/null as mismatched
                    if primary_val != secondary_val:
                        mismatches += 1
                        if len(mismatch_ids) < 20:
                            mismatch_ids.append(str(primary_val))

        except Exception:
            logger.error(
                f"  {fc_name}: error reading cursor on {cursor_target}",
                exc_info=True,
            )
            continue

        pct_in_sync = round((total - mismatches) / total * 100, 2) if total else 0.0

        logger.info(f"  {fc_name}:")
        logger.info(f"    Primary field  : {primary_field}")
        logger.info(f"    Secondary field: {secondary_field}")
        logger.info(f"    Versioned      : {is_versioned}")
        logger.info(f"    Total records  : {total:,}")
        logger.info(f"    Mismatches     : {mismatches:,}  ({100 - pct_in_sync:.2f}% out of sync)")
        logger.info(f"    Latest primary ID: {latest_primary_id}")

        if mismatch_ids:
            display = mismatch_ids[:20]
            suffix = " ... (truncated)" if mismatches > 20 else ""
            logger.info(f"    Mismatch sample: {', '.join(display)}{suffix}")

        sync_results.append({
            "feature_class": fc_name,
            "primary_field": primary_field,
            "secondary_field": secondary_field,
            "is_versioned": is_versioned,
            "total_records": total,
            "mismatch_count": mismatches,
            "latest_primary_id": latest_primary_id,
            "pct_in_sync": pct_in_sync,
        })

    logger.info("-" * 60)
    fcs_with_mismatches = sum(1 for r in sync_results if r["mismatch_count"] > 0)
    logger.info(f"Checked {len(sync_results)} dual-ID feature class(es)")
    logger.info(f"  {fcs_with_mismatches} have out-of-sync ID fields")

    return sync_results


# ---------------------------------------------------------------------------
# CSV writers
# ---------------------------------------------------------------------------
def _write_rules_csv(rules, path):

    if not rules:
        logger.warning("No matching rules to write — rules CSV will not be created")
        return

    fieldnames = [
        "feature_class", "rule_name", "rule_type", "triggering_events",
        "field", "is_sequence_rule", "is_mirror_rule", "sequence_name",
        "mirror_source_field", "id_rule_count_for_fc", "script_expression",
    ]

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rules:
            writer.writerow({k: row.get(k, "") for k in fieldnames})

    logger.info(f"Rules CSV written: {path}  ({len(rules)} rows)")


def _write_sync_csv(sync_results, path):

    if not sync_results:

        logger.warning("No sync results to write — sync CSV will not be created")
        return

    fieldnames = [
        "feature_class", "primary_field", "secondary_field", "is_versioned",
        "total_records", "mismatch_count", "latest_primary_id", "pct_in_sync",
    ]

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in sync_results:
            writer.writerow({k: row.get(k, "") for k in fieldnames})

    logger.info(f"Sync CSV written: {path}  ({len(sync_results)} rows)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():

    start_time = time.asctime(time.localtime(time.time()))
    logger.info(f"Start: {start_time}")
    logger.info(f"Script: {FILE_NAME}")
    logger.info(f"SDE connection: {SDEADM_RW}")

    # Step 1 — attribute rule scan
    with arcpy.EnvManager(workspace=SDEADM_RW):
        rules = get_attribute_rules(SDEADM_RW)

    _write_rules_csv(rules, RULES_CSV)

    dual_id_count = len({
        fc for fc, rs in _group_by_fc(rules).items()
        if any(r["is_sequence_rule"] for r in rs) and any(r["is_mirror_rule"] for r in rs)
    })

    logger.info(
        f"SUMMARY — Step 1: {len(rules)} ID rule(s) found across feature classes; "
        f"{dual_id_count} FC(s) have the dual-ID pattern"
    )

    # Step 2 — ID sync check
    sync_results = check_id_sync(SDEADM_RW, rules)
    _write_sync_csv(sync_results, SYNC_CSV)

    fcs_out_of_sync = sum(1 for r in sync_results if r["mismatch_count"] > 0)
    logger.info(
        f"SUMMARY — Step 2: {len(sync_results)} FC(s) checked; "
        f"{fcs_out_of_sync} FC(s) have out-of-sync ID fields"
    )

    logger.info("-" * 60)
    end_time = time.asctime(time.localtime(time.time()))
    logger.info(f"End: {end_time}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
try:
    main()

except:
    tb = sys.exc_info()[2]
    tbinfo = traceback.format_tb(tb)[0]
    pymsg = (
        "PYTHON ERRORS:\nTraceback Info:\n" + tbinfo
        + "\nError Info:\n    "
        + str(sys.exc_info()[0]) + ": " + str(sys.exc_info()[1]) + "\n"
    )
    logger.error(pymsg)

    # send_mail(
    #     to=str(config.get("EMAIL", "recipients")).split(","),
    #     subject=f"ERROR - {FILE_NAME_BASE} Failed",
    #     text=f"{log_server} / {FILE_NAME} \n\n{pymsg}",
    # )

    sys.exit()
