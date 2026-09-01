from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from src.ml.inference import predict


class TestPreprocess:
    def test_output_shape_is_1_3_224_224(self) -> None:
        img = Image.new("RGB", (500, 300), (120, 80, 200))
        out = predict._preprocess(img)
        assert out.shape == (1, 3, 224, 224)
        assert out.dtype == np.float32

    def test_values_normalized(self) -> None:
        # A solid-color image gives deterministic, finite normalized values.
        img = Image.new("RGB", (224, 224), (128, 128, 128))
        out = predict._preprocess(img)
        assert np.isfinite(out).all()
        # 128/255 scaled by mean/std -> roughly around 0
        assert abs(float(out.mean())) < 1.0

    def test_grayscale_converted_to_rgb(self) -> None:
        img = Image.new("L", (224, 224), 100)
        out = predict._preprocess(img)
        assert out.shape == (1, 3, 224, 224)

    def test_resize_preserves_batch_dim(self) -> None:
        img = Image.new("RGB", (100, 100), (10, 20, 30))
        out = predict._preprocess(img)
        assert out.shape[0] == 1
        assert out.shape[1] == 3


class TestGetModelInfo:
    def test_info_contract(self) -> None:
        info = predict.get_model_info()
        assert "model_exists" in info
        assert "onnx_exists" in info
        assert "num_classes" in info
        assert "classes" in info
        assert isinstance(info["num_classes"], int)
        assert info["num_classes"] >= 4

    def test_class_names_have_expected_defaults(self) -> None:
        # configs/class_names.json may not exist; at minimum defaults are present
        assert set(predict.CLASS_NAMES) >= {"pothole", "garbage"}

    def test_model_info_device_is_str(self) -> None:
        info = predict.get_model_info()
        assert isinstance(info["device"], str)
        assert info["device"] in ("cpu", "cuda")
