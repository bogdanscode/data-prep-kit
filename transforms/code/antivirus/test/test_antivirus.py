import os
import time
from typing import Tuple

import clamd
import pyarrow as pa
from data_processing.test_support.transform.transform_test import AbstractTransformTest
from data_processing.utils import get_logger
from antivirus_transform import AntivirusTransform


INIT_TIMEOUT_SEC=60
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

table = pa.Table.from_pydict({
            'document_id': ['ID_1', 'ID_2'],
            'contents': ['INNOCENT', 'X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*'],
        })
expected_table = pa.Table.from_pydict({
            'document_id': ['ID_1', 'ID_2'],
            'contents': ['INNOCENT', 'X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*'],
            'virus_detection': [None, 'Win.Test.EICAR_HDB-1'],
        })
expected_metadata_list = [{"clean": 1, "infected": 1}, {}]  # transform() result  # flush() result


class TestAntivirusTransform(AbstractTransformTest):
    """
    Extends the super-class to define the test data for the tests defined there.
    The name of this class MUST begin with the word Test so that pytest recognizes it as a test class.
    """

    def get_test_transform_fixtures(self) -> list[Tuple]:
        fixtures = [
            (
                AntivirusTransform(
                    {
                        "antivirus_input_column": "contents", 
                        "antivirus_output_column": "virus_detection"
                    }
                ),
                [table],
                [expected_table],
                expected_metadata_list
            ),
        ]
        return fixtures