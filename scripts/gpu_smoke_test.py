import sys
import torch
import time
from pathlib import Path
from src.nlp.finbert_inference import infer_csv

def run_smoke_test():
    print("==================================================")
    print("GPU SMOKE TEST")
    print("==================================================")
    
    if not torch.cuda.is_available():
        print("CUDA smoke test NOT EXECUTED because CUDA was unavailable in this environment.")
        return

    input_csv = Path("data/processed/reduced_dataset-release.csv")
    output_csv = Path("data/pipeline_output_smoke/finbert_smoke_output.csv")
    checkpoint_dir = Path("data/pipeline_output_smoke/checkpoints")
    
    # Clean up any previous smoke output to test a fresh run
    if output_csv.exists():
        output_csv.unlink()
        
    start_time = time.time()
    
    try:
        infer_csv(
            input_csv=input_csv,
            output_csv=output_csv,
            batch_size=16,
            chunk_size=50,
            max_rows=100,
            device="cuda",
            overwrite=True,
            checkpoint_dir=checkpoint_dir,
        )
    except Exception as e:
        print(f"Smoke test failed during execution: {e}")
        sys.exit(1)
        
    duration = time.time() - start_time
    print("\n--- SMOKE TEST RESULTS ---")
    print("CUDA detected: YES")
    print("Inference completed on CUDA: YES (no exceptions raised)")
    
    if output_csv.exists():
        import pandas as pd
        df = pd.read_csv(output_csv)
        print(f"Output rows: {len(df)}")
        print(f"Output schema: {list(df.columns)}")
        print(f"Throughput: {len(df) / max(duration, 0.001):.1f} rows/sec")
    else:
        print("Output file not created!")
        sys.exit(1)
        
if __name__ == "__main__":
    run_smoke_test()
