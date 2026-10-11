from __future__ import annotations

import logging

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


class TestWarmupModel:
    """Startup preload (predict.warmup_model) is fail-open and artifact-driven.

    It must load ONNX when present, fall back to a PyTorch artifact, and — most
    importantly — never download pretrained weights at boot, and never raise,
    because the lifespan treats it as optional.
    """

    def test_skips_without_artifacts(self, monkeypatch, tmp_path, caplog) -> None:
        missing = tmp_path / "nope"
        monkeypatch.setattr(predict, "ONNX_PATH", missing)
        monkeypatch.setattr(predict, "ADAPTER_DIR", missing / "adapter")
        monkeypatch.setattr(predict, "MODEL_PATH", missing / "model.pth")

        def _fail(*args, **kwargs) -> None:
            pytest.fail("warmup must not attempt a load when no artifact exists")

        monkeypatch.setattr(predict, "_get_onnx_session", _fail)
        monkeypatch.setattr(predict, "_get_torch_model", _fail)

        with caplog.at_level(logging.INFO, logger="src.ml.inference.predict"):
            predict.warmup_model()

        assert "No loadable model artifact" in caplog.text

    def test_loads_onnx_when_present(self, monkeypatch, tmp_path, caplog) -> None:
        onnx_file = tmp_path / "model.onnx"
        onnx_file.touch()
        monkeypatch.setattr(predict, "ONNX_PATH", onnx_file)

        loaded: list[str] = []
        monkeypatch.setattr(predict, "_get_onnx_session", lambda: loaded.append("onnx") or object())

        with caplog.at_level(logging.INFO, logger="src.ml.inference.predict"):
            predict.warmup_model()

        assert loaded == ["onnx"]
        assert "Model warmup complete: onnx:model.onnx" in caplog.text

    def test_falls_back_to_torch_artifact(self, monkeypatch, tmp_path, caplog) -> None:
        missing = tmp_path / "nope"
        model_file = tmp_path / "model.pth"
        model_file.touch()
        monkeypatch.setattr(predict, "ONNX_PATH", missing)
        monkeypatch.setattr(predict, "ADAPTER_DIR", missing / "adapter")
        monkeypatch.setattr(predict, "MODEL_PATH", model_file)

        loaded: list[str] = []
        monkeypatch.setattr(predict, "_get_torch_model", lambda: loaded.append("torch") or object())

        with caplog.at_level(logging.INFO, logger="src.ml.inference.predict"):
            predict.warmup_model()

        assert loaded == ["torch"]
        assert "Model warmup complete" in caplog.text

    def test_fail_open_on_load_error(self, monkeypatch, tmp_path, caplog) -> None:
        missing = tmp_path / "nope"
        onnx_file = tmp_path / "model.onnx"
        onnx_file.touch()
        monkeypatch.setattr(predict, "ONNX_PATH", onnx_file)
        monkeypatch.setattr(predict, "ADAPTER_DIR", missing / "adapter")
        monkeypatch.setattr(predict, "MODEL_PATH", missing / "model.pth")

        def _raise(*args, **kwargs) -> None:
            raise RuntimeError("boom")

        monkeypatch.setattr(predict, "_get_onnx_session", _raise)

        with caplog.at_level(logging.WARNING, logger="src.ml.inference.predict"):
            predict.warmup_model()  # must not raise

        assert "Model warmup (ONNX) failed" in caplog.text
