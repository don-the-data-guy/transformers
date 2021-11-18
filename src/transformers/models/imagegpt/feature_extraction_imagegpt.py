# coding=utf-8
# Copyright 2021 The HuggingFace Inc. team. All rights reserved.
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
"""Feature extractor class for ImageGPT."""

from typing import List, Optional, Union

import numpy as np
from PIL import Image

from ...feature_extraction_utils import BatchFeature, FeatureExtractionMixin
from ...file_utils import TensorType
from ...image_utils import ImageFeatureExtractionMixin, is_torch_tensor
from ...utils import logging


logger = logging.get_logger(__name__)


def squared_euclidean_distance(a, b):
    b = b.T
    a2 = np.sum(np.square(a), axis=1)
    b2 = np.sum(np.square(b), axis=0)
    ab = np.matmul(a, b)
    d = a2[:, None] - 2 * ab + b2[None, :]
    return d


def color_quantize(x, clusters):
    x = x.reshape(-1, 3)
    d = squared_euclidean_distance(x, clusters)
    return np.argmin(d, axis=1)


class ImageGPTFeatureExtractor(FeatureExtractionMixin, ImageFeatureExtractionMixin):
    r"""
    Constructs an ImageGPT feature extractor. This feature extractor can be used to resize images to a smaller
    resolution (such as 32x32 or 64x64), normalize them and finally color quantize them to obtain sequences of "pixel
    values" (color clusters).

    This feature extractor inherits from :class:`~transformers.FeatureExtractionMixin` which contains most of the main
    methods. Users should refer to this superclass for more information regarding those methods.

    Args:
        clusters (:obj:`np.ndarray`):
            The color clusters to use, as a :obj:`np.ndarray` of shape :obj:`(n_clusters, 3)`.
        do_resize (:obj:`bool`, `optional`, defaults to :obj:`True`):
            Whether to resize the input to a certain :obj:`size`.
        size (:obj:`int` or :obj:`Tuple(int)`, `optional`, defaults to 32):
            Resize the input to the given size. If a tuple is provided, it should be (width, height). If only an
            integer is provided, then the input will be resized to (size, size). Only has an effect if :obj:`do_resize`
            is set to :obj:`True`.
        resample (:obj:`int`, `optional`, defaults to :obj:`PIL.Image.BILINEAR`):
            An optional resampling filter. This can be one of :obj:`PIL.Image.NEAREST`, :obj:`PIL.Image.BOX`,
            :obj:`PIL.Image.BILINEAR`, :obj:`PIL.Image.HAMMING`, :obj:`PIL.Image.BICUBIC` or :obj:`PIL.Image.LANCZOS`.
            Only has an effect if :obj:`do_resize` is set to :obj:`True`.
        do_normalize (:obj:`bool`, `optional`, defaults to :obj:`True`):
            Whether or not to normalize the input to the range between -1 and +1.
    """

    model_input_names = ["pixel_values"]

    def __init__(self, clusters, do_resize=True, size=32, resample=Image.BILINEAR, do_normalize=True, **kwargs):
        super().__init__(**kwargs)
        self.clusters = clusters
        self.do_resize = do_resize
        self.size = size
        self.resample = resample
        self.do_normalize = do_normalize

    def normalize(self, image):
        """
        Normalizes :obj:`image` into the range -1 to +1.

        Args:
            image (:obj:`PIL.Image.Image` or :obj:`np.ndarray` or :obj:`torch.Tensor`):
                The image to normalize.

        Returns:
            :obj:`np.ndarray`: The normalized image.
        """
        image = self.to_numpy_array(image, rescale=False, channel_first=False)

        return image / 127.5 - 1

    def __call__(
        self,
        images: Union[
            Image.Image, np.ndarray, "torch.Tensor", List[Image.Image], List[np.ndarray], List["torch.Tensor"]  # noqa
        ],
        return_tensors: Optional[Union[str, TensorType]] = None,
        **kwargs
    ) -> BatchFeature:
        """
        Main method to prepare for the model one or several image(s).

        .. warning::

           NumPy arrays and PyTorch tensors are converted to PIL images when resizing, so the most efficient is to pass
           PIL images.

        Args:
            images (:obj:`PIL.Image.Image`, :obj:`np.ndarray`, :obj:`torch.Tensor`, :obj:`List[PIL.Image.Image]`, :obj:`List[np.ndarray]`, :obj:`List[torch.Tensor]`):
                The image or batch of images to be prepared. Each image can be a PIL image, NumPy array or PyTorch
                tensor. In case of a NumPy array/PyTorch tensor, each image should be of shape (C, H, W), where C is a
                number of channels, H and W are image height and width.

            return_tensors (:obj:`str` or :class:`~transformers.file_utils.TensorType`, `optional`, defaults to :obj:`'np'`):
                If set, will return tensors of a particular framework. Acceptable values are:

                * :obj:`'tf'`: Return TensorFlow :obj:`tf.constant` objects.
                * :obj:`'pt'`: Return PyTorch :obj:`torch.Tensor` objects.
                * :obj:`'np'`: Return NumPy :obj:`np.ndarray` objects.
                * :obj:`'jax'`: Return JAX :obj:`jnp.ndarray` objects.

        Returns:
            :class:`~transformers.BatchFeature`: A :class:`~transformers.BatchFeature` with the following fields:

            - **pixel_values** -- Pixel values to be fed to a model, of shape (batch_size, num_channels, height,
              width).
        """
        # Input type checking for clearer error
        valid_images = False

        # Check that images has a valid type
        if isinstance(images, (Image.Image, np.ndarray)) or is_torch_tensor(images):
            valid_images = True
        elif isinstance(images, (list, tuple)):
            if len(images) == 0 or isinstance(images[0], (Image.Image, np.ndarray)) or is_torch_tensor(images[0]):
                valid_images = True

        if not valid_images:
            raise ValueError(
                "Images must of type `PIL.Image.Image`, `np.ndarray` or `torch.Tensor` (single example), "
                "`List[PIL.Image.Image]`, `List[np.ndarray]` or `List[torch.Tensor]` (batch of examples)."
            )

        is_batched = bool(
            isinstance(images, (list, tuple))
            and (isinstance(images[0], (Image.Image, np.ndarray)) or is_torch_tensor(images[0]))
        )

        if not is_batched:
            images = [images]

        # transformations (resizing + normalization)
        if self.do_resize and self.size is not None:
            images = [self.resize(image, size=self.size, resample=self.resample) for image in images]

        if self.do_normalize:
            images = [self.normalize(image) for image in images]

        # color quantize from (batch_size, height, width, 3) to (batch_size, height, width)
        images = np.array(images)
        images = color_quantize(images, self.clusters).reshape(images.shape[:-1])

        # flatten to (batch_size, height*width)
        batch_size = images.shape[0]
        images = images.reshape(batch_size, -1)

        # return as BatchFeature
        data = {"pixel_values": images}
        encoded_inputs = BatchFeature(data=data, tensor_type=return_tensors)

        return encoded_inputs
