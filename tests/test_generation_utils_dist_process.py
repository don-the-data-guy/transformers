# coding=utf-8
# Copyright 2020 The HuggingFace Team Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a clone of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import unittest

from transformers import is_torch_available
from transformers.testing_utils import require_torch, torch_device

from .test_modeling_common import ids_tensor


if is_torch_available():
    import torch
    import torch.nn.functional as F

    from transformers.generation_utils_dist_process import (
        DistProcessorList,
        MinLengthDistProcessor,
        NoBadWordsDistProcessor,
        NoRepeatNGramDistProcessor,
        RepetitionPenaltyDistProcessor,
        TemperatureDistWarper,
        TopKDistWarper,
        TopPDistWarper,
    )


@require_torch
class DistProcessorTest(unittest.TestCase):
    def _get_uniform_logits(self, batch_size: int, length: int):
        scores = torch.ones((batch_size, length), device=torch_device, dtype=torch.float) / length
        return scores

    def test_min_lenght_dist_processor(self):
        vocab_size = 20
        batch_size = 4
        eos_token_id = 0

        min_dist_processor = MinLengthDistProcessor(min_length=10, eos_token_id=eos_token_id)

        # check that min length is applied at length 5
        input_ids = ids_tensor((batch_size, 5), vocab_size=20)
        scores = self._get_uniform_logits(batch_size, vocab_size)
        scores_before_min_length = min_dist_processor(input_ids, scores)
        self.assertListEqual(scores_before_min_length[:, eos_token_id].tolist(), 4 * [-float("inf")])

        # check that min length is not applied anymore at length 15
        input_ids = ids_tensor((batch_size, 15), vocab_size=20)
        scores = self._get_uniform_logits(batch_size, vocab_size)
        scores_before_min_length = min_dist_processor(input_ids, scores)
        self.assertFalse(torch.isinf(scores_before_min_length).any())

    def test_temperature_dist_warper(self):
        input_ids = None
        length = 20

        scores = self._get_uniform_logits(batch_size=2, length=length)

        # tweak scores to not be uniform anymore
        scores[1, 5] = (1 / length) + 0.1  # peak, 1st batch
        scores[1, 10] = (1 / length) - 0.4  # valley, 1st batch

        # compute softmax
        probs = F.softmax(scores, dim=-1)

        temp_dist_warper_sharper = TemperatureDistWarper(temperature=0.5)
        temp_dist_warper_smoother = TemperatureDistWarper(temperature=1.3)

        warped_prob_sharp = F.softmax(temp_dist_warper_sharper(input_ids, scores.clone()), dim=-1)
        warped_prob_smooth = F.softmax(temp_dist_warper_smoother(input_ids, scores.clone()), dim=-1)

        # uniform distribution stays uniform
        self.assertTrue(torch.allclose(probs[0, :], warped_prob_sharp[0, :], atol=1e-3))
        self.assertTrue(torch.allclose(probs[0, :], warped_prob_smooth[0, :], atol=1e-3))

        # sharp peaks get higher, valleys get lower
        self.assertLess(probs[1, :].max(), warped_prob_sharp[1, :].max())
        self.assertGreater(probs[1, :].min(), warped_prob_sharp[1, :].min())

        # smooth peaks get lower, valleys get higher
        self.assertGreater(probs[1, :].max(), warped_prob_smooth[1, :].max())
        self.assertLess(probs[1, :].min(), warped_prob_smooth[1, :].min())

    def test_repetition_penalty_dist_process(self):
        input_ids = torch.tensor([[0, 1], [5, 0]], device=torch_device, dtype=torch.long)
        vocab_size = 10

        scores = self._get_uniform_logits(batch_size=2, length=vocab_size)

        # give values special values
        scores[0, 0] = -(1 / vocab_size)
        scores[1, 5] = 4 / vocab_size

        rep_penalty_proc = RepetitionPenaltyDistProcessor(penalty=2)

        scores = rep_penalty_proc(input_ids, scores.clone())

        # check that values were correctly changed
        self.assertAlmostEqual(scores[0, 0].item(), -(1 / vocab_size) * 2)
        self.assertAlmostEqual(scores[0, 1].item(), (1 / vocab_size) / 2)

        self.assertAlmostEqual(scores[1, 0].item(), (1 / vocab_size) / 2)
        self.assertAlmostEqual(scores[1, 5].item(), (4 / vocab_size) / 2)

    def test_top_k_dist_warper(self):
        input_ids = None
        vocab_size = 10
        batch_size = 2

        # create ramp distribution
        ramp_logits = (
            torch.arange(vocab_size, device=torch_device, dtype=torch.float).unsqueeze(0).repeat(batch_size, 1)
        )
        ramp_logits[1:, : vocab_size // 2] = ramp_logits[1:, : vocab_size // 2] + vocab_size

        top_k_warp = TopKDistWarper(3)

        scores = top_k_warp(input_ids, ramp_logits)

        # check that correct tokens are filtered
        self.assertListEqual(torch.isinf(scores[0]).tolist(), 7 * [True] + 3 * [False])
        self.assertListEqual(torch.isinf(scores[1]).tolist(), 2 * [True] + 3 * [False] + 5 * [True])

        # check special cases
        length = 5

        logits = self._get_uniform_logits(batch_size=batch_size, length=length)
        top_k_warp_safety_check = TopKDistWarper(k=1, filter_value=0.0, min_tokens_to_keep=3)

        scores = top_k_warp_safety_check(input_ids, logits)
        # uniform dist is not changed
        self.assertListEqual((scores == 0.0).to(torch.long).sum(dim=-1).tolist(), [0, 0])

        ramp_logits = torch.arange(length, device=torch_device, dtype=torch.float).unsqueeze(0).repeat(batch_size, 1)
        scores = top_k_warp_safety_check(input_ids, ramp_logits)

        # min_tokens overwrites k: 3 tokens are kept => 2 tokens are nullified
        self.assertListEqual((scores == 0.0).to(torch.long).sum(dim=-1).tolist(), [2, 2])

    def test_top_p_dist_warper(self):
        input_ids = None
        vocab_size = 10
        batch_size = 2

        # create distribution and take log (inverse to Softmax as taken in TopPDistWarper)
        dist = torch.log(
            torch.tensor([[0.3, 0.1, 0.1, 0.5], [0.2, 0.3, 0.3, 0.2]], device=torch_device, dtype=torch.float)
        )

        top_p_warp = TopPDistWarper(0.7)
        filtered_dist = torch.exp(top_p_warp(input_ids, dist))

        # dist should be filtered to keep min num values so that sum is >= 0.7
        # exp (-inf) => 0
        EXPECTED_FILTERED_DIST = torch.tensor(
            [[0.3, 0.0, 0.0, 0.5], [0.0, 0.3, 0.3, 0.2]], device=torch_device, dtype=torch.float
        )
        self.assertTrue(torch.allclose(filtered_dist, EXPECTED_FILTERED_DIST, atol=1e-3))

        # check edge cases with negative and extreme logits
        ramp_logits = torch.arange(vocab_size, device=torch_device, dtype=torch.float).unsqueeze(0).repeat(
            batch_size, 1
        ) - (vocab_size // 2)

        # make ramp_logits more extreme
        ramp_logits[1] = ramp_logits[1] * 100.0

        # make sure at least 2 tokens are kept
        top_p_warp = TopPDistWarper(0.9, min_tokens_to_keep=2, filter_value=0.0)
        filtered_dist = top_p_warp(input_ids, ramp_logits)

        # first batch should keep three tokens, second batch would keep only 1, but due to `min_tokens_to_keep=2` keeps 2.
        self.assertListEqual((filtered_dist != 0.0).to(torch.long).sum(dim=-1).tolist(), [3, 2])

    def test_no_repeat_ngram_dist_processor(self):
        vocab_size = 3
        batch_size = 2

        input_ids = torch.tensor([[1, 1, 2, 1], [0, 1, 0, 1]], device=torch_device, dtype=torch.long)
        scores = self._get_uniform_logits(batch_size, vocab_size)

        no_repeat_proc_2_gram = NoRepeatNGramDistProcessor(2)
        no_repeat_proc_3_gram = NoRepeatNGramDistProcessor(3)

        filtered_scores_2_gram = no_repeat_proc_2_gram(input_ids, scores.clone())
        filtered_scores_3_gram = no_repeat_proc_3_gram(input_ids, scores.clone())

        # 2-gram would forbid 2nd and 3rd token (1,2) at 1st batch and 1st token (0) at 2nd batch
        self.assertListEqual(torch.isinf(filtered_scores_2_gram).tolist(), [[False, True, True], [True, False, False]])

        # 3-gram would forbid no token at 1st batch and 1st token (0) at 2nd batch
        self.assertListEqual(
            torch.isinf(filtered_scores_3_gram).tolist(), [[False, False, False], [True, False, False]]
        )

    def test_no_bad_words_dist_processor(self):
        vocab_size = 5
        batch_size = 2
        eos_token_id = 4

        input_ids = torch.tensor([[0, 1, 3, 1], [0, 1, 0, 1]], device=torch_device, dtype=torch.long)
        bad_word_tokens = [[1], [4], [1, 0], [0, 1, 2], [1, 3, 1, 3]]
        scores = self._get_uniform_logits(batch_size, vocab_size)

        no_bad_words_dist_proc = NoBadWordsDistProcessor(bad_words_ids=bad_word_tokens, eos_token_id=eos_token_id)

        filtered_scores = no_bad_words_dist_proc(input_ids, scores.clone())

        # batch 1: 1st, 2nd, and 4th (0, 1, 3) token are forbidden
        # batch 2: 1st, 2nd, and 3rd (0, 1, 2) token are forbidden
        # Note that 5th element cannot be forbidden as it is EOS token
        self.assertListEqual(
            torch.isinf(filtered_scores).tolist(), [[True, True, False, True, False], [True, True, True, False, False]]
        )

        # check edge case
        no_bad_words_dist_proc = NoBadWordsDistProcessor(bad_words_ids=[[4]], eos_token_id=eos_token_id)
        filtered_scores = no_bad_words_dist_proc(input_ids, scores.clone())
        self.assertTrue(torch.allclose(scores, filtered_scores, atol=1e-3))

    def test_processor_list(self):
        batch_size = 4
        sequence_length = 10
        vocab_size = 15
        eos_token_id = 0

        # dummy input_ids and scores
        input_ids = ids_tensor((batch_size, sequence_length), vocab_size)
        input_ids_comp = input_ids.clone()

        scores = self._get_uniform_logits(batch_size, vocab_size)
        scores_comp = scores.clone()

        # instantiate all dist processors
        min_dist_proc = MinLengthDistProcessor(min_length=10, eos_token_id=eos_token_id)
        temp_dist_warp = TemperatureDistWarper(temperature=0.5)
        rep_penalty_proc = RepetitionPenaltyDistProcessor(penalty=2)
        top_k_warp = TopKDistWarper(3)
        top_p_warp = TopPDistWarper(0.8)
        no_repeat_proc = NoRepeatNGramDistProcessor(2)
        no_bad_words_dist_proc = NoBadWordsDistProcessor(bad_words_ids=[[1]], eos_token_id=eos_token_id)

        # no processor list
        scores = min_dist_proc(input_ids, scores)
        scores = temp_dist_warp(input_ids, scores)
        scores = rep_penalty_proc(input_ids, scores)
        scores = top_k_warp(input_ids, scores)
        scores = top_p_warp(input_ids, scores)
        scores = no_repeat_proc(input_ids, scores)
        scores = no_bad_words_dist_proc(input_ids, scores)

        # with processor list
        processor = DistProcessorList(
            [
                min_dist_proc,
                temp_dist_warp,
                rep_penalty_proc,
                top_k_warp,
                top_p_warp,
                no_repeat_proc,
                no_bad_words_dist_proc,
            ]
        )
        scores_comp = processor(input_ids, scores_comp)

        # scores should be equal
        self.assertTrue(torch.allclose(scores, scores_comp, atol=1e-3))

        # input_ids should never be changed
        self.assertListEqual(input_ids.tolist(), input_ids_comp.tolist())
