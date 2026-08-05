import os
import glob
import json
import time
import uuid
import platform
import sys
from datetime import datetime, timezone
from utils.data_loader import OlistDataLoader
from agents.coordinator import Coordinator

def run_batch_pipeline():
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8', errors='replace') # type: ignore
        except Exception:
            pass

    start_time = time.time()
    run_id = f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    
    print(f"=== Starting Multi-Agent A2A Batch Pipeline (Run ID: {run_id}) ===")
    
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    input_dir = os.path.join(os.path.dirname(__file__), "input")
    output_dir = os.path.join(os.path.dirname(__file__), "output")
    logging_dir = os.path.join(os.path.dirname(__file__), "logging")

    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(logging_dir, exist_ok=True)

    data_loader = OlistDataLoader(data_dir=data_dir)
    coordinator = Coordinator(data_loader=data_loader)

    input_files = sorted(glob.glob(os.path.join(input_dir, "EC_*.json")))
    if not input_files:
        print(f"[WARNING] No input files found in {input_dir}.")
        return

    total_cases = len(input_files)
    success_count = 0
    failed_count = 0
    all_trace_logs = []

    print(f"[INFO] Discovered {total_cases} case files in {input_dir}. Executing pipeline...")

    for file_path in input_files:
        file_name = os.path.basename(file_path)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                case_data = json.load(f)

            result = coordinator.process_case(case_data, output_dir=output_dir, run_id=run_id)
            
            if "trace_logs" in result:
                all_trace_logs.extend(result["trace_logs"])

            if result.get("status") == "success" and result.get("current_state") == "WRITTEN":
                success_count += 1
                print(f"  + [{file_name}] => SUCCESS (State: WRITTEN, Verdict: PASS)")
            else:
                failed_count += 1
                err_code = result.get("error", {}).get("code", "UNKNOWN_ERROR")
                print(f"  - [{file_name}] => FAILED (State: {result.get('current_state')}, Error: {err_code})")

        except Exception as e:
            failed_count += 1
            print(f"  ! [{file_name}] => SYSTEM EXCEPTION ({str(e)})")
            all_trace_logs.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "run_id": run_id,
                "correlation_id": "none",
                "case_id": file_name.split(".")[0],
                "state_from": "PROCESSING",
                "state_to": "FAILED",
                "event_type": "SYSTEM_EXCEPTION",
                "details": {"exception": str(e)}
            })

    # 3. Write logging/trace.jsonl in strict JSON Lines format
    trace_path = os.path.join(logging_dir, "trace.jsonl")
    with open(trace_path, "w", encoding="utf-8") as f:
        for log in all_trace_logs:
            f.write(json.dumps(log, ensure_ascii=False) + "\n")

    # 4. Write logging/metadata.json with model and runtime reporting
    duration = round(time.time() - start_time, 3)
    metadata = {
        "student_info": {
            "full_name": "Đàm Minh Tuấn",
            "student_id": "2A202601169",
            "role": "Full A2A System Architect & Lead Engineer"
        },
        "execution_metadata": {
            "run_id": run_id,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "python_version": sys.version,
            "platform": platform.platform()
        },
        "model_configuration": {
            "model_name": "gemini-flash-lite-latest",
            "parameter_count": "<= 10B (Flash-Lite Lightweight Agent Model)",
            "precision": "FP16/BF16",
            "temperature": 0.0,
            "determinism": "100% Deterministic Financial & Policy Rule Execution"
        },
        "models": [
            {"agent": "order_seller", "model": "gemini-flash-lite-latest", "parameter_size": "<= 10B (Flash-Lite Lightweight Agent Model)"},
            {"agent": "payment", "model": "gemini-flash-lite-latest", "parameter_size": "<= 10B (Flash-Lite Lightweight Agent Model)"},
            {"agent": "delivery", "model": "gemini-flash-lite-latest", "parameter_size": "<= 10B (Flash-Lite Lightweight Agent Model)"},
            {"agent": "policy", "model": "gemini-flash-lite-latest", "parameter_size": "<= 10B (Flash-Lite Lightweight Agent Model)"},
            {"agent": "verifier", "model": "gemini-flash-lite-latest", "parameter_size": "<= 10B (Flash-Lite Lightweight Agent Model)"},
            {"agent": "coordinator", "model": "gemini-flash-lite-latest", "parameter_size": "<= 10B (Flash-Lite Lightweight Agent Model)"}
        ],
        "runtime_statistics": {
            "total_cases_processed": total_cases,
            "successful_cases_written": success_count,
            "failed_or_rejected_cases": failed_count,
            "total_trace_events_recorded": len(all_trace_logs),
            "execution_duration_seconds": duration,
            "average_time_per_case_ms": round((duration / max(total_cases, 1)) * 1000, 2)
        }
    }

    metadata_path = os.path.join(logging_dir, "metadata.json")
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    print("\n=== Batch Pipeline Execution Summary ===")
    print(f" - Total Cases Processed: {total_cases}")
    print(f" - Successfully Verified & Written: {success_count}/{total_cases}")
    print(f" - Failed or Rejected Cases: {failed_count}")
    print(f" - Total Duration: {duration}s ({round((duration / max(total_cases, 1)) * 1000, 2)} ms/case)")
    print(f" - System Audit Trace Log: {trace_path}")
    print(f" - Execution Metadata Report: {metadata_path}")
    print("=========================================\n")

if __name__ == "__main__":
    run_batch_pipeline()
