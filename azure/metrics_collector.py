import argparse
from pathlib import Path
from typing import Dict, List

import pandas as pd

from env_config import WORKER_NODES
from schema import BenchmarkMetrics, WorkerNode

CM = {w["vm_id"]: w["capacity_multiplier"] for w in WORKER_NODES}
COST = {w["vm_id"]: w["total_cost_per_sec"] for w in WORKER_NODES}
ALGOS = ["lpt", "rr"]
LABEL = {"lpt": "LPT", "rr": "RR"}


def latest(results_dir: Path, pattern: str) -> Path:
    files = sorted(results_dir.glob(pattern), key=lambda p: p.stat().st_mtime)
    if not files:
        raise FileNotFoundError(f"tidak ada file {pattern} di {results_dir}")
    return files[-1]


def load_logs(results_dir: Path) -> pd.DataFrame:
    frames = []
    for a in ALGOS:
        df = pd.read_csv(latest(results_dir, f"execution_log_{a}_*.csv"))
        df["algorithm"] = LABEL[a]
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def load_summary(results_dir: Path) -> pd.DataFrame:
    df = pd.read_csv(latest(results_dir, "benchmark_summary_*.csv"))
    df["algorithm"] = df["algorithm"].str.lower().map(LABEL)
    return df.set_index("algorithm")


def ready_times(df: pd.DataFrame) -> Dict[str, float]:
    return {vm: float((g["estimated_ms"] / CM[vm]).sum()) for vm, g in df.groupby("assigned_vm_id")}


def imbalance(vals: List[float]) -> float:
    avg = sum(vals) / len(vals)
    return (max(vals) - min(vals)) / avg if avg > 0 else 0.0


def metrics_from_ready_times(algo: str, rt: Dict[str, float], n_tasks: int, t_sched_ms: float) -> dict:
    vals = [rt.get(vm, 0.0) for vm in CM]
    cmax = max(vals)
    util = sum(vals) / (len(vals) * cmax) * 100 if cmax > 0 else 0.0
    cost = sum(rt.get(vm, 0.0) / 1000.0 * COST[vm] for vm in CM)

    m = BenchmarkMetrics(
        algorithm_name=algo,
        makespan_ms=cmax,
        degree_of_imbalance=imbalance(vals),
        avg_cpu_utilization_pct=util,
        avg_ram_utilization_pct=0.0,
        throughput_tasks_per_sec=n_tasks / (cmax / 1000.0) if cmax > 0 else 0.0,
        total_cost=cost,
        scheduling_duration_ms=t_sched_ms,
    )
    return m.model_dump()


def calculate_metrics(algorithm_name: str, workers: List[WorkerNode], total_tasks: int,
                      scheduling_duration_ms: float) -> BenchmarkMetrics:
    rt = {w.vm_id: w.ready_time_ms for w in workers}
    row = metrics_from_ready_times(algorithm_name, rt, total_tasks, scheduling_duration_ms)
    return BenchmarkMetrics(**row)


def collect_all(results_dir: Path) -> pd.DataFrame:
    log = load_logs(results_dir)
    summ = load_summary(results_dir)

    rows = []
    for algo, df in log.groupby("algorithm"):
        row = metrics_from_ready_times(algo, ready_times(df), len(df), float(summ.loc[algo, "scheduling_duration_ms"]))
        ok = df[df["status"] == "success"]
        busy = [float(ok.loc[ok["assigned_vm_id"] == vm, "actual_ms"].sum()) for vm in CM]
        row["tasks_total"] = len(df)
        row["tasks_failed"] = len(df) - len(ok)
        row["makespan_actual_ms"] = max(busy)
        row["di_actual"] = imbalance(busy)
        row["wall_clock_ms"] = float(summ.loc[algo, "wall_clock_makespan_ms"])
        rows.append(row)

    out = pd.DataFrame(rows).set_index("algorithm_name").loc[[LABEL[a] for a in ALGOS]].reset_index()
    out.to_csv(results_dir / "metrics_summary.csv", index=False)
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--results", default="results")
    a = p.parse_args()
    print(collect_all(Path(a.results)).round(6).to_string(index=False))