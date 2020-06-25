# coding=utf-8
# Copyright 2019-present, the HuggingFace Inc. team.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import unittest
from doctest import DocTestSuite
from typing import List, Union
import logging

import transformers

from .utils import require_tf, require_torch, slow

logger = logging.getLogger()


@require_torch
@require_tf
@slow
class TestCodeExamples(unittest.TestCase):
    def analyze_directory(
            self,
            directory: str,
            identifier: Union[str, None] = None,
            ignore_files: Union[List[str], None] = [],
            n_identifier: Union[str, None] = None
    ):
        """
        Runs through the specific directory, looking for the files identified with `identifier`. Executes
        the doctests in those files

        Args:
            directory (:obj:`str`): Directory containing the files
            identifier (:obj:`str`): Will parse files containing this
            ignore_files (:obj:`List[str]`): List of files to skip
            n_identifier (:obj:`str` or :obj:`List[str]`): Will not parse files containing this/these identifiers.
        """
        files = [file for file in os.listdir(directory) if os.path.isfile(os.path.join(directory, file))]

        if identifier is not None:
            files = [file for file in files if identifier in file]

        if n_identifier is not None:
            if isinstance(n_identifier, List):
                for n_ in n_identifier:
                    files = [file for file in files if n_ not in file]
            else:
                files = [file for file in files if n_identifier not in file]

        ignore_files.append("__init__.py")
        files = [file for file in files if file not in ignore_files]

        for file in files:
            # Open all files
            print("Testing", file)
            module_identifier = file.split(".")[0]

            try:
                module_identifier = getattr(transformers, module_identifier)
                suite = DocTestSuite(module_identifier)
                result = unittest.TextTestRunner().run(suite)
                self.assertIs(len(result.failures), 0)
            except AttributeError:
                logger.info(f"{module_identifier} is not user-facing.")

    def test_modeling_examples(self):
        transformers_directory = "src/transformers"
        files = "modeling"
        ignore_files = [
            "modeling_ctrl.py",
            "modeling_tf_ctrl.py",
        ]
        self.analyze_directory(transformers_directory, identifier=files, ignore_files=ignore_files)

    def test_tokenization_examples(self):
        transformers_directory = "src/transformers"
        files = "tokenization"
        self.analyze_directory(transformers_directory, identifier=files)

    def test_configuration_examples(self):
        transformers_directory = "src/transformers"
        files = "configuration"
        self.analyze_directory(transformers_directory, identifier=files)

    def test_remaining_examples(self):
        transformers_directory = "src/transformers"
        n_identifiers = ["configuration", "modeling", "tokenization"]
        self.analyze_directory(transformers_directory, n_identifier=n_identifiers)

    def test_doc_sources(self):
        doc_source_directory = "docs/source"
        self.analyze_directory(doc_source_directory)
