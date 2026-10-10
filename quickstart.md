# RiskPulse Quickstart Guide

This document provides a step-by-step guide to setting up and running the RiskPulse platform locally. The system consists of a Python-based backend (FastAPI + AI Pipeline) and a React-based frontend (Vite).


## 1. Environment Setup

First, clone the repository and navigate to the root directory:
```bash
git clone <your-repo-url>
cd RiskPulse
```

Create and activate a virtual environment to isolate the Python dependencies:

**On Windows:**
```bash
python -m venv .venv
.\.venv\Scripts\activate
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

## 2. Running the Application

To run the full stack, you will need to open **two separate terminal windows**.

### Terminal 1: Start the Backend Server
Ensure your virtual environment is activated, then start the FastAPI server:
```bash
# Windows
.\.venv\Scripts\uvicorn.exe src.dashboard.api:app --host 0.0.0.0 --port 8000 --reload

# macOS / Linux
uvicorn src.dashboard.api:app --host 0.0.0.0 --port 8000 --reload
```
*The backend API will now be available at `http://localhost:8000`.*

### Terminal 2: Start the Frontend Application
Open a new terminal window, navigate to the frontend directory, install dependencies, and start the development server:
```bash
cd frontend
npm install
npm run dev
```
*The frontend dashboard will be available at the local URL provided in the terminal (usually `http://localhost:5173`).*

---

## 3. Running the Data Pipeline (Optional)

If you need to process a new batch of raw data through the Risk Engine pipeline, you can run the pipeline script manually from the root directory. Make sure your virtual environment is activated:

```bash
# Windows
.\.venv\Scripts\python.exe src/pipeline/run_pipeline.py --input <path_to_input.csv> --output-dir <path_to_output_dir>

# macOS / Linux
python src/pipeline/run_pipeline.py --input <path_to_input.csv> --output-dir <path_to_output_dir>
```
*Note: Depending on your hardware and dataset size, running the full NLP pipeline may take some time. The script supports chunking and checkpoint resumption.*
