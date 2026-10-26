import csv
import random
from datetime import datetime
from pathlib import Path

from lpt_logic import run_lpt
from metrics_collector import WORKERS
from rr_logic import run_round_robin
from schema import ImageTask, WorkerNode

OUT = Path("results/mock")
LOG_HEADER = ["algorithm", "task_id", "assigned_vm_id", "estimated_start_ms", "estimated_finish_ms",
              "actual_duration_ms", "output_file_path", "validation_status", "status", "error_message"]
SUM_HEADER = ["algorithm", "makespan_ms", "degree_of_imbalance", "avg_utilization_pct",
              "throughput_tasks_per_sec", "tasks_total", "tasks_succeeded", "tasks_failed",
              "scheduling_duration_ms"]


def make_tasks(n):
    tasks = []
    for i in range(n):
        w = random.randint(640, 1920)
        h = max(480, min(1080, int(w * random.choice([3 / 4, 9 / 16]))))
        tasks.append(ImageTask(task_id=f"task_{i:03d}", file_path=f"raw_images/image_{i:03d}.jpg",
                               width_px=w, height_px=h, file_size_bytes=w * h // 4,
                               estimated_processing_time_ms=w * h / 10000))
    return tasks


def make_workers():
    return [WorkerNode(vm_id=vm, host_id="host", capacity_multiplier=c["capacity_multiplier"],
                       total_cost_per_sec=c["total_cost_per_sec"]) for vm, c in WORKERS.items()]


def main(n=50):
    random.seed(1)
    tasks = make_tasks(n)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    OUT.mkdir(parents=True, exist_ok=True)
    summary = []

    for algo, fn, t_sched in [("lpt", run_lpt, 1.8), ("rr", run_round_robin, 0.4)]:
        assignments, _ = fn(tasks, make_workers())
        rows = [{
            "algorithm": algo.upper(), "task_id": a.task_id, "assigned_vm_id": a.assigned_vm_id,
            "estimated_start_ms": a.estimated_start_time_ms, "estimated_finish_ms": a.estimated_finish_time_ms,
            "actual_duration_ms": (a.estimated_finish_time_ms - a.estimated_start_time_ms) * random.uniform(0.9, 1.1),
            "output_file_path": f"/data/out/{a.task_id}.jpg", "validation_status": "VALID",
            "status": "SUCCESS", "error_message": "",
        } for a in assignments]
        with open(OUT / f"execution_log_{algo}_{ts}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=LOG_HEADER)
            w.writeheader()
            w.writerows(rows)
        summary.append({"algorithm": algo.upper(), "makespan_ms": 0, "degree_of_imbalance": 0,
                        "avg_utilization_pct": 0, "throughput_tasks_per_sec": 0, "tasks_total": n,
                        "tasks_succeeded": n, "tasks_failed": 0, "scheduling_duration_ms": t_sched})

    with open(OUT / f"benchmark_summary_{ts}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SUM_HEADER)
        w.writeheader()
        w.writerows(summary)
    print(f"log mock tersimpan di {OUT}")


if __name__ == "__main__":
    main()