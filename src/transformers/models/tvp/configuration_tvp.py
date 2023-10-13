# coding=utf-8
# Copyright 2023 The Intel AIA Team Authors, and HuggingFace Inc. team. All rights reserved.
#
# Licensed under the Apache License=, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing=, software
# distributed under the License is distributed on an "AS IS" BASIS=,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND=, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
""" TVP model configuration"""

import copy
from ...configuration_utils import PretrainedConfig
from ...utils import logging
from ..auto import CONFIG_MAPPING


logger = logging.get_logger(__name__)


TVP_PRETRAINED_CONFIG_ARCHIVE_MAP = {
    "Intel/tvp-base": "https://huggingface.co/Intel/tvp-base/resolve/main/config.json",
}


class TvpConfig(PretrainedConfig):
    r"""
    This is the configuration class to store the configuration of a [`TvpModel`]. It is used to instantiate an Tvp
    model according to the specified arguments, defining the model architecture. Instantiating a configuration with the
    defaults will yield a similar configuration to that of the Tvp
    [Intel/tvp-base](https://huggingface.co/Intel/tvp-base) architecture.

    Configuration objects inherit from [`PretrainedConfig`] and can be used to control the model outputs. Read the
    documentation from [`PretrainedConfig`] for more information.


    Args:
        backbone_config (`PretrainedConfig` or `dict`, *optional*):
            The configuration of the backbone model.
        alpha (`float`, *optional*, defaults to 1.0):
            The weight of distance loss.
        beta (`float`, *optional*, defaults to 0.1):
            The weight of duration loss.
        visual_prompter_type (`str`, *optional*, defaults to `"framepad"`):
            Visual prompt type. The type of padding. Framepad means padding on each frame.
        visual_prompter_apply (`str`, *optional*, defaults to `"replace"`):
            The way of applying visual prompt. Replace means use the value of prompt to change the original value in
            visual inputs.
        max_img_size (`int`, *optional*, defaults to 448):
            The maximum size of image.
        pad_size (`int`, *optional*, defaults to 96):
            The maximum size of padding.
        num_frm (`int`, *optional*, defaults to 48):
            There are num_frm frames extracted from a video.
        vocab_size (`int`, *optional*, defaults to 30522):
            Vocabulary size of the Tvp text model. Defines the number of different tokens that can be represented by
            the `inputs_ids` passed when calling [`TvpModel`].
        hidden_size (`int`, *optional*, defaults to 768):
            Dimensionality of the encoder layers.
        intermediate_size (`int`, *optional*, defaults to 3072):
            Dimensionality of the "intermediate" (i.e., feed-forward) layer in the Transformer encoder.
        num_hidden_layers (`int`, *optional*, defaults to 12):
            Number of hidden layers in the Transformer encoder.
        num_attention_heads (`int`, *optional*, defaults to 12):
            Number of attention heads for each attention layer in the Transformer encoder.
        max_position_embeddings (`int`, *optional*, defaults to 512):
            The maximum sequence length that this model might ever be used with. Typically set this to something large
            just in case (e.g., 512 or 1024 or 2048).
        max_grid_col_position_embeddings (`int`, *optional*, defaults to 100):
            The maximum column sequence length of visual position embeddings.
        max_grid_row_position_embeddings (`int`, *optional*, defaults to 100):
            The maximum row sequence length of visual position embeddings.
        hidden_dropout_prob (`float`, *optional*, defaults to 0.1):
            The dropout probability of hidden layers.
        hidden_act (`str` or `function`, *optional*, defaults to `"gelu"`):
            The non-linear activation function (function or string) in the encoder and pooler. If string, `"gelu"`,
            `"relu"`, `"selu"` and `"gelu_new"` ``"quick_gelu"` are supported.
        layer_norm_eps (`float`, *optional*, defaults to 1e-12):
            The epsilon used by the layer normalization layers.
        attention_dropout (`float`, *optional*, defaults to 0.0):
            The dropout ratio for the attention probabilities.
        initializer_range (`float`, *optional*, defaults to 0.02):
            The standard deviation of the truncated_normal_initializer for initializing all weight matrices.
        attention_probs_dropout_prob (`float`, *optional*, defaults to 0.1):
            The dropout probability of attention layers.
    """

    model_type = "tvp"

    def __init__(
        self,
        backbone_config=None,
        alpha=1.0,
        beta=0.1,
        visual_prompter_type="framepad",
        visual_prompter_apply="replace",
        max_img_size=448,
        pad_size=96,
        num_frm=48,
        vocab_size=30522,
        hidden_size=768,
        intermediate_size=3072,
        num_hidden_layers=12,
        num_attention_heads=12,
        max_position_embeddings=512,
        max_grid_col_position_embeddings=100,
        max_grid_row_position_embeddings=100,
        hidden_dropout_prob=0.1,
        hidden_act="gelu",
        layer_norm_eps=1e-12,
        initializer_range=0.02,
        pad_token_id=0,
        type_vocab_size=2,
        attention_probs_dropout_prob=0.1,
        **kwargs,
    ):
        super().__init__(pad_token_id=pad_token_id, **kwargs)

        if backbone_config is None:
            logger.info("`backbone_config` is `None`. Initializing the config with the default `ResNet` backbone.")
            backbone_config = CONFIG_MAPPING["resnet"](out_features=["stage4"])
        elif isinstance(backbone_config, dict):
            backbone_model_type = backbone_config.get("model_type")
            config_class = CONFIG_MAPPING[backbone_model_type]
            backbone_config = config_class.from_dict(backbone_config)

        self.backbone_config = backbone_config
        self.alpha = alpha
        self.beta = beta
        self.visual_prompter_type = visual_prompter_type
        self.visual_prompter_apply = visual_prompter_apply
        self.max_img_size = max_img_size
        self.pad_size = pad_size
        self.num_frm = num_frm
        self.vocab_size = vocab_size
        self.hidden_size = hidden_size
        self.intermediate_size = intermediate_size
        self.num_hidden_layers = num_hidden_layers
        self.num_attention_heads = num_attention_heads
        self.max_position_embeddings = max_position_embeddings
        self.max_grid_col_position_embeddings = max_grid_col_position_embeddings
        self.max_grid_row_position_embeddings = max_grid_row_position_embeddings
        self.layer_norm_eps = layer_norm_eps
        self.hidden_dropout_prob = hidden_dropout_prob
        self.hidden_act = hidden_act
        self.initializer_range = initializer_range
        self.type_vocab_size = type_vocab_size
        self.attention_probs_dropout_prob = attention_probs_dropout_prob

    @classmethod
    def from_backbone_config(cls, backbone_config: PretrainedConfig, **kwargs):
        """Instantiate a [`TvpConfig`] (or a derived class) from a pre-trained backbone model configuration.

        Args:
            backbone_config ([`PretrainedConfig`]):
                The backbone configuration.
        Returns:
            [`TvpConfig`]: An instance of a configuration object
        """
        return cls(backbone_config=backbone_config, **kwargs)

    def to_dict(self):
        """
        Serializes this instance to a Python dictionary. Override the default [`~PretrainedConfig.to_dict`].

        Returns:
            `Dict[str, any]`: Dictionary of all the attributes that make up this configuration instance,
        """
        output = copy.deepcopy(self.__dict__)
        if output["backbone_config"] is not None:
            output["backbone_config"] = self.backbone_config.to_dict()
        output["model_type"] = self.__class__.model_type
        return output
