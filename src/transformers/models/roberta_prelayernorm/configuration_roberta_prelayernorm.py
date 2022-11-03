# coding=utf-8
# Copyright 2022 The Google AI Language Team Authors and The HuggingFace Inc. team.
# Copyright (c) 2018, NVIDIA CORPORATION.  All rights reserved.
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
""" RoBERTa-PreLayerNorm configuration"""
from collections import OrderedDict
from typing import Mapping

from ...onnx import OnnxConfig
from ...utils import logging
from ..bert.configuration_bert import BertConfig


logger = logging.get_logger(__name__)

ROBERTA_PRELAYERNORM_PRETRAINED_CONFIG_ARCHIVE_MAP = {
    "princeton-nlp/efficient_mlm_m0.40": "https://huggingface.co/princeton-nlp/efficient_mlm_m0.40/resolve/main/config.json",
}



class RobertaPreLayerNormConfig(BertConfig):
    r"""
    This is the configuration class to store the configuration of a [`RobertaPreLayerNormModel`] or a [`TFRobertaPreLayerNormModel`]. It is
    used to instantiate a RoBERTa-PreLayerNorm model according to the specified arguments, defining the model architecture.
    Instantiating a configuration with the defaults will yield a similar configuration to that of the RoBERTa-PreLayerNorm
    [princeton-nlp/efficient_mlm_m0.40](https://huggingface.co/princeton-nlp/efficient_mlm_m0.40) architecture.

    Configuration objects inherit from [`PretrainedConfig`] and can be used to control the model outputs. Read the
    documentation from [`PretrainedConfig`] for more information.

    The [`RobertaPreLayerNormConfig`] class directly inherits [`BertConfig`]. It reuses the same defaults. Please check the parent
    class for more information.

    Examples:

    ```python
    >>> from transformers import RobertaPreLayerNormConfig, RobertaPreLayerNormModel

    >>> # Initializing a RoBERTa-PreLayerNorm configuration
    >>> configuration = RobertaPreLayerNormConfig()

    >>> # Initializing a model (with random weights) from the configuration
    >>> model = RobertaPreLayerNormModel(configuration)

    >>> # Accessing the model configuration
    >>> configuration = model.config
    ```"""
    model_type = "roberta-prelayernorm"

    def __init__(self, pad_token_id=1, bos_token_id=0, eos_token_id=2, **kwargs):
        """Constructs RobertaPreLayerNormConfig."""
        super().__init__(pad_token_id=pad_token_id, bos_token_id=bos_token_id, eos_token_id=eos_token_id, **kwargs)


class RobertaPreLayerNormOnnxConfig(OnnxConfig):
    @property
    def inputs(self) -> Mapping[str, Mapping[int, str]]:
        if self.task == "multiple-choice":
            dynamic_axis = {0: "batch", 1: "choice", 2: "sequence"}
        else:
            dynamic_axis = {0: "batch", 1: "sequence"}
        return OrderedDict(
            [
                ("input_ids", dynamic_axis),
                ("attention_mask", dynamic_axis),
            ]
        )
