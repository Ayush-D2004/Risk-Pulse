# RiskPulse Quickstart Guide

This document provides a step-by-step guide to setting up and running the RiskPulse platform locally. The system consists of a Python-based backend (FastAPI + AI Pipeline) and a React-based frontend (Vite + TypeScript).

---

## 1. Environment Setup

First, clone the repository and navigate to the root directory:
```bash
git clone https://github.com/Ayush-D2004/IIITN-AyushDhoble-Hackathon.git
cd IIITN-AyushDhoble-Hackathon
```

Create and activate a virtual environment to isolate the Python dependencies:

**On Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**On macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install the required Python dependencies:
```bash
pip install -r requirements.txt
```

---

## 2. Download Historical Datasets & Artifacts

Before starting the applications or executing offline pipelines, fetch the dataset package:

```bash
python download_data.py
```

- **What this does:** Automatically downloads the historical package (~1.5 GB) from [Google Drive](https://drive.google.com/file/d/1jm-49S-1m6m1u74ll8p_mOl7ooHAtSiP/view?usp=sharing), displays a progress bar via `gdown`, and reconstructs the required directory structure:
  - `data/processed/full_dataset-release.csv`
  - `data/processed/reduced_dataset-release.csv`
  - `data/pipeline_output/` (including `canonical_events.csv` and intermediate model checkpoints)
- 📖 **More information:** For full schema documentation, SQLite database descriptions, and manual setup fallbacks, refer to [data/README.md](data/README.md).

---

## 3. Running the Full Stack Application

To run the application, open **two separate terminal windows**.

### Terminal 1: Start the Backend Server
Ensure your virtual environment is activated, then start the FastAPI server:

**On Windows:**
```powershell
.\.venv\Scripts\uvicorn.exe src.dashboard.api:app --host 0.0.0.0 --port 8000 --reload
```

**On macOS / Linux:**
```bash
uvicorn src.dashboard.api:app --host 0.0.0.0 --port 8000 --reload
```
*The backend API will be available at `http://localhost:8000` (API docs at `http://localhost:8000/docs`).*

### Terminal 2: Start the Frontend Application
Open a new terminal window, navigate to the `frontend` directory, install packages, and start the development server:

```bash
cd frontend
npm install
npm run dev
```
*The React Command Center dashboard will be available at `http://localhost:5173`.*

---

## 4. Running the Offline Data Pipeline (Optional)

If you want to manually run the NLP Risk Engine across the historical 862k tweet dataset from the command line:

**On Windows:**
```powershell
.\.venv\Scripts\python.exe src/pipeline/run_pipeline.py --input data/processed/full_dataset-release.csv --output-dir data/pipeline_output
```

**On macOS / Linux:**
```bash
python src/pipeline/run_pipeline.py --input data/processed/full_dataset-release.csv --output-dir data/pipeline_output
```

*Note: The pipeline includes FinBERT sentiment inference, DeBERTa-v3 zero-shot classification, FAISS clustering, and Yahoo Finance market alignment. It supports automatic batching and checkpoint resumption.*
