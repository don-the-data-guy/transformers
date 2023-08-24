# Copyright 2023 The HuggingFace Team. All rights reserved.
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


import unittest

import numpy as np

from transformers import LlamaConfig, is_flax_available, is_torch_available
from transformers.testing_utils import require_flax, slow, skip

from ...generation.test_flax_utils import FlaxGenerationTesterMixin
from ...test_modeling_flax_common import FlaxModelTesterMixin, ids_tensor, random_attention_mask


if is_flax_available():
    import jax.numpy as jnp

    from transformers.models.llama.modeling_flax_llama import FlaxLlamaForCausalLM, FlaxLlamaModel
    from transformers import LlamaTokenizerFast

if is_torch_available():
    pass

class FlaxLlamaModelTester:
    def __init__(
        self,
        parent,
        batch_size=2,
        seq_length=7,
        is_training=True,
        use_input_mask=True,
        use_token_type_ids=False,
        use_labels=True,
        vocab_size=99,
        hidden_size=16,
        num_hidden_layers=2,
        num_attention_heads=2,
        attention_types=[[["global", "local"], 2]],
        intermediate_size=64,
        hidden_act="gelu",
        hidden_dropout_prob=0.1,
        attention_probs_dropout_prob=0.1,
        max_position_embeddings=512,
        window_size=7,
        initializer_range=0.02,
    ):
        self.parent = parent
        self.batch_size = batch_size
        self.seq_length = seq_length
        self.is_training = is_training
        self.use_input_mask = use_input_mask
        self.use_token_type_ids = use_token_type_ids
        self.use_labels = use_labels
        self.vocab_size = vocab_size
        self.hidden_size = hidden_size
        self.num_hidden_layers = num_hidden_layers
        self.num_attention_heads = num_attention_heads
        self.attention_types = attention_types
        self.intermediate_size = intermediate_size
        self.hidden_act = hidden_act
        self.hidden_dropout_prob = hidden_dropout_prob
        self.attention_probs_dropout_prob = attention_probs_dropout_prob
        self.max_position_embeddings = max_position_embeddings
        self.window_size = window_size
        self.initializer_range = initializer_range
        self.scope = None
        self.bos_token_id = vocab_size - 1
        self.eos_token_id = vocab_size - 1
        self.pad_token_id = vocab_size - 1

    def prepare_config_and_inputs(self):
        input_ids = ids_tensor([self.batch_size, self.seq_length], self.vocab_size)

        input_mask = None
        if self.use_input_mask:
            input_mask = random_attention_mask([self.batch_size, self.seq_length])

        config = LlamaConfig(
            vocab_size=self.vocab_size,
            hidden_size=self.hidden_size,
            num_hidden_layers=self.num_hidden_layers,
            num_attention_heads=self.num_attention_heads,
            intermediate_size=self.intermediate_size,
            hidden_act=self.hidden_act,
            hidden_dropout_prob=self.hidden_dropout_prob,
            attention_probs_dropout_prob=self.attention_probs_dropout_prob,
            max_position_embeddings=self.max_position_embeddings,
            use_cache=False,
            is_decoder=False,
            initializer_range=self.initializer_range,
        )

        return (config, input_ids, input_mask)

    def prepare_config_and_inputs_for_common(self):
        config_and_inputs = self.prepare_config_and_inputs()
        config, input_ids, attention_mask = config_and_inputs
        inputs_dict = {"input_ids": input_ids, "attention_mask": attention_mask}
        return config, inputs_dict

    def check_use_cache_forward(self, model_class_name, config, input_ids, attention_mask):
        max_decoder_length = 20
        model = model_class_name(config)

        past_key_values = model.init_cache(input_ids.shape[0], max_decoder_length)
        attention_mask = jnp.ones((input_ids.shape[0], max_decoder_length), dtype="i4")

        position_ids = jnp.broadcast_to(
            jnp.arange(input_ids.shape[-1] - 1)[None, :], (input_ids.shape[0], input_ids.shape[-1] - 1)
        )
        outputs_cache = model(
            input_ids[:, :-1],
            attention_mask=attention_mask,
            past_key_values=past_key_values,
            position_ids=position_ids,
        )

        position_ids = jnp.array(input_ids.shape[0] * [[input_ids.shape[-1] - 1]], dtype="i4")
        outputs_cache_next = model(
            input_ids[:, -1:],
            attention_mask=attention_mask,
            past_key_values=outputs_cache.past_key_values,
            position_ids=position_ids,
        )

        outputs = model(input_ids)

        diff = np.max(np.abs((outputs_cache_next[0][:, -1, :5] - outputs[0][:, -1, :5])))
        self.parent.assertTrue(diff < 1e-3, msg=f"Max diff is {diff}")

    def check_use_cache_forward_with_attn_mask(self, model_class_name, config, input_ids, attention_mask):
        max_decoder_length = 20
        model = model_class_name(config)

        attention_mask_cache = jnp.concatenate(
            [attention_mask, jnp.zeros((attention_mask.shape[0], max_decoder_length - attention_mask.shape[1]))],
            axis=-1,
        )

        past_key_values = model.init_cache(input_ids.shape[0], max_decoder_length)
        position_ids = jnp.broadcast_to(
            jnp.arange(input_ids.shape[-1] - 1)[None, :], (input_ids.shape[0], input_ids.shape[-1] - 1)
        )

        outputs_cache = model(
            input_ids[:, :-1],
            attention_mask=attention_mask_cache,
            past_key_values=past_key_values,
            position_ids=position_ids,
        )
        position_ids = jnp.array(input_ids.shape[0] * [[input_ids.shape[-1] - 1]], dtype="i4")
        outputs_cache_next = model(
            input_ids[:, -1:],
            past_key_values=outputs_cache.past_key_values,
            attention_mask=attention_mask_cache,
            position_ids=position_ids,
        )

        outputs = model(input_ids, attention_mask=attention_mask)

        diff = np.max(np.abs((outputs_cache_next[0][:, -1, :5] - outputs[0][:, -1, :5])))
        self.parent.assertTrue(diff < 1e-3, msg=f"Max diff is {diff}")


@require_flax
class FlaxLlamaModelTest(FlaxModelTesterMixin, FlaxGenerationTesterMixin, unittest.TestCase):
    all_model_classes = (FlaxLlamaModel, FlaxLlamaForCausalLM) if is_flax_available() else ()
    all_generative_model_classes = (FlaxLlamaForCausalLM,) if is_flax_available() else ()

    def setUp(self):
        self.model_tester = FlaxLlamaModelTester(self)

    def test_use_cache_forward(self):
        for model_class_name in self.all_model_classes:
            config, input_ids, attention_mask = self.model_tester.prepare_config_and_inputs()
            self.model_tester.check_use_cache_forward(model_class_name, config, input_ids, attention_mask)

    def test_use_cache_forward_with_attn_mask(self):
        for model_class_name in self.all_model_classes:
            config, input_ids, attention_mask = self.model_tester.prepare_config_and_inputs()
            self.model_tester.check_use_cache_forward_with_attn_mask(
                model_class_name, config, input_ids, attention_mask
            )

    @slow
    def test_model_from_pretrained(self):
        for model_class_name in self.all_model_classes:
            model = model_class_name.from_pretrained("openlm-research/open_llama_3b_v2", from_pt=True)
            outputs = model(np.ones((1, 1)))
            self.assertIsNotNone(outputs)

    @slow
    @skip # wip test
    def test_model_logits(self):
        model_id = "openlm-research/open_llama_3b_v2"
        model = FlaxLlamaForCausalLM.from_pretrained(model_id, from_pt=True)
        test_batch = jnp.arange(32).reshape(4, 8) + 0x777

        flax_logits = model(test_batch).logits

        # TODO: add expected logits here
        # fmt: off
        EXPECTED_LOGITS = None
        # fmt: on

        self.assertAlmostEqual(flax_logits, EXPECTED_LOGITS, places=4)

    @slow
    @skip # wip test
    def test_model_hidden_states(self):
        model_id = "openlm-research/open_llama_3b_v2"
        model = FlaxLlamaForCausalLM.from_pretrained(model_id, from_pt=True)
        test_batch = jnp.arange(32).reshape(4, 8) + 0x777

        flax_hidden_states = model(test_batch).hidden_states
        # TODO: calculate mean of all hidden states
        flax_hidden_means = None

        # TODO: add expected logits here
        # fmt: off
        EXPECTED_HIDDEN_MEANS = None
        # fmt: on

        self.assertAlmostEqual(flax_hidden_means, EXPECTED_HIDDEN_MEANS, places=4)

    @slow
    @skip # wip test
    def test_generated_text(self):
        model_id = "openlm-research/open_llama_3b_v2"
        model = FlaxLlamaForCausalLM.from_pretrained(model_id, from_pt=True)

        tokenizer = LlamaTokenizerFast.from_pretrained(model_id)
        test_batch = [
            "Aloha, World! ",
            "2 + 2 = ",
            "Paris is the capital of ",
            "我很高興認識"
        ] 

        inputs = tokenizer(test_batch, return_tensors='np', padding=True, truncation=True)
        generated_ids = model.generate(**inputs, max_length=20).sequences
        generated_text = tokenizer.batch_decode(generated_ids, skip_special_tokens=True)

        # TODO: add expected outputs
        EXPECTED_GENERATION = None

        self.assertListEqual(generated_text, EXPECTED_GENERATION)