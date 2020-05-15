# coding=utf-8
# Copyright 2020 Huggingface
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
from shutil import copyfile

from transformers.tokenization_marian import MarianTokenizer, save_json, vocab_files_names
from transformers.file_utils import cached_property
from transformers.convert_marian_to_pytorch import ORG_NAME
from .test_tokenization_common import TokenizerTesterMixin
from .utils import slow
from .utils import require_torch, slow, torch_device
from pathlib import Path


SAMPLE_SP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures/test_sentencepiece.model")

mock_tokenizer_config = {"target_lang": "fi", "source_lang": "en"}
class MarianTokenizationTest(TokenizerTesterMixin, unittest.TestCase):

    tokenizer_class = MarianTokenizer

    def setUp(self):
        super().setUp()
        vocab = ["l", "o", "w", "e", "r", "s", "t", "i", "d", "n",
                 "\u0120", "\u0120l", "\u0120n", "\u0120lo", "\u0120low", "er", "\u0120lowest", "\u0120newer", "\u0120wider", "<unk>",
                 "<pad>"]
        vocab_tokens = dict(zip(vocab, range(len(vocab))))
        save_dir = Path(self.tmpdirname)
        save_json(vocab_tokens, save_dir/ vocab_files_names['vocab'])
        save_json(mock_tokenizer_config, save_dir/ vocab_files_names['tokenizer_config_file'])
        if not (save_dir/vocab_files_names['source_spm']).exists():
            copyfile(SAMPLE_SP, save_dir/ vocab_files_names['source_spm'])
            copyfile(SAMPLE_SP, save_dir / vocab_files_names['target_spm'])

        tokenizer = MarianTokenizer.from_pretrained(self.tmpdirname)
        tokenizer.save_pretrained(self.tmpdirname)


    def get_tokenizer(self, **kwargs):
        return MarianTokenizer.from_pretrained(self.tmpdirname, **kwargs)

    def get_input_output_texts(self):
        input_text = "This is a test"
        output_text = "This is a test"
        return input_text, output_text

    def test_tokenizer_equivalence_en_de(self):
        en_de_tokenizer = MarianTokenizer.from_pretrained(f'{ORG_NAME}opus-mt-en-de')
        batch = en_de_tokenizer.prepare_translation_batch(["I am a small frog"], return_tensors=None)
        expected = [38, 121, 14, 697, 38848, 0]
        self.assertListEqual(expected, batch.input_ids[0])
