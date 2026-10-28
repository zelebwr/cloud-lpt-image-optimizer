import csv
import random
from datetime import datetime
from pathlib import Path

from env_config import WORKER_NODES

OUT = Path("results/mock")
CM = {w["vm_id"]: w["capacity_multiplier"] for w in WORKER_NODES}
LOG_FIELDS = ["task_id", "assigned_vm_id", "input_file", "output_file", "estimated_ms",
              "actual_ms", "output_valid", "status", "error"]
SUM_FIELDS = ["algorithm", "total_tasks", "success_count", "failed_count",
              "wall_clock_makespan_ms", "scheduling_duration_ms"]


def make_tasks(n):
    tasks = []
    for i in range(n):
        w = random.randint(640, 1920)
        h = max(480, min(1080, int(w * random.choice([3 / 4, 9 / 16]))))
        tasks.append((f"TASK-{i + 1:03d}", w * h / 10000))
    return tasks


def schedule(algo, tasks):
    ids = list(CM)
    rt = {v: 0.0 for v in ids}
    order = sorted(tasks, key=lambda t: -t[1]) if algo == "lpt" else tasks
    out = []
    for i, (tid, et) in enumerate(order):
        vm = min(ids, key=lambda j: rt[j] + et / CM[j]) if algo == "lpt" else ids[i % len(ids)]
        rt[vm] += et / CM[vm]
        out.append((tid, et, vm))
    return out


def main(n=50):
    random.seed(1)
    tasks = make_tasks(n)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    OUT.mkdir(parents=True, exist_ok=True)
    summary = []

    for algo, t_sched in [("lpt", 1.8), ("rr", 0.4)]:
        rows, busy = [], {v: 0.0 for v in CM}
        for tid, et, vm in schedule(algo, tasks):
            actual = et / CM[vm] * random.uniform(0.9, 1.1)
            busy[vm] += actual
            rows.append({
                "task_id": tid, "assigned_vm_id": vm,
                "input_file": f"data/raw_images/{tid}.jpg", "output_file": f"data/processed_images/{tid}_processed.jpg",
                "estimated_ms": et, "actual_ms": actual,
                "output_valid": True, "status": "success", "error": "",
            })
        with open(OUT / f"execution_log_{algo}_{ts}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=LOG_FIELDS)
            w.writeheader()
            w.writerows(rows)
        summary.append({"algorithm": algo, "total_tasks": n, "success_count": n, "failed_count": 0,
                        "wall_clock_makespan_ms": round(max(busy.values()), 2),
                        "scheduling_duration_ms": t_sched})

    with open(OUT / f"benchmark_summary_{ts}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SUM_FIELDS)
        w.writeheader()
        w.writerows(summary)
    print(f"log mock tersimpan di {OUT}")


if __name__ == "__main__":
    main()