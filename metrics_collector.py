import argparse
from pathlib import Path
from typing import Dict, List

import pandas as pd

from env_config import WORKER_NODES
from schema import BenchmarkMetrics, WorkerNode

# Spesifikasi VM dan tarif diambil dari env_config.py (Peran 1) agar satu sumber.
WORKERS = {
    w["vm_id"]: {
        "capacity_multiplier": w["capacity_multiplier"],
        "total_cost_per_sec": w["total_cost_per_sec"],
    }
    for w in WORKER_NODES
}
ALGOS = ["LPT", "RR"]


def latest(results_dir: Path, pattern: str) -> Path:
    files = sorted(results_dir.glob(pattern), key=lambda p: p.stat().st_mtime)
    if not files:
        raise FileNotFoundError(f"tidak ada file {pattern} di {results_dir}")
    return files[-1]


def load_logs(results_dir: Path) -> pd.DataFrame:
    frames = []
    for a in ALGOS:
        df = pd.read_csv(latest(results_dir, f"execution_log_{a.lower()}_*.csv"))
        df["algorithm"] = a
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def load_sched(results_dir: Path) -> Dict[str, float]:
    df = pd.read_csv(latest(results_dir, "benchmark_summary_*.csv"))
    return dict(zip(df["algorithm"].str.upper(), df["scheduling_duration_ms"]))


def metrics_from_ready_times(algo: str, rt: Dict[str, float], n_tasks: int, t_sched_ms: float) -> dict:
    vals = [rt.get(vm, 0.0) for vm in WORKERS]
    cmax = max(vals)
    avg = sum(vals) / len(vals)
    di = (cmax - min(vals)) / avg if avg > 0 else 0.0
    util = sum(vals) / (len(vals) * cmax) * 100 if cmax > 0 else 0.0
    tp = n_tasks / (cmax / 1000.0) if cmax > 0 else 0.0
    cost = sum(rt.get(vm, 0.0) / 1000.0 * c["total_cost_per_sec"] for vm, c in WORKERS.items())

    m = BenchmarkMetrics(
        algorithm_name=algo,
        makespan_ms=cmax,
        degree_of_imbalance=di,
        avg_cpu_utilization_pct=util,
        # RAM belum diukur di eksperimen ini (tidak ada data memori dari worker)
        avg_ram_utilization_pct=0.0,
        throughput_tasks_per_sec=tp,
        total_cost=cost,
        scheduling_duration_ms=t_sched_ms,
    )
    return m.model_dump()


def calculate_metrics(algorithm_name: str, workers: List[WorkerNode], total_tasks: int,
                      scheduling_duration_ms: float) -> BenchmarkMetrics:
    vals = [w.ready_time_ms for w in workers]
    cmax = max(vals)
    avg = sum(vals) / len(vals)
    return BenchmarkMetrics(
        algorithm_name=algorithm_name,
        makespan_ms=cmax,
        degree_of_imbalance=(cmax - min(vals)) / avg if avg > 0 else 0.0,
        avg_cpu_utilization_pct=sum(vals) / (len(vals) * cmax) * 100 if cmax > 0 else 0.0,
        avg_ram_utilization_pct=0.0,
        throughput_tasks_per_sec=total_tasks / (cmax / 1000.0) if cmax > 0 else 0.0,
        total_cost=sum(w.ready_time_ms / 1000.0 * w.total_cost_per_sec for w in workers),
        scheduling_duration_ms=scheduling_duration_ms,
    )


def collect_all(results_dir: Path) -> pd.DataFrame:
    log = load_logs(results_dir)
    sched = load_sched(results_dir)

    rows = []
    for algo, df in log.groupby("algorithm"):
        rt = df.groupby("assigned_vm_id")["estimated_finish_ms"].max().to_dict()
        row = metrics_from_ready_times(algo, rt, len(df), float(sched.get(algo, 0.0)))
        ok = df[df["status"] == "SUCCESS"]
        row["tasks_total"] = len(df)
        row["tasks_failed"] = len(df) - len(ok)
        row["tasks_corrupt"] = int((df["validation_status"] != "VALID").sum()) if "validation_status" in df else 0
        row["makespan_actual_ms"] = float(ok.groupby("assigned_vm_id")["actual_duration_ms"].sum().max()) if len(ok) else 0.0
        rows.append(row)

    out = pd.DataFrame(rows).set_index("algorithm_name").loc[ALGOS].reset_index()
    out.to_csv(results_dir / "metrics_summary.csv", index=False)
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--results", default="results")
    a = p.parse_args()
    print(collect_all(Path(a.results)).round(8).to_string(index=False))