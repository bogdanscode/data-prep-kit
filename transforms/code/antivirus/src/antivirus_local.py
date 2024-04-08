import os
import time

import clamd
from antivirus_transform import AntivirusTransform
from data_processing.data_access import DataAccessLocal
from data_processing.utils import get_logger

INIT_TIMEOUT_SEC=60

def check_clamd():
    logger = get_logger(__name__)
    cd = clamd.ClamdUnixSocket()
    check_end = time.time() + INIT_TIMEOUT_SEC
    while True:
        try:
            cd.ping()
            break
        except Exception as err:
            if time.time() < check_end:
                logger.debug('waiting until clamd is ready...')
                time.sleep(1)
            else:
                logger.error(f"clamd didn't become ready in {INIT_TIMEOUT_SEC} sec. Please check if clamav container is running.")
                raise err
    del cd

# create parameters
input_folder = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "test-data", "input"))
antivirus_params = {
    "antivirus_input_column": "contents",
    "antivirus_output_column": "virus_detection",
}
if __name__ == "__main__":
    check_clamd()
    # Here we show how to run outside of ray
    # Create and configure the transform.
    transform = AntivirusTransform(antivirus_params)
    # Use the local data access to read a parquet table.
    data_access = DataAccessLocal()
    table = data_access.get_table(os.path.join(input_folder, "sample.parquet"))
    print(f"input table: {table}")
    # Transform the table
    table_list, metadata = transform.transform(table)
    print(f"\noutput table: {table_list}")
    print(f"output metadata : {metadata}")
