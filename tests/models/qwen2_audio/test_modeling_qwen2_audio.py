# coding=utf-8
# Copyright 2024 The HuggingFace Inc. team. All rights reserved.
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
"""Testing suite for the PyTorch Qwen2Audio model."""

import gc
import unittest

import requests

from transformers import (
    AutoProcessor,
    AutoTokenizer,
    Qwen2AudioConfig,
    Qwen2AudioForConditionalGeneration,
    is_torch_available,
)
from transformers.testing_utils import (
    require_torch,
    slow,
    torch_device,
)

from ...test_configuration_common import ConfigTester
from ...test_modeling_common import ModelTesterMixin, floats_tensor, ids_tensor


if is_torch_available():
    import torch
else:
    is_torch_greater_or_equal_than_2_0 = False

from transformers.pipelines.audio_utils import ffmpeg_read


class Qwen2AudioModelTester:
    def __init__(
        self,
        parent,
        ignore_index=-100,
        audio_token_index=0,
        seq_length=7,
        feat_seq_length=60,
        text_config={
            "model_type": "qwen2",
            "intermediate_size": 36,
            "initializer_range": 0.02,
            "hidden_size": 32,
            "max_position_embeddings": 52,
            "num_hidden_layers": 2,
            "num_attention_heads": 4,
            "num_key_value_heads": 2,
            "use_labels": True,
            "use_mrope": False,
            "vocab_size": 99,
        },
        is_training=True,
        audio_config={
            "model_type": "qwen2_audio_encoder",
            "d_model": 16,
            "encoder_attention_heads": 4,
            "encoder_ffn_dim": 16,
            "encoder_layers": 2,
            "num_mel_bins": 80,
            "max_source_positions": 30,
            "initializer_range": 0.02,
        },
    ):
        self.parent = parent
        self.ignore_index = ignore_index
        self.audio_token_index = audio_token_index
        self.text_config = text_config
        self.audio_config = audio_config
        self.seq_length = seq_length
        self.feat_seq_length = feat_seq_length

        self.num_hidden_layers = text_config["num_hidden_layers"]
        self.vocab_size = text_config["vocab_size"]
        self.hidden_size = text_config["hidden_size"]
        self.num_attention_heads = text_config["num_attention_heads"]
        self.is_training = is_training

        self.batch_size = 3
        self.encoder_seq_length = audio_config["max_source_positions"] // 2 + seq_length - 1

    def get_config(self):
        return Qwen2AudioConfig(
            text_config=self.text_config,
            audio_config=self.audio_config,
            ignore_index=self.ignore_index,
            audio_token_index=self.audio_token_index,
        )

    def prepare_config_and_inputs(self):
        input_features_values = floats_tensor(
            [
                self.batch_size,
                self.audio_config["num_mel_bins"],
                self.feat_seq_length,
            ]
        )
        config = self.get_config()
        feature_attention_mask = (
            (ids_tensor([self.batch_size, self.feat_seq_length], config.text_config.vocab_size - 1) + 1)
            .ne(1)
            .long()
            .to(torch_device)
        )
        return config, input_features_values, feature_attention_mask

    def prepare_config_and_inputs_for_common(self):
        config_and_inputs = self.prepare_config_and_inputs()
        config, input_features_values, feature_attention_mask = config_and_inputs
        input_ids = ids_tensor([self.batch_size, self.seq_length], config.text_config.vocab_size - 1) + 1
        attention_mask = torch.ones(input_ids.shape, dtype=torch.long).to(torch_device)
        attention_mask[:, :1] = 0
        # we are giving 3 audios let's make sure we pass in 3 audios tokens
        input_ids[:, 1] = config.audio_token_index
        inputs_dict = {
            "input_features": input_features_values,
            "feature_attention_mask": feature_attention_mask,
            "input_ids": input_ids,
            "attention_mask": attention_mask,
        }
        return config, inputs_dict

    def create_and_check_qwen2audio_model_fp16_forward(self, config, input_ids, pixel_values, attention_mask):
        model = Qwen2AudioForConditionalGeneration(config=config)
        model.to(torch_device)
        model.eval()
        with torch.autocast(device_type="cuda", dtype=torch.float16):
            logits = model(
                input_ids=input_ids,
                attention_mask=attention_mask,
                pixel_values=pixel_values.to(torch.bfloat16),
                return_dict=True,
            )["logits"]
        self.parent.assertFalse(torch.isnan(logits).any().item())


@require_torch
class Qwen2AudioForConditionalGenerationModelTest(ModelTesterMixin, unittest.TestCase):
    """
    Model tester for `Qwen2AudioForConditionalGeneration`.
    """

    all_model_classes = (Qwen2AudioForConditionalGeneration,) if is_torch_available() else ()
    test_pruning = False
    test_head_masking = False

    def setUp(self):
        self.model_tester = Qwen2AudioModelTester(self)
        self.config_tester = ConfigTester(self, config_class=Qwen2AudioConfig, has_text_modality=False)

    @unittest.skip(
        reason="This architecure seem to not compute gradients properly when using GC, check: https://github.com/huggingface/transformers/pull/27124"
    )
    def test_training_gradient_checkpointing(self):
        pass

    @unittest.skip(
        reason="This architecure seem to not compute gradients properly when using GC, check: https://github.com/huggingface/transformers/pull/27124"
    )
    def test_training_gradient_checkpointing_use_reentrant(self):
        pass

    @unittest.skip(
        reason="This architecure seem to not compute gradients properly when using GC, check: https://github.com/huggingface/transformers/pull/27124"
    )
    def test_training_gradient_checkpointing_use_reentrant_false(self):
        pass

    @unittest.skip(reason="Compile not yet supported because in LLava models")
    def test_sdpa_can_compile_dynamic(self):
        pass

    @unittest.skip(reason="Compile not yet supported because in LLava models")
    def test_sdpa_can_dispatch_on_flash(self):
        pass


@require_torch
class Qwen2AudioForConditionalGenerationIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.processor = AutoProcessor.from_pretrained("Qwen/Qwen2-Audio-7B")

    def tearDown(self):
        gc.collect()
        torch.cuda.empty_cache()

    @slow
    def test_small_model_integration_test_single(self):
        # Let' s make sure we test the preprocessing to replace what is used
        model = Qwen2AudioForConditionalGeneration.from_pretrained("Qwen/Qwen2-Audio-7B")

        prompt = "<|audio_bos|><|AUDIO|><|audio_eos|>Detect the language and recognize the speech:"
        url = "https://qianwen-res.oss-cn-beijing.aliyuncs.com/Qwen2-Audio/audio/1272-128104-0000.flac"
        raw_audio = ffmpeg_read(
            requests.get(url).content, sampling_rate=self.processor.feature_extractor.sampling_rate
        )

        inputs = self.processor(text=prompt, audios=raw_audio, return_tensors="pt")

        EXPECTED_INPUT_IDS = torch.tensor([[151647, 151646, 151648, 57193, 279, 4128, 323, 15282, 279, 8806, 25]])
        self.assertTrue(torch.equal(inputs["input_ids"], EXPECTED_INPUT_IDS))

        output = model.generate(**inputs, max_new_tokens=32)
        EXPECTED_DECODED_TEXT = "<|audio_bos|><|AUDIO|><|audio_eos|>Detect the language and recognize the speech:<|en|>mister quilter is the apostle of the middle classes and we are glad to welcome his gospel<|endoftext|>"

        self.assertEqual(
            self.processor.decode(output[0], skip_special_tokens=False),
            EXPECTED_DECODED_TEXT,
        )

    @slow
    def test_small_model_integration_test_batch(self):
        # Let' s make sure we test the preprocessing to replace what is used
        model = Qwen2AudioForConditionalGeneration.from_pretrained("Qwen/Qwen2-Audio-7B")

        prompts = [
            "<|audio_bos|><|AUDIO|><|audio_eos|>Detect the language and recognize the speech:",
            "<|audio_bos|><|AUDIO|><|audio_eos|>Generate the caption in English:",
            "<|audio_bos|><|AUDIO|><|audio_eos|>Classify the human vocal sound to VocalSound in English:",
        ]
        url1 = "https://qianwen-res.oss-cn-beijing.aliyuncs.com/Qwen2-Audio/audio/1272-128104-0000.flac"
        audio1 = ffmpeg_read(requests.get(url1).content, sampling_rate=self.processor.feature_extractor.sampling_rate)
        url2 = "https://qianwen-res.oss-cn-beijing.aliyuncs.com/Qwen2-Audio/audio/glass-breaking-151256.mp3"
        audio2 = ffmpeg_read(requests.get(url2).content, sampling_rate=self.processor.feature_extractor.sampling_rate)
        url3 = "https://qianwen-res.oss-cn-beijing.aliyuncs.com/Qwen2-Audio/audio/f2641_0_throatclearing.wav"
        audio3 = ffmpeg_read(requests.get(url3).content, sampling_rate=self.processor.feature_extractor.sampling_rate)

        inputs = self.processor(text=prompts, audios=[audio1, audio2, audio3], return_tensors="pt", padding=True)

        output = model.generate(**inputs, max_new_tokens=32)
        print(self.processor.batch_decode(output, skip_special_tokens=True))

        EXPECTED_DECODED_TEXT = [
            "Detect the language and recognize the speech:mister quilter is the apostle of the middle classes and we are glad to welcome his gospel",
            "Generate the caption in English: Glass is breaking.",
            "Classify the human vocal sound to VocalSound in English: Throat clearing",
        ]
        self.assertEqual(
            self.processor.batch_decode(output, skip_special_tokens=True),
            EXPECTED_DECODED_TEXT,
        )

    def test_tokenizer_integration(self):
        slow_tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen2-Audio-7B", use_fast=False)
        fast_tokenizer = AutoTokenizer.from_pretrained(
            "Qwen/Qwen2-Audio-7B",
            from_slow=True,
            legacy=False,
        )

        prompt = "<|im_start|>system\nAnswer the questions.<|im_end|><|im_start|>user\n<|audio_bos|><|AUDIO|><|audio_eos|>\nWhat is it in this audio?<|im_end|><|im_start|>assistant\n"
        EXPECTED_OUTPUT = [
            "<|im_start|>",
            "system",
            "Ċ",
            "Answer",
            "Ġthe",
            "Ġquestions",
            ".",
            "<|im_end|>",
            "<|im_start|>",
            "user",
            "Ċ",
            "<|audio_bos|>",
            "<|AUDIO|>",
            "<|audio_eos|>",
            "Ċ",
            "What",
            "Ġis",
            "Ġit",
            "Ġin",
            "Ġthis",
            "Ġaudio",
            "?",
            "<|im_end|>",
            "<|im_start|>",
            "assistant",
            "Ċ",
        ]
        print(slow_tokenizer.tokenize(prompt))
        self.assertEqual(slow_tokenizer.tokenize(prompt), EXPECTED_OUTPUT)
        self.assertEqual(fast_tokenizer.tokenize(prompt), EXPECTED_OUTPUT)