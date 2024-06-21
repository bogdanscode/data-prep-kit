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

import io
import json
import logging
import zipfile
from argparse import ArgumentParser, Namespace
from datetime import datetime
from typing import Any

import pyarrow as pa
import ray
from data_processing.data_access import (
    DataAccess,
    DataAccessFactory,
    DataAccessFactoryBase,
)
from data_processing.runtime.pure_python.runtime_configuration import (
    PythonTransformRuntimeConfiguration,
)
from data_processing.transform import AbstractBinaryTransform, TransformConfiguration
from data_processing.utils import TransformUtils, str2bool
from data_processing_ray.runtime.ray import (
    DefaultRayTransformRuntime,
    RayTransformLauncher,
)
from data_processing_ray.runtime.ray.runtime_configuration import (
    RayTransformRuntimeConfiguration,
)
from ray.actor import ActorHandle


shortname = "code2parquet"
cli_prefix = f"{shortname}_"
supported_langs_file_key = f"{shortname}_supported_langs_file"
supported_languages = f"{shortname}_supported_languages"
data_factory_key = f"{shortname}_data_factory"
detect_programming_lang_key = f"{shortname}_detect_programming_lang"
domain_key = f"{shortname}_domain"
snapshot_key = f"{shortname}_snapshot"


def _get_supported_languages(lang_file: str, data_access: DataAccess, logger: logging.Logger) -> dict[str, str]:
    logger.debug(f"Getting supported languages from file {lang_file}")
    json_data, _ = data_access.get_file(lang_file)
    lang_dict = json.loads(json_data.decode("utf-8"))
    reversed_dict = {ext: langs for langs, exts in lang_dict.items() for ext in exts}
    logger.debug(f"Supported languages {reversed_dict}")
    return reversed_dict


class CodeToParquetTransform(AbstractBinaryTransform):
    """ """

    def __init__(self, config: dict):
        """
        Initialize based on the dictionary of configuration information.
        This is generally called with configuration parsed from the CLI arguments defined
        by the companion runtime, LangSelectorTransformRuntime.  If running inside the RayMutatingDriver,
        these will be provided by that class with help from the RayMutatingDriver.
        """

        super().__init__(config)
        from data_processing.utils import get_logger

        self.logger = get_logger(__name__)
        self.domain = config.get(domain_key, "")
        self.snapshot = config.get(snapshot_key, "")
        self.detect_programming_lang = config.get(detect_programming_lang_key, "")
        supported_languages_ref = config.get(supported_languages, None)
        if supported_languages_ref is None:
            path = config.get(supported_langs_file_key, None)
            if path is None:
                raise RuntimeError(f"Missing configuration value for key {supported_langs_file_key}")
            daf = config.get(data_factory_key, None)
            data_access = daf.create_data_access()
            self.languages_supported = _get_supported_languages(
                lang_file=path, data_access=data_access, logger=self.logger
            )
        else:
            # This is recommended for production approach. In this case domain list is build by the
            # runtime once, loaded to the object store and can be accessed by actors without additional reads
            try:
                self.logger.info(
                    f"Loading languages to include from Ray storage under reference {supported_languages_ref}"
                )
                self.languages_supported = ray.get(supported_languages_ref)
            except Exception as e:
                self.logger.warning(f"Exception loading languages list from ray object storage {e}")
                raise RuntimeError(f"exception loading from object storage for key {supported_languages_ref}")

    def _get_lang_from_ext(self, ext):
        lang = "unknown"
        if ext is not None:
            lang = self.languages_supported.get(ext, lang)
        return lang

    def transform_binary(self, file_name: str, byte_array: bytes) -> tuple[list[tuple[bytes, str]], dict[str, Any]]:
        """
        Converts raw data file (ZIP) to Parquet format
        """
        # We currently only process .zip files
        if TransformUtils.get_file_extension(file_name)[1] != ".zip":
            self.logger.warning(f"Got unsupported file type {file_name}, skipping")
            return [], {}
        data = []
        number_of_rows = 0
        with zipfile.ZipFile(io.BytesIO(bytes(byte_array))) as opened_zip:
            # Loop through each file member in the ZIP archive
            for member in opened_zip.infolist():
                if not member.is_dir():
                    with opened_zip.open(member) as file:
                        try:
                            # Read the content of the file
                            content_bytes = file.read()
                            # Decode the content
                            content_string = TransformUtils.decode_content(content_bytes)
                            if content_string and len(content_string) > 0:
                                ext = TransformUtils.get_file_extension(member.filename)[1]
                                row_data = {
                                    "title": member.filename,
                                    "document": TransformUtils.get_file_basename(file_name),
                                    "contents": content_string,
                                    "document_id": TransformUtils.str_to_hash(content_string),
                                    "ext": ext,
                                    "hash": TransformUtils.str_to_hash(content_string),
                                    "size": len(content_string),
                                    "date_acquired": datetime.now().isoformat(),
                                }
                                if self.detect_programming_lang:
                                    lang = self._get_lang_from_ext(ext)
                                    row_data["programming_language"] = lang
                                data.append(row_data)
                                number_of_rows += 1
                            else:
                                self.logger.warning(
                                    f"file {member.filename} is empty. content {content_string}, skipping"
                                )
                        except Exception as e:
                            self.logger.warning(f"Exception {str(e)} processing file {member.filename}, skipping")
        table = pa.Table.from_pylist(data)
        return [(TransformUtils.convert_arrow_to_binary(table=table), ".parquet")], {"number of rows": number_of_rows}


class CodeToParquetRuntime(DefaultRayTransformRuntime):
    """
    Ingest to Parquet runtime support
    """

    def __init__(self, params: dict[str, Any]):
        """
        Create filter runtime
        :param params: parameters, that should include
            ingest_supported_langs_file_key: supported languages file
            ingest_detect_programming_lang_key: whether to detect programming language
            ingest_domain_key: domain
            ingest_snapshot_key: snapshot
        """
        super().__init__(params)
        from data_processing.utils import get_logger

        self.logger = get_logger(__name__)

    def get_transform_config(
        self,
        data_access_factory: DataAccessFactoryBase,
        statistics: ActorHandle,
        files: list[str],
    ) -> dict[str, Any]:
        """
        Set environment for filter execution
        :param data_access_factory - data access factory
        :param statistics - reference to the statistics object
        :param files - list of files to process
        :return: dictionary of filter init params
        """
        lang_file = self.params.get(supported_langs_file_key, None)
        if lang_file is None:
            raise RuntimeError(f"Missing configuration key {supported_langs_file_key}")
        lang_data_access_factory = self.params.get(data_factory_key, None)
        if lang_data_access_factory is None:
            raise RuntimeError(f"Missing configuration key {data_factory_key}")
        lang_dict = _get_supported_languages(
            lang_file=lang_file,
            data_access=lang_data_access_factory.create_data_access(),
            logger=self.logger,
        )
        lang_refs = ray.put(lang_dict)
        self.logger.debug(f"Placed language list into Ray object storage under reference{lang_refs}")
        return {supported_languages: lang_refs} | self.params


class CodeToParquetTransformConfiguration(TransformConfiguration):
    """
    Provides support for configuring and using the associated Transform class include
    configuration with CLI args and combining of metadata.
    """

    def __init__(self):
        super().__init__(
            name=shortname,
            transform_class=CodeToParquetTransform,
            remove_from_metadata=[data_factory_key],
        )
        from data_processing.utils import get_logger

        self.logger = get_logger(__name__)
        self.daf = None

    def add_input_params(self, parser: ArgumentParser) -> None:
        """
        Add Transform-specific arguments to the given parser.
        This will be included in a dictionary used to initialize the ProgLangMatchTransform.
        By convention a common prefix should be used for all mutator-specific CLI args
        (e.g, noop_, pii_, etc.)
        """
        parser.add_argument(
            f"--{supported_langs_file_key}",
            type=str,
            default=None,
            help="Path to file containing the list of supported languages",
        )
        parser.add_argument(
            f"--{detect_programming_lang_key}",
            type=lambda x: bool(str2bool(x)),
            default=True,
            help="generate programming lang",
        )
        parser.add_argument(f"--{snapshot_key}", type=str, help="Name the dataset", default="")
        parser.add_argument(
            f"--{domain_key}",
            type=str,
            help="To identify whether data is code or natural language",
            default="",
        )
        # Create the DataAccessFactor to use CLI args
        self.daf = DataAccessFactory(cli_prefix, False)
        # Add the DataAccessFactory parameters to the transform's configuration parameters.
        self.daf.add_input_params(parser)

    def apply_input_params(self, args: Namespace) -> bool:
        """
        Validate and apply the arguments that have been parsed
        :param args: user defined arguments.
        :return: True, if validate pass or False otherwise
        """
        dargs = vars(args)
        if dargs.get(supported_langs_file_key, None) is None:
            self.logger.warning(f"{supported_langs_file_key} is required, but got None")
            return False
        self.params = {
            detect_programming_lang_key: dargs.get(detect_programming_lang_key, None),
            supported_langs_file_key: dargs.get(supported_langs_file_key, ""),
            domain_key: dargs.get(domain_key, ""),
            snapshot_key: dargs.get(snapshot_key, ""),
            data_factory_key: self.daf,
        }
        self.logger.info(f"Transform configuration {self.params}")

        # Validate and populate the transform's DataAccessFactory
        return self.daf.apply_input_params(args)


class CodeToParquetPythonConfiguration(PythonTransformRuntimeConfiguration):
    def __init__(self):
        super().__init__(transform_config=CodeToParquetTransformConfiguration())


class CodeToParquetRayConfiguration(RayTransformRuntimeConfiguration):
    def __init__(self):
        super().__init__(transform_config=CodeToParquetTransformConfiguration(), runtime_class=CodeToParquetRuntime)


if __name__ == "__main__":
    launcher = RayTransformLauncher(CodeToParquetRayConfiguration())
    launcher.launch()