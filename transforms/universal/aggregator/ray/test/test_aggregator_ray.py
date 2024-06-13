# (C) Copyright IBM Corp. 2024.
# Licensed under the Apache License, Version 2.0 (the “License”);
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#  http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an “AS IS” BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
################################################################################

import os

from data_processing.test_support.launch.transform_test import (
    AbstractTransformLauncherTest
)
from data_processing.test_support import get_files_in_folder
from data_processing_ray.runtime.ray import RayTransformLauncher
from aggregator_transform_ray import AggregateRayTransformConfiguration


class TestRayAggregatorTransform(AbstractTransformLauncherTest):
    """
    Extends the super-class to define the test data for the tests defined there.
    The name of this class MUST begin with the word Test so that pytest recognizes it as a test class.
    """

    def get_test_transform_fixtures(self) -> list[tuple]:
        basedir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../test-data"))
        config = {
            "run_locally": True,
            # When running in ray, our Runtime's get_transform_config() method  will load the domains using
            # the orchestrator's DataAccess/Factory. So we don't need to provide the bl_local_config configuration.
            # aggregator parameters
            "aggregator_aggregator_cpu": 0.5,
            "aggregator_num_aggregators": 2,
            "aggregator_doc_column": "contents",
        }
        launcher = RayTransformLauncher(AggregateRayTransformConfiguration())
        fixtures = [(launcher, config, basedir + "/input", basedir + "/expected")]
        return fixtures

    def _validate_directory_contents_match(self, dir: str, expected: str, ignore_columns: list[str] = []):
        # Compare files
        f_set1 = get_files_in_folder(dir=dir, ext=".csv", return_data=False)
        f_set2 = get_files_in_folder(dir=expected, ext=".csv", return_data=False)
        assert len(f_set1) == len(f_set2)

        # Compare metadata
        f_set1 = get_files_in_folder(dir=dir, ext=".json", return_data=False)
        f_set2 = get_files_in_folder(dir=expected, ext=".json", return_data=False)
        assert len(f_set1) == len(f_set2)