import torch

_LOGGED_MODELS = set()

def resolve_device(requested_device: str | None = None) -> str:
    """
    Strict device selection for GPU execution hygiene.

    Behavior:
    - If `requested_device` is "cuda" (or "cuda:X"):
      - Requires CUDA. Fails loudly if CUDA is unavailable.
      - Never silently falls back to CPU.
    - If `requested_device` is "cpu":
      - Uses CPU intentionally.
    - If `requested_device` is "auto" or None:
      - Uses CUDA if available, else CPU.
    """
    if requested_device is None:
        requested_device = "auto"

    requested_device = requested_device.lower().strip()

    cuda_available = torch.cuda.is_available()

    if requested_device.startswith("cuda"):
        if not cuda_available:
            raise RuntimeError(
                f"GPU REQUIREMENT FAILED: Device '{requested_device}' was requested, "
                "but torch.cuda.is_available() is False. "
                "Will NOT silently fall back to CPU."
            )
        return requested_device

    if requested_device == "cpu":
        return "cpu"

    if requested_device == "auto":
        return "cuda" if cuda_available else "cpu"

    # Default fallback for unrecognized explicit strings
    raise ValueError(f"Unrecognized device request: '{requested_device}'. Use 'cuda', 'cpu', or 'auto'.")

def verify_device_execution(model, tensors: list[torch.Tensor] | dict[str, torch.Tensor], expected_device_str: str) -> None:
    """
    Verifies that the model and inputs are on the expected device.
    Logs actual execution parameters.
    """
    expected_device = torch.device(expected_device_str)
    
    # 1. Check Model Device
    # Get the device of the first parameter
    try:
        model_device = next(model.parameters()).device
    except StopIteration:
        model_device = expected_device # No parameters

    if model_device.type != expected_device.type:
        raise RuntimeError(
            f"GPU EXECUTION FAILED: Model is on {model_device.type}, "
            f"but expected {expected_device.type}."
        )

    # 2. Check Tensors Device
    if isinstance(tensors, dict):
        tensor_list = list(tensors.values())
    else:
        tensor_list = tensors
        
    for i, t in enumerate(tensor_list):
        if hasattr(t, "device") and t.device.type != expected_device.type:
            raise RuntimeError(
                f"GPU EXECUTION FAILED: Tensor {i} is on {t.device.type}, "
                f"but expected {expected_device.type}."
            )

    # 3. Log real device stats (only once per model instance to avoid spamming)
    model_id = id(model)
    if model_id not in _LOGGED_MODELS:
        cuda_available = torch.cuda.is_available()
        gpu_name = torch.cuda.get_device_name(expected_device) if expected_device.type == "cuda" else "N/A"
        
        print(f"--- GPU Execution Verification ---")
        print(f"Requested/Resolved device: {expected_device_str}")
        print(f"CUDA available: {cuda_available}")
        print(f"GPU name: {gpu_name}")
        print(f"Model device: {model_device}")
        
        if len(tensor_list) > 0:
             print(f"Inference device: {tensor_list[0].device}")
        print(f"----------------------------------")
        _LOGGED_MODELS.add(model_id)
