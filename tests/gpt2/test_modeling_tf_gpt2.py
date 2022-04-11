# coding=utf-8
# Copyright 2020 The HuggingFace Team. All rights reserved.
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

from transformers import GPT2Config, is_tf_available
from transformers.testing_utils import require_tf, slow

from ..test_configuration_common import ConfigTester
from ..test_modeling_tf_common import TFModelTesterMixin, floats_tensor, ids_tensor, random_attention_mask
from ..utils.test_modeling_tf_core import TFCoreModelTesterMixin


if is_tf_available():
    import tensorflow as tf

    from transformers import GPT2Tokenizer
    from transformers.models.gpt2.modeling_tf_gpt2 import (
        TF_GPT2_PRETRAINED_MODEL_ARCHIVE_LIST,
        TFGPT2DoubleHeadsModel,
        TFGPT2ForSequenceClassification,
        TFGPT2LMHeadModel,
        TFGPT2Model,
    )
    from transformers.tf_utils import shape_list


class TFGPT2ModelTester:
    def __init__(
        self,
        parent,
    ):
        self.parent = parent
        self.batch_size = 13
        self.seq_length = 7
        self.is_training = True
        self.use_token_type_ids = True
        self.use_input_mask = True
        self.use_labels = True
        self.use_mc_token_ids = True
        self.vocab_size = 99
        self.hidden_size = 32
        self.num_hidden_layers = 5
        self.num_attention_heads = 4
        self.intermediate_size = 37
        self.hidden_act = "gelu"
        self.hidden_dropout_prob = 0.1
        self.attention_probs_dropout_prob = 0.1
        self.max_position_embeddings = 512
        self.type_vocab_size = 16
        self.type_sequence_label_size = 2
        self.initializer_range = 0.02
        self.num_labels = 3
        self.num_choices = 4
        self.scope = None
        self.bos_token_id = self.vocab_size - 1
        self.eos_token_id = self.vocab_size - 1
        self.pad_token_id = self.vocab_size - 1

    def prepare_config_and_inputs(self):
        input_ids = ids_tensor([self.batch_size, self.seq_length], self.vocab_size)

        input_mask = None
        if self.use_input_mask:
            input_mask = random_attention_mask([self.batch_size, self.seq_length])

        token_type_ids = None
        if self.use_token_type_ids:
            token_type_ids = ids_tensor([self.batch_size, self.seq_length], self.type_vocab_size)

        mc_token_ids = None
        if self.use_mc_token_ids:
            mc_token_ids = ids_tensor([self.batch_size, self.num_choices], self.seq_length)

        sequence_labels = None
        token_labels = None
        choice_labels = None
        if self.use_labels:
            sequence_labels = ids_tensor([self.batch_size], self.type_sequence_label_size)
            token_labels = ids_tensor([self.batch_size, self.seq_length], self.num_labels)
            choice_labels = ids_tensor([self.batch_size], self.num_choices)

        config = GPT2Config(
            vocab_size=self.vocab_size,
            n_embd=self.hidden_size,
            n_layer=self.num_hidden_layers,
            n_head=self.num_attention_heads,
            # intermediate_size=self.intermediate_size,
            # hidden_act=self.hidden_act,
            # hidden_dropout_prob=self.hidden_dropout_prob,
            # attention_probs_dropout_prob=self.attention_probs_dropout_prob,
            n_positions=self.max_position_embeddings,
            # type_vocab_size=self.type_vocab_size,
            # initializer_range=self.initializer_range
            bos_token_id=self.bos_token_id,
            eos_token_id=self.eos_token_id,
            pad_token_id=self.pad_token_id,
            return_dict=True,
        )

        head_mask = ids_tensor([self.num_hidden_layers, self.num_attention_heads], 2)

        return (
            config,
            input_ids,
            input_mask,
            head_mask,
            token_type_ids,
            mc_token_ids,
            sequence_labels,
            token_labels,
            choice_labels,
        )

    def prepare_config_and_inputs_for_decoder(self):
        (
            config,
            input_ids,
            input_mask,
            head_mask,
            token_type_ids,
            mc_token_ids,
            sequence_labels,
            token_labels,
            choice_labels,
        ) = self.prepare_config_and_inputs()

        encoder_hidden_states = floats_tensor([self.batch_size, self.seq_length, self.hidden_size])
        encoder_attention_mask = ids_tensor([self.batch_size, self.seq_length], vocab_size=2)

        return (
            config,
            input_ids,
            input_mask,
            head_mask,
            token_type_ids,
            sequence_labels,
            token_labels,
            choice_labels,
            encoder_hidden_states,
            encoder_attention_mask,
        )

    def create_and_check_gpt2_model(self, config, input_ids, input_mask, head_mask, token_type_ids, *args):
        model = TFGPT2Model(config=config)
        inputs = {
            "input_ids": input_ids,
            "attention_mask": input_mask,
            "token_type_ids": token_type_ids,
        }
        result = model(inputs)

        inputs = [input_ids, None, input_mask]  # None is the input for 'past'
        result = model(inputs)

        result = model(input_ids)

        self.parent.assertEqual(result.last_hidden_state.shape, (self.batch_size, self.seq_length, self.hidden_size))

    def create_and_check_gpt2_model_past(self, config, input_ids, input_mask, head_mask, token_type_ids, *args):
        model = TFGPT2Model(config=config)

        # first forward pass
        outputs = model(input_ids, token_type_ids=token_type_ids, use_cache=True)
        outputs_use_cache_conf = model(input_ids, token_type_ids=token_type_ids)
        outputs_no_past = model(input_ids, token_type_ids=token_type_ids, use_cache=False)

        self.parent.assertTrue(len(outputs) == len(outputs_use_cache_conf))
        self.parent.assertTrue(len(outputs) == len(outputs_no_past) + 1)

        output, past = outputs.to_tuple()

        # create hypothetical next token and extent to next_input_ids
        next_tokens = ids_tensor((self.batch_size, 1), config.vocab_size)
        next_token_types = ids_tensor([self.batch_size, 1], self.type_vocab_size)

        # append to next input_ids and token_type_ids
        next_input_ids = tf.concat([input_ids, next_tokens], axis=-1)
        next_token_type_ids = tf.concat([token_type_ids, next_token_types], axis=-1)

        output_from_no_past = model(next_input_ids, token_type_ids=next_token_type_ids)["last_hidden_state"]
        output_from_past = model(next_tokens, token_type_ids=next_token_types, past=past)["last_hidden_state"]

        # select random slice
        random_slice_idx = int(ids_tensor((1,), shape_list(output_from_past)[-1]))
        output_from_no_past_slice = output_from_no_past[:, -1, random_slice_idx]
        output_from_past_slice = output_from_past[:, 0, random_slice_idx]

        # test that outputs are equal for slice
        tf.debugging.assert_near(output_from_past_slice, output_from_no_past_slice, rtol=1e-6)

    def create_and_check_gpt2_model_attention_mask_past(
        self, config, input_ids, input_mask, head_mask, token_type_ids, *args
    ):
        model = TFGPT2Model(config=config)

        # create attention mask
        half_seq_length = self.seq_length // 2
        attn_mask_begin = tf.ones((self.batch_size, half_seq_length), dtype=tf.int32)
        attn_mask_end = tf.zeros((self.batch_size, self.seq_length - half_seq_length), dtype=tf.int32)
        attn_mask = tf.concat([attn_mask_begin, attn_mask_end], axis=1)

        # first forward pass
        output, past = model(input_ids, attention_mask=attn_mask).to_tuple()

        # create hypothetical next token and extent to next_input_ids
        next_tokens = ids_tensor((self.batch_size, 1), config.vocab_size)

        # change a random masked slice from input_ids
        random_seq_idx_to_change = ids_tensor((1,), half_seq_length).numpy() + 1
        random_other_next_tokens = ids_tensor((self.batch_size, self.seq_length), config.vocab_size)
        vector_condition = tf.range(self.seq_length) == (self.seq_length - random_seq_idx_to_change)
        condition = tf.transpose(
            tf.broadcast_to(tf.expand_dims(vector_condition, -1), (self.seq_length, self.batch_size))
        )
        input_ids = tf.where(condition, random_other_next_tokens, input_ids)

        # append to next input_ids and attn_mask
        next_input_ids = tf.concat([input_ids, next_tokens], axis=-1)
        attn_mask = tf.concat([attn_mask, tf.ones((shape_list(attn_mask)[0], 1), dtype=tf.int32)], axis=1)

        # get two different outputs
        output_from_no_past = model(next_input_ids, attention_mask=attn_mask)["last_hidden_state"]
        output_from_past = model(next_tokens, past=past, attention_mask=attn_mask)["last_hidden_state"]

        # select random slice
        random_slice_idx = int(ids_tensor((1,), shape_list(output_from_past)[-1]))
        output_from_no_past_slice = output_from_no_past[:, -1, random_slice_idx]
        output_from_past_slice = output_from_past[:, 0, random_slice_idx]

        # test that outputs are equal for slice
        tf.debugging.assert_near(output_from_past_slice, output_from_no_past_slice, rtol=1e-12)

    def create_and_check_gpt2_model_past_large_inputs(
        self, config, input_ids, input_mask, head_mask, token_type_ids, *args
    ):
        model = TFGPT2Model(config=config)

        input_ids = input_ids[:1, :]
        input_mask = input_mask[:1, :]
        token_type_ids = token_type_ids[:1, :]
        self.batch_size = 1

        # first forward pass
        outputs = model(input_ids, attention_mask=input_mask, token_type_ids=token_type_ids, use_cache=True)

        output, past = outputs.to_tuple()

        # create hypothetical next token and extent to next_input_ids
        next_tokens = ids_tensor((self.batch_size, 3), config.vocab_size)
        next_attn_mask = ids_tensor((self.batch_size, 3), 2)
        next_token_types = ids_tensor((self.batch_size, 3), self.type_vocab_size)

        # append to next input_ids and token_type_ids
        next_input_ids = tf.concat([input_ids, next_tokens], axis=-1)
        next_attention_mask = tf.concat([input_mask, next_attn_mask], axis=-1)
        next_token_type_ids = tf.concat([token_type_ids, next_token_types], axis=-1)

        output_from_no_past = model(
            next_input_ids, token_type_ids=next_token_type_ids, attention_mask=next_attention_mask
        )["last_hidden_state"]
        output_from_past = model(
            next_tokens, token_type_ids=next_token_types, attention_mask=next_attention_mask, past=past
        )["last_hidden_state"]
        self.parent.assertTrue(output_from_past.shape[1] == next_tokens.shape[1])

        # select random slice
        random_slice_idx = int(ids_tensor((1,), shape_list(output_from_past)[-1]))
        output_from_no_past_slice = output_from_no_past[:, -3:, random_slice_idx]
        output_from_past_slice = output_from_past[:, :, random_slice_idx]

        # test that outputs are equal for slice
        tf.debugging.assert_near(output_from_past_slice, output_from_no_past_slice, rtol=1e-3)

    def create_and_check_gpt2_lm_head(self, config, input_ids, input_mask, head_mask, token_type_ids, *args):
        model = TFGPT2LMHeadModel(config=config)
        inputs = {
            "input_ids": input_ids,
            "attention_mask": input_mask,
            "token_type_ids": token_type_ids,
        }
        result = model(inputs)
        self.parent.assertEqual(result.logits.shape, (self.batch_size, self.seq_length, self.vocab_size))

    def create_and_check_gpt2_xla_generate(self, config, input_ids, *args):
        config.eos_token_id = None
        config.max_length = 10
        model = TFGPT2LMHeadModel(config=config)

        # make sure there are no pad tokens in prompt
        input_ids = tf.where(input_ids != config.pad_token_id, input_ids, config.pad_token_id - 1)

        generated = model.generate(input_ids)

        generate_xla = tf.function(model.generate, jit_compile=True)
        generated_xla = generate_xla(input_ids)

        self.parent.assertListEqual(generated.numpy().tolist(), generated_xla.numpy().tolist())

    def create_and_check_gpt2_double_head(
        self, config, input_ids, input_mask, head_mask, token_type_ids, mc_token_ids, *args
    ):
        model = TFGPT2DoubleHeadsModel(config=config)

        multiple_choice_inputs_ids = tf.tile(tf.expand_dims(input_ids, 1), (1, self.num_choices, 1))
        multiple_choice_input_mask = tf.tile(tf.expand_dims(input_mask, 1), (1, self.num_choices, 1))
        multiple_choice_token_type_ids = tf.tile(tf.expand_dims(token_type_ids, 1), (1, self.num_choices, 1))

        inputs = {
            "input_ids": multiple_choice_inputs_ids,
            "mc_token_ids": mc_token_ids,
            "attention_mask": multiple_choice_input_mask,
            "token_type_ids": multiple_choice_token_type_ids,
        }
        result = model(inputs)
        self.parent.assertEqual(
            result.logits.shape, (self.batch_size, self.num_choices, self.seq_length, self.vocab_size)
        )
        self.parent.assertEqual(result.mc_logits.shape, (self.batch_size, self.num_choices))

    def create_and_check_gpt2_for_sequence_classification(
        self, config, input_ids, input_mask, head_mask, token_type_ids, mc_token_ids, sequence_labels, *args
    ):
        config.num_labels = self.num_labels
        inputs = {
            "input_ids": input_ids,
            "attention_mask": input_mask,
            "token_type_ids": token_type_ids,
            "labels": sequence_labels,
        }
        model = TFGPT2ForSequenceClassification(config)

        result = model(inputs)
        self.parent.assertEqual(result.logits.shape, (self.batch_size, self.num_labels))

    def prepare_config_and_inputs_for_common(self):
        config_and_inputs = self.prepare_config_and_inputs()

        (
            config,
            input_ids,
            input_mask,
            head_mask,
            token_type_ids,
            mc_token_ids,
            sequence_labels,
            token_labels,
            choice_labels,
        ) = config_and_inputs

        inputs_dict = {
            "input_ids": input_ids,
            "token_type_ids": token_type_ids,
            "attention_mask": input_mask,
        }
        return config, inputs_dict


@require_tf
class TFGPT2ModelTest(TFModelTesterMixin, TFCoreModelTesterMixin, unittest.TestCase):

    all_model_classes = (
        (TFGPT2Model, TFGPT2LMHeadModel, TFGPT2ForSequenceClassification, TFGPT2DoubleHeadsModel)
        if is_tf_available()
        else ()
    )
    all_generative_model_classes = (TFGPT2LMHeadModel,) if is_tf_available() else ()
    test_head_masking = False
    test_onnx = True
    onnx_min_opset = 10

    def setUp(self):
        self.model_tester = TFGPT2ModelTester(self)
        self.config_tester = ConfigTester(self, config_class=GPT2Config, n_embd=37)

    def test_config(self):
        self.config_tester.run_common_tests()

    def test_gpt2_model(self):
        config_and_inputs = self.model_tester.prepare_config_and_inputs()
        self.model_tester.create_and_check_gpt2_model(*config_and_inputs)

    def test_gpt2_model_past(self):
        config_and_inputs = self.model_tester.prepare_config_and_inputs()
        self.model_tester.create_and_check_gpt2_model_past(*config_and_inputs)

    def test_gpt2_model_att_mask_past(self):
        config_and_inputs = self.model_tester.prepare_config_and_inputs()
        self.model_tester.create_and_check_gpt2_model_attention_mask_past(*config_and_inputs)

    def test_gpt2_model_past_large_inputs(self):
        config_and_inputs = self.model_tester.prepare_config_and_inputs()
        self.model_tester.create_and_check_gpt2_model_past_large_inputs(*config_and_inputs)

    def test_gpt2_lm_head(self):
        config_and_inputs = self.model_tester.prepare_config_and_inputs()
        self.model_tester.create_and_check_gpt2_lm_head(*config_and_inputs)

    def test_gpt2_xla_generate(self):
        config_and_inputs = self.model_tester.prepare_config_and_inputs()
        self.model_tester.create_and_check_gpt2_xla_generate(*config_and_inputs)

    def test_gpt2_double_head(self):
        config_and_inputs = self.model_tester.prepare_config_and_inputs()
        self.model_tester.create_and_check_gpt2_double_head(*config_and_inputs)

    def test_model_common_attributes(self):
        config, inputs_dict = self.model_tester.prepare_config_and_inputs_for_common()

        for model_class in self.all_model_classes:
            model = model_class(config)
            assert isinstance(model.get_input_embeddings(), tf.keras.layers.Layer)

            if model_class in self.all_generative_model_classes:
                x = model.get_output_embeddings()
                assert isinstance(x, tf.keras.layers.Layer)
                name = model.get_bias()
                assert name is None
            else:
                x = model.get_output_embeddings()
                assert x is None
                name = model.get_bias()
                assert name is None

    def test_gpt2_sequence_classification_model(self):
        config_and_inputs = self.model_tester.prepare_config_and_inputs()
        self.model_tester.create_and_check_gpt2_for_sequence_classification(*config_and_inputs)

    @slow
    def test_model_from_pretrained(self):
        for model_name in TF_GPT2_PRETRAINED_MODEL_ARCHIVE_LIST[:1]:
            model = TFGPT2Model.from_pretrained(model_name)
            self.assertIsNotNone(model)


@require_tf
class TFGPT2ModelLanguageGenerationTest(unittest.TestCase):
    @slow
    def test_lm_generate_distilgpt2(self):
        model = TFGPT2LMHeadModel.from_pretrained("distilgpt2")
        input_ids = tf.convert_to_tensor([[464, 1893]], dtype=tf.int32)  # The president

        # The president of the United States, and the president of the United Kingdom, have been in the White
        # fmt: off
        expected_output_ids = [464, 1893, 286, 262, 1578, 1829, 11, 290, 262, 1893, 286, 262, 1578, 7526, 11, 423, 587, 287, 262, 2635]
        # fmt: on

        output_ids = model.generate(input_ids, do_sample=False)
        self.assertListEqual(output_ids[0].numpy().tolist(), expected_output_ids)

    @slow
    def test_lm_generate_greedy_distilgpt2_batch_special(self):
        model = TFGPT2LMHeadModel.from_pretrained("distilgpt2")
        tokenizer = GPT2Tokenizer.from_pretrained("distilgpt2")

        tokenizer.pad_token = tokenizer.eos_token
        tokenizer.padding_side = "left"

        sentences = ["Today is a beautiful day and", "Yesterday was"]
        input_ids = tokenizer(sentences, return_tensors="tf", padding=True).input_ids

        generation_kwargs = {
            "bad_words_ids": [tokenizer("is").input_ids, tokenizer("angry about").input_ids],
            "no_repeat_ngram_size": 2,
            "do_sample": False,
            "repetition_penalty": 1.3,
        }

        output_ids = model.generate(input_ids, **generation_kwargs)

        output_strings = tokenizer.batch_decode(output_ids, skip_special_tokens=True)
        expected_output_string = [
            "Today is a beautiful day and I am so happy to be able take part in this amazing event.",
            "Yesterday was a very busy day for the first time since I started writing this post",
        ]
        self.assertListEqual(output_strings, expected_output_string)

    @slow
    def test_lm_generate_sample_distilgpt2_batch_special(self):
        model = TFGPT2LMHeadModel.from_pretrained("distilgpt2")
        tokenizer = GPT2Tokenizer.from_pretrained("distilgpt2")

        tokenizer.pad_token = tokenizer.eos_token
        tokenizer.padding_side = "left"

        sentences = ["Today is a beautiful day and", "Yesterday was"]
        input_ids = tokenizer(sentences, return_tensors="tf", padding=True).input_ids

        generation_kwargs = {
            "do_sample": True,
            "bad_words_ids": [tokenizer("is").input_ids, tokenizer("angry about").input_ids],
            "no_repeat_ngram_size": 2,
            "repetition_penalty": 1.3,
            "temperature": 1.5,
            "top_k": 500,
            "top_p": 0.9,
            "seed": [42, 0],  # seed set -> deterministic sampling sequence -> deterministic generation
        }

        # forces the generation to happen on CPU, to avoid GPU-related quirks
        with tf.device(":/CPU:0"):
            output_ids = model.generate(input_ids, **generation_kwargs)

        output_strings = tokenizer.batch_decode(output_ids, skip_special_tokens=True)

        expected_output_string = [
            "Today is a beautiful day and we will make you feel very hot/terrific in all",
            "Yesterday was another solid success as news coverage became standard American domestic television hit.",
        ]
        self.assertListEqual(output_strings, expected_output_string)

    @slow
    def test_lm_generate_greedy_distilgpt2_beam_search_special(self):
        model = TFGPT2LMHeadModel.from_pretrained("distilgpt2")
        tokenizer = GPT2Tokenizer.from_pretrained("distilgpt2")

        tokenizer.pad_token = tokenizer.eos_token
        tokenizer.padding_side = "left"

        sentences = ["Today is a beautiful day and", "Yesterday was"]
        input_ids = tokenizer(sentences, return_tensors="tf", padding=True).input_ids

        generation_kwargs = {
            "bad_words_ids": [tokenizer("is").input_ids, tokenizer("angry about").input_ids],
            "no_repeat_ngram_size": 2,
            "do_sample": False,
            "num_beams": 2,
        }

        output_ids = model.generate(input_ids, **generation_kwargs)

        output_strings = tokenizer.batch_decode(output_ids, skip_special_tokens=True)
        expected_output_string = [
            "Today is a beautiful day and a great day for all of us.\n\nI’m",
            "Yesterday was the first day of the year for the second time in a row,",
        ]
        self.assertListEqual(output_strings, expected_output_string)

    @slow
    def test_lm_generate_gpt2(self):
        model = TFGPT2LMHeadModel.from_pretrained("gpt2")
        input_ids = tf.convert_to_tensor([[464, 3290]], dtype=tf.int32)  # The dog

        # The dog was found in a field near the intersection of West and West Streets.\n\nThe dog
        # fmt: off
        expected_output_ids = [464, 3290, 373, 1043, 287, 257, 2214, 1474, 262, 16246, 286, 2688, 290, 2688, 27262, 13, 198, 198, 464, 3290]
        # fmt: on
        output_ids = model.generate(input_ids, do_sample=False)
        self.assertListEqual(output_ids[0].numpy().tolist(), expected_output_ids)

    @slow
    def test_lm_generate_gpt2_xla(self):
        """This test gives the exact same results as the non-xla test above"""
        model = TFGPT2LMHeadModel.from_pretrained("gpt2")
        input_ids = tf.convert_to_tensor([[464, 3290]], dtype=tf.int32)  # The dog

        # The dog was found in a field near the intersection of West and West Streets.\n\nThe dog
        # fmt: off
        expected_output_ids = [464, 3290, 373, 1043, 287, 257, 2214, 1474, 262, 16246, 286, 2688, 290, 2688, 27262, 13, 198, 198, 464, 3290]
        # fmt: on
        xla_generate = tf.function(model.generate, jit_compile=True)

        output_ids = xla_generate(input_ids, do_sample=False)
        self.assertListEqual(output_ids[0].numpy().tolist(), expected_output_ids)
