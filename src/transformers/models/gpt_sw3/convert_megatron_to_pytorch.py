####################################################################################################

# From: https://github.com/NVIDIA/NeMo/blob/117029aef03b86359a0b777079f8f39515cacf0e/nemo/collections/nlp/models/language_modeling/megatron/gpt_model.py#L94
# Original model settings parameters:
#
#   Note: This relates to attention
#   apply_query_key_layer_scaling=True, # This is set to True in config
#   normalize_attention_scores=True,    # TODO: Verify that this is True by default in Nemo Megatron GPT implementation
#
#       See: https://github.com/NVIDIA/NeMo/blob/117029aef03b86359a0b777079f8f39515cacf0e/nemo/collections/nlp/modules/common/megatron/transformer.py#L414
#
#       coeff = None
#       self.norm_factor = math.sqrt(self.hidden_size_per_attention_head) # -> sqrt(attention head dim)
#       if self.apply_query_key_layer_scaling:
#           coeff = self.layer_number
#           self.norm_factor *= coeff
#
#       matmul_result = torch.baddbmm(
#             matmul_input_buffer,
#             query_layer.transpose(0, 1),  # [b * np, sq, hn]
#             key_layer.transpose(0, 1).transpose(1, 2),  # [b * np, hn, sk]
#             beta=0.0,
#             alpha=(1.0 / self.norm_factor) if self.normalize_attention_scores else 1.0,
#         )
#
#         See: https://pytorch.org/docs/stable/generated/torch.baddbmm.html
#         alpha (Number, optional) – multiplier for batch1 @ batch2 (alpha)
#
#
#   kv_channels=None,
#
#   pre_process=True,
#       Seems to be Megatron specific and not relevant for hf implementation.
#
#   post_process=True,
#       See: https://github.com/NVIDIA/NeMo/blob/117029aef03b86359a0b777079f8f39515cacf0e/nemo/collections/nlp/models/language_modeling/megatron/gpt_model.py#L39
#       Seems to be Megatron specific and not relevant for hf implementation.
#   TODO: if comparison with NeMo fails recheck this!
#
#   init_method_std=0.02,
#   use_scaled_init_method=True,
#   hidden_dropout=0.1,
#   precision=16,
#
#   normalization='layernorm',
#   layernorm_epsilon=1e-5,
#
#   transformer_block_type='pre_ln',
#       See: https://github.com/NVIDIA/NeMo/blob/117029aef03b86359a0b777079f8f39515cacf0e/nemo/collections/nlp/modules/common/megatron/transformer.py#L1835
#       # Pre-LN: x -> LN -> MHA -> Residual -> LN -> MLP -> Residual
#
#   openai_gelu=False,
#   activation='gelu',
#       Nemo uses this one without approximate argument:
#       https://pytorch.org/docs/stable/generated/torch.nn.functional.gelu.html
#
#   From Megatron:
#   trainer:
#       precision: bf16
#

import argparse
import os
import re
import zipfile
from os.path import join, isfile

import torch

from transformers import AutoTokenizer, GptSw3Config


####################################################################################################


def recursive_print(name, val, spaces=0):
    # Format the message.
    if name is None:
        msg = None
    else:
        fmt = "." * max(0, spaces - 2) + "# {:" + str(50 - spaces) + "s}"
        msg = fmt.format(name)

    # Print and recurse (if needed).
    if isinstance(val, dict):
        if msg is not None:
            print(msg)
        for k in val.keys():
            recursive_print(k, val[k], spaces + 2)
    elif isinstance(val, torch.Tensor):
        print(msg, ":", val.size())
    else:
        print(msg, ":", val)


def fix_query_key_value_ordering(param, num_splits, num_heads, hidden_size):
    # Permutes layout of param tensor to [num_splits * num_heads * hidden_size, :]
    # for compatibility with later versions of NVIDIA Megatron-LM.
    # The inverse operation is performed inside Megatron-LM to read checkpoints:
    # https://github.com/NVIDIA/Megatron-LM/blob/v2.4/megatron/checkpointing.py#L209
    # If param is the weight tensor of the self-attention block, the returned tensor
    # will have to be transposed one more time to be read by HuggingFace GPT2.
    input_shape = param.size()
    # other versions store [num_heads * num_splits * hidden_size, :]
    saved_shape = (num_heads, num_splits, hidden_size) + input_shape[1:]
    param = param.view(*saved_shape)
    param = param.transpose(0, 1).contiguous()
    param = param.view(*input_shape)
    return param


def convert_megatron_checkpoint(sd_megatron, config):
    """
    Converts a Megatron checkpoint to a HuggingFace GPT-SW3 checkpoint.
    """
    # n_positions = config.n_positions
    layers = config.n_layer
    vocab_size = config.vocab_size
    # heads = config.n_head
    # hidden_size_per_head = config.n_embd // config.n_head

    word_embeddings = sd_megatron["model.language_model.embedding.word_embeddings.weight"][: vocab_size, :]
    sd_hf = {
        "transformer.wte.weight": word_embeddings,
        "transformer.wpe.weight": sd_megatron["model.language_model.embedding.position_embeddings.weight"],
        "transformer.ln_f.weight": sd_megatron["model.language_model.encoder.final_layernorm.weight"],
        "transformer.ln_f.bias": sd_megatron["model.language_model.encoder.final_layernorm.bias"]}

    pf = "model.language_model.encoder.layers."
    for i in range(layers):
        sd_hf[f"transformer.h.{i}.ln_1.weight"] = sd_megatron[f"{pf}{i}.input_layernorm.weight"]
        sd_hf[f"transformer.h.{i}.ln_1.bias"] = sd_megatron[f"{pf}{i}.input_layernorm.bias"]
        val1 = sd_megatron[f"{pf}{i}.self_attention.query_key_value.weight"]
        sd_hf[f"transformer.h.{i}.attn.c_attn.weight"] = val1
        val2 = sd_megatron[f"{pf}{i}.self_attention.query_key_value.bias"]
        sd_hf[f"transformer.h.{i}.attn.c_attn.bias"] = val2
        sd_hf[f"transformer.h.{i}.attn.c_proj.weight"] = sd_megatron[f"{pf}{i}.self_attention.dense.weight"]
        sd_hf[f"transformer.h.{i}.attn.c_proj.bias"] = sd_megatron[f"{pf}{i}.self_attention.dense.bias"]
        sd_hf[f"transformer.h.{i}.ln_2.weight"] = sd_megatron[f"{pf}{i}.post_attention_layernorm.weight"]
        sd_hf[f"transformer.h.{i}.ln_2.bias"] = sd_megatron[f"{pf}{i}.post_attention_layernorm.bias"]
        sd_hf[f"transformer.h.{i}.mlp.c_fc.weight"] = sd_megatron[f"{pf}{i}.mlp.dense_h_to_4h.weight"]
        sd_hf[f"transformer.h.{i}.mlp.c_fc.bias"] = sd_megatron[f"{pf}{i}.mlp.dense_h_to_4h.bias"]
        sd_hf[f"transformer.h.{i}.mlp.c_proj.weight"] = sd_megatron[f"{pf}{i}.mlp.dense_4h_to_h.weight"]
        sd_hf[f"transformer.h.{i}.mlp.c_proj.bias"] = sd_megatron[f"{pf}{i}.mlp.dense_4h_to_h.bias"]

    # For LM head, transformers' wants the matrix to weight embeddings.
    sd_hf["lm_head.weight"] = word_embeddings

    return sd_hf


def copy_config(config_hf, config_megatron):
    """Copy the config from Megatron to hf."""
    config_hf.vocab_size = 64000
    config_hf.n_positions = config_megatron["encoder_seq_length"]
    config_hf.n_embd = config_megatron["hidden_size"]
    config_hf.n_layer = config_megatron["num_layers"]
    config_hf.n_head = config_megatron["num_attention_heads"]
    config_hf.n_inner = config_megatron["ffn_hidden_size"]
    config_hf.activation_function = "gelu"
    config_hf.resid_pdrop = 0.1
    config_hf.embd_pdrop = 0.1
    config_hf.attn_pdrop = 0.1
    config_hf.layer_norm_epsilon = config_megatron["layernorm_epsilon"]  # 1e-5
    config_hf.initializer_range = config_megatron["init_method_std"]  # 0.02
    config_hf.apply_query_key_layer_scaling = config_megatron["apply_query_key_layer_scaling"]  # True
    config_hf.normalize_attention_scores = True
    config_hf.use_cache = False
    config_hf.bos_token_id = 3
    config_hf.eos_token_id = 3
    config_hf.pad_token_id = 3
    return config_hf


def main(args):
    checkpoint_path = args.checkpoint_path
    save_path = args.save_path
    assert isfile(checkpoint_path), f"ERROR! could not find file {checkpoint_path}"

    # Load the model.
    checkpoint = torch.load(checkpoint_path, map_location="cpu")

    # Load the config.
    config_megatron = checkpoint["hyper_parameters"]["cfg"]
    config_hf = copy_config(config_hf=GptSw3Config(), config_megatron=config_megatron)
    config_hf.architectures = ["GptSw3LMHeadModel"]

    sd_megatron = checkpoint["state_dict"]

    # Convert.
    print("Converting")
    sd_hf = convert_megatron_checkpoint(sd_megatron, config_hf)

    # Print the structure of converted state dict.
    if args.print_checkpoint_structure:
        recursive_print(None, sd_hf)

    config_hf.tokenizer_class = "GptSw3Tokenizer"

    # TODO: investigate what should be saved here, especially considering we only use spiece.model as tokenizer
    #  1. config is probably correct
    #  2. torch.save for model is probably correct
    # Store the config to file.
    print("Saving config")
    config_hf.save_pretrained(save_path)

    # Store the state_dict to file.
    output_checkpoint_file = os.path.join(save_path, "pytorch_model.bin")
    print(f'Saving checkpoint to "{output_checkpoint_file}"')
    torch.save(sd_hf, output_checkpoint_file)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--checkpoint_path",
        type=str,
        required=True,
        help="e.g. megatron_gpt--val_loss=2.42-step=38000-consumed_samples=54720000"
    )
    parser.add_argument(
        "--save_path",
        type=str,
        required=True,
        help="e.g. /home/user/gpt-sw3/hf"
    )
    parser.add_argument(
        "--print-checkpoint-structure",
        action="store_true",
    )
    _args = parser.parse_args()
    main(_args)
