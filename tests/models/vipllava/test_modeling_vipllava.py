# coding=utf-8
# Copyright 2023 The HuggingFace Inc. team. All rights reserved.
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
"""Testing suite for the PyTorch VipLlava model."""

import gc
import unittest

import requests

from transformers import (
    AutoProcessor,
    VipLlavaConfig,
    VipLlavaForConditionalGeneration,
    is_torch_available,
    is_vision_available,
)
from transformers.testing_utils import require_bitsandbytes, require_torch, require_torch_gpu, slow, torch_device

from ...generation.test_utils import GenerationTesterMixin
from ...test_configuration_common import ConfigTester
from ...test_modeling_common import ModelTesterMixin, floats_tensor, ids_tensor


if is_torch_available():
    import torch
else:
    is_torch_greater_or_equal_than_2_0 = False

if is_vision_available():
    from PIL import Image


# Copied from transformers.tests.models.llava.test_modeling_llava.LlavaVisionText2TextModelTester with Llava->VipLlava
class VipLlavaVisionText2TextModelTester:
    # Ignore copy
    def __init__(
        self,
        parent,
        ignore_index=-100,
        image_token_index=0,
        projector_hidden_act="gelu",
        seq_length=7,
        vision_feature_layers=[0, 0, 1, 1, 0],
        text_config={
            "model_type": "llama",
            "seq_length": 7,
            "is_training": True,
            "use_input_mask": True,
            "use_token_type_ids": False,
            "use_labels": True,
            "vocab_size": 99,
            "hidden_size": 32,
            "num_hidden_layers": 2,
            "num_attention_heads": 4,
            "intermediate_size": 37,
            "hidden_act": "gelu",
            "hidden_dropout_prob": 0.1,
            "attention_probs_dropout_prob": 0.1,
            "max_position_embeddings": 512,
            "type_vocab_size": 16,
            "type_sequence_label_size": 2,
            "initializer_range": 0.02,
            "num_labels": 3,
            "num_choices": 4,
            "pad_token_id": 1,
        },
        is_training=True,
        vision_config={
            "batch_size": 12,
            "image_size": 30,
            "patch_size": 2,
            "num_channels": 3,
            "is_training": True,
            "hidden_size": 32,
            "projection_dim": 32,
            "num_hidden_layers": 2,
            "num_attention_heads": 4,
            "intermediate_size": 37,
            "dropout": 0.1,
            "attention_dropout": 0.1,
            "initializer_range": 0.02,
        },
    ):
        self.parent = parent
        self.ignore_index = ignore_index
        self.image_token_index = image_token_index
        self.projector_hidden_act = projector_hidden_act
        self.vision_feature_layers = vision_feature_layers
        self.text_config = text_config
        self.vision_config = vision_config
        self.pad_token_id = text_config["pad_token_id"]

        self.num_hidden_layers = text_config["num_hidden_layers"]
        self.vocab_size = text_config["vocab_size"]
        self.hidden_size = text_config["hidden_size"]
        self.num_attention_heads = text_config["num_attention_heads"]
        self.is_training = is_training

        self.batch_size = 3
        self.num_channels = 3
        self.image_size = 336
        self.encoder_seq_length = 232
        self.num_image_tokens = 225
        self.seq_length = seq_length + self.num_image_tokens

    def get_config(self):
        return VipLlavaConfig(
            text_config=self.text_config,
            vision_config=self.vision_config,
            ignore_index=self.ignore_index,
            image_token_index=self.image_token_index,
            projector_hidden_act=self.projector_hidden_act,
            vision_feature_layers=self.vision_feature_layers,
            image_seq_length=self.num_image_tokens,
        )

    def prepare_config_and_inputs(self):
        pixel_values = floats_tensor(
            [
                self.batch_size,
                self.vision_config["num_channels"],
                self.vision_config["image_size"],
                self.vision_config["image_size"],
            ]
        )
        config = self.get_config()

        return config, pixel_values

    def prepare_config_and_inputs_for_common(self):
        config_and_inputs = self.prepare_config_and_inputs()
        config, pixel_values = config_and_inputs
        input_ids = ids_tensor([self.batch_size, self.seq_length], config.text_config.vocab_size - 1) + 1
        attention_mask = input_ids.ne(1).to(torch_device)

        input_ids[input_ids == config.image_token_index] = self.pad_token_id
        input_ids[:, : self.num_image_tokens] = config.image_token_index
        inputs_dict = {
            "pixel_values": pixel_values,
            "input_ids": input_ids,
            "attention_mask": attention_mask,
        }
        return config, inputs_dict


@require_torch
# Copied from transformers.tests.models.llava.test_modeling_llava.LlavaForConditionalGenerationModelTest with Llava->VipLlava
class VipLlavaForConditionalGenerationModelTest(ModelTesterMixin, GenerationTesterMixin, unittest.TestCase):
    """
    Model tester for `VipLlavaForConditionalGeneration`.
    """

    all_model_classes = (VipLlavaForConditionalGeneration,) if is_torch_available() else ()
    all_generative_model_classes = (VipLlavaForConditionalGeneration,) if is_torch_available() else ()
    fx_compatible = False
    test_pruning = False
    test_resize_embeddings = True
    test_head_masking = False

    def setUp(self):
        self.model_tester = VipLlavaVisionText2TextModelTester(self)
        self.config_tester = ConfigTester(self, config_class=VipLlavaConfig, has_text_modality=False)

    # overwrite inputs_embeds tests because we need to delete "pixel values" for LVLMs
    def test_inputs_embeds(self):
        config, inputs_dict = self.model_tester.prepare_config_and_inputs_for_common()

        for model_class in self.all_model_classes:
            model = model_class(config)
            model.to(torch_device)
            model.eval()

            inputs = self._prepare_for_class(inputs_dict, model_class)

            input_ids = inputs["input_ids"]
            del inputs["input_ids"]
            del inputs["pixel_values"]

            wte = model.get_input_embeddings()
            inputs["inputs_embeds"] = wte(input_ids)

            with torch.no_grad():
                model(**inputs)

    # overwrite inputs_embeds tests because we need to delete "pixel values" for LVLMs
    # while some other models require pixel_values to be present
    def test_inputs_embeds_matches_input_ids(self):
        config, inputs_dict = self.model_tester.prepare_config_and_inputs_for_common()

        for model_class in self.all_model_classes:
            model = model_class(config)
            model.to(torch_device)
            model.eval()

            inputs = self._prepare_for_class(inputs_dict, model_class)
            input_ids = inputs["input_ids"]
            del inputs["input_ids"]
            del inputs["pixel_values"]

            inputs_embeds = model.get_input_embeddings()(input_ids)

            with torch.no_grad():
                out_ids = model(input_ids=input_ids, **inputs)[0]
                out_embeds = model(inputs_embeds=inputs_embeds, **inputs)[0]
            self.assertTrue(torch.allclose(out_embeds, out_ids))

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

    @unittest.skip(reason="Compile not yet supported because it is not yet supported in LLava")
    def test_sdpa_can_compile_dynamic(self):
        pass

    @unittest.skip(reason="Compile not yet supported because in LLava models")
    def test_sdpa_can_dispatch_on_flash(self):
        pass


@require_torch
class VipLlavaForConditionalGenerationIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.processor = AutoProcessor.from_pretrained("llava-hf/vip-llava-7b-hf")

    def tearDown(self):
        gc.collect()
        torch.cuda.empty_cache()

    @slow
    @require_bitsandbytes
    def test_small_model_integration_test(self):
        model_id = "llava-hf/vip-llava-7b-hf"

        model = VipLlavaForConditionalGeneration.from_pretrained(model_id, load_in_4bit=True)
        processor = AutoProcessor.from_pretrained(model_id)

        url = "https://huggingface.co/datasets/huggingface/documentation-images/resolve/main/diffusers/compel-neg.png"

        image = Image.open(requests.get(url, stream=True).raw)
        prompt = "USER: <image>\nCan you please describe this image?\nASSISTANT:"

        inputs = processor(prompt, image, return_tensors="pt").to(torch_device, torch.float16)

        outputs = model.generate(**inputs, max_new_tokens=10)

        EXPECTED_OUTPUT = "USER: <image> \nCan you please describe this image?\nASSISTANT: The image features a brown and white cat sitting on"
        self.assertEqual(processor.decode(outputs[0], skip_special_tokens=True), EXPECTED_OUTPUT)

    @slow
    @require_torch_gpu
    def test_vipllava_merge_inputs_error_bug(self):
        # This is a reproducer of https://github.com/huggingface/transformers/pull/28333 and makes sure it does not happen anymore
        model_id = "llava-hf/vip-llava-7b-hf"
        model = VipLlavaForConditionalGeneration.from_pretrained(model_id, load_in_4bit=True)

        # Simulate some user inputs
        pixel_values = torch.randn(
            (1, 3, 336, 336),
            dtype=torch.float,
            device=torch_device,
        )
        input_ids = torch.tensor(
            [
                [32001, 32001, 1, 15043, 7084, 32000, 29871, 13, 7900],
            ],
            dtype=torch.long,
            device=torch_device,
        )
        attention_mask = torch.tensor(
            [[0, 0, 1, 1, 1, 1, 1, 1, 1]],
            dtype=torch.long,
            device=torch_device,
        )

        # Make sure that the loss is properly computed
        loss = model(
            pixel_values=pixel_values,
            input_ids=input_ids,
            attention_mask=attention_mask,
            labels=input_ids,
        ).loss
        loss.backward()

    @slow
    @require_bitsandbytes
    def test_expansion_in_processing(self):
        model_id = "llava-hf/vip-llava-7b-hf"
        model = VipLlavaForConditionalGeneration.from_pretrained(model_id, load_in_4bit=True)
        processor = AutoProcessor.from_pretrained(model_id)

        prompt = "USER: <image>\nDescribe the image:\nASSISTANT:"
        image_file = "http://images.cocodataset.org/val2017/000000039769.jpg"
        raw_image = Image.open(requests.get(image_file, stream=True).raw)

        # check processing with expansion of inputs
        processor.vision_feature_select_strategy = "default"
        processor.patch_size = 14
        inputs_expanded = processor(prompt, raw_image, return_tensors="pt").to(torch_device, torch.float16)
        self.assertTrue(inputs_expanded.input_ids.shape[-1] == 593)

        # check processing without expansion of inputs (legacy behavior)
        processor.vision_feature_select_strategy = None
        processor.patch_size = None
        inputs = processor(prompt, raw_image, return_tensors="pt").to(torch_device, torch.float16)
        self.assertTrue(inputs.input_ids.shape[-1] == 18)

        # generate exactly 20 tokens
        output = model.generate(**inputs, min_new_tokens=20, max_new_tokens=20)
        output_expanded = model.generate(**inputs_expanded, min_new_tokens=20, max_new_tokens=20)

        # check that both inputs are handled correctly and generate the same output
        self.assertListEqual(output_expanded[:, -20:].tolist(), output[:, -20:].tolist())
