import os
import arcpy
import logging
import datetime

import pandas as pd

from configparser import ConfigParser

from HRMutils import setupLog

arcpy.env.overwriteOutput = True
arcpy.SetLogHistory(False)

config = ConfigParser()
config.read('config.ini')

logFile = os.path.join(os.getcwd(), f"{datetime.date.today()}_loggies.log")
logger = setupLog(logFile)

console_handler = logging.StreamHandler()
log_formatter = logging.Formatter(
    '%(asctime)s | %(levelname)s | FUNCTION: %(funcName)s | Msgs: %(message)s', datefmt='%d-%b-%y %H:%M:%S'
)
console_handler.setFormatter(log_formatter)
logger.addHandler(console_handler)  # print logs to console
logger.setLevel(logging.DEBUG)


def get_attr_rule_tables(sde_conn):

    # 1. Initialize connection to the enterprise database
    sql_executor = arcpy.ArcSDESQLExecute(sde_conn)

    # 2. Define and execute your SQL statement
    with open("../attr_rule_tables.sql", "r") as file:
        sql_statement = file.read()

    attr_rule_table_info = sql_executor.execute(sql_statement)

    agg_field_table_info = {x[0]: [] for x in attr_rule_table_info}

    for table in attr_rule_table_info:

        table_name = table[0]
        rule_name = table[1]
        arcade_exp = table[2]
        field_name = table[3]
        rule_type = table[4]
        is_enabled = True if table[5] == 'true' else False

        rule_info = {
            'rule_name': rule_name,
            'arcade_exp': arcade_exp,
            'field_name': field_name,
            'rule_type': rule_type,
            'is_enabled': is_enabled,
        }

        print(f"\t{table_name}: {field_name}\t\t {arcade_exp}")

        agg_field_table_info[table_name].append(rule_info)

    return agg_field_table_info


if __name__ == "__main__":

    for dbs in [
        [
            config.get("SERVER", "dev_rw"),
        ],
        # [
        #     config.get("SERVER", "qa_rw"),
        # ],
        # [
        #     config.get("SERVER", "prod_rw"),
        # ],

    ]:

        for count, db in enumerate(dbs, start=1):
            logger.info(f"{count}/{len(dbs)}) Database: {db}")

            table_info = get_attr_rule_tables(db)

            # Need to know if more than one rule exists
            multi_attr_fields_info = {k: v for k, v in table_info.items() if len(v) > 1}

            # Create DataFrame
            rows = []
            for feature_class, rules in multi_attr_fields_info.items():
                for rule in rules:
                    rows.append({'feature_class': feature_class, **rule})

            df = pd.DataFrame(rows, columns=['feature_class', 'field_name', 'rule_name', 'rule_type', 'arcade_exp',
                                             'is_enabled'])

            print(df.to_string(index=False))

            df.to_excel("features_multi_attr_rules.xlsx", index=False)

            for info in multi_attr_fields_info:

                print(info)

                # TODO: Export rules
                # TODO: Delete rules
                # TODO: Disable Editor tracking

                # TODO: Make changes

                # TODO: Import rules
                # TODO: Enable Editor Tracking

