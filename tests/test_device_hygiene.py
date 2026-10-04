import pytest
import torch
import pandas as pd
from unittest import mock
from src.pipeline.device_utils import resolve_device, verify_device_execution
from src.nlp.finbert_inference import FinBERT, infer_csv
from src.pipeline.validators import assert_no_leakage

def test_device_cpu_resolves_to_cpu():
    assert resolve_device("cpu") == "cpu"

@mock.patch("torch.cuda.is_available", return_value=True)
def test_device_auto_resolves_to_cuda_when_available(mock_is_available):
    assert resolve_device("auto").startswith("cuda")
    assert resolve_device(None).startswith("cuda")

@mock.patch("torch.cuda.is_available", return_value=False)
def test_device_auto_resolves_to_cpu_when_unavailable(mock_is_available):
    assert resolve_device("auto") == "cpu"
    assert resolve_device(None) == "cpu"

@mock.patch("torch.cuda.is_available", return_value=False)
def test_device_cuda_fails_when_unavailable(mock_is_available):
    with pytest.raises(RuntimeError, match="GPU REQUIREMENT FAILED"):
        resolve_device("cuda")

def test_model_device_mismatch():
    class DummyModel(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.linear = torch.nn.Linear(1, 1)

    model = DummyModel() # on CPU by default
    # Suppose we expect cuda but model is on CPU
    with pytest.raises(RuntimeError, match="GPU EXECUTION FAILED: Model is on cpu, but expected cuda"):
        verify_device_execution(model, [], "cuda")

def test_tensor_device_mismatch():
    class DummyModel(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.linear = torch.nn.Linear(1, 1)
            
    model = DummyModel() # cpu
    tensors = [torch.tensor([1.0], device="cpu")]
    # model and tensor match their actual device (cpu), but if we expect cpu, should pass
    verify_device_execution(model, tensors, "cpu")
    
    # If we expected them to be on cuda but they are on CPU, it would fail
    # However we already know model mismatch fails first. Let's spoof the model device check
    # to only test tensor failure.
    # Actually just pass model on CPU but we expect CPU. Then pass a GPU tensor if possible... 
    # Hard to mock a GPU tensor if CUDA is not available. 
    # Let's mock the tensor's device property.
    class MockTensor:
        def __init__(self, dev_type):
            self.device = torch.device(dev_type)
            
    tensors = [MockTensor("cuda")]
    with pytest.raises(RuntimeError, match="GPU EXECUTION FAILED: Tensor 0 is on cuda, but expected cpu"):
        verify_device_execution(model, tensors, "cpu")

def test_leakage_guard():
    df_clean = pd.DataFrame({"TWEET": ["hello", "world"]})
    # Should not raise
    assert_no_leakage(df_clean)
    
    df_leaky = pd.DataFrame({"TWEET": ["hello"], "1_DAY_RETURN": [0.05]})
    with pytest.raises(ValueError, match="LEAKAGE GUARD TRIGGERED"):
        assert_no_leakage(df_leaky)
