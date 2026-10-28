import argparse
from pathlib import Path

import pandas as pd

COLS = {
    "algorithm_name": "Algoritma",
    "makespan_ms": "Makespan Est (ms)",
    "degree_of_imbalance": "DI",
    "avg_cpu_utilization_pct": "Util (%)",
    "throughput_tasks_per_sec": "Throughput (task/s)",
    "total_cost": "Total Cost (USD)",
    "scheduling_duration_ms": "T_sched (ms)",
    "makespan_actual_ms": "Makespan Aktual (ms)",
    "di_actual": "DI Aktual",
    "wall_clock_ms": "Wall-clock (ms)",
    "tasks_failed": "Gagal",
}


def gain(base, new):
    return (base - new) / base * 100 if base else 0.0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--results", default="results")
    a = p.parse_args()
    results_dir = Path(a.results)

    df = pd.read_csv(results_dir / "metrics_summary.csv")
    table = df[list(COLS)].rename(columns=COLS).round(6)
    lines = ["Ringkasan Benchmark LPT vs Round Robin (Azure)", "", table.to_string(index=False), ""]

    lpt = df[df["algorithm_name"] == "LPT"].iloc[0]
    rr = df[df["algorithm_name"] == "RR"].iloc[0]
    lines.append(f"Makespan estimasi LPT lebih rendah {gain(rr['makespan_ms'], lpt['makespan_ms']):.2f}% dari RR")
    lines.append(f"DI estimasi LPT lebih rendah {gain(rr['degree_of_imbalance'], lpt['degree_of_imbalance']):.2f}% dari RR")
    lines.append(f"Makespan aktual LPT lebih rendah {gain(rr['makespan_actual_ms'], lpt['makespan_actual_ms']):.2f}% dari RR")
    lines.append(f"Wall-clock LPT lebih rendah {gain(rr['wall_clock_ms'], lpt['wall_clock_ms']):.2f}% dari RR")
    lines.append(f"Throughput LPT {lpt['throughput_tasks_per_sec']:.2f} vs RR {rr['throughput_tasks_per_sec']:.2f} task/s")
    lines.append(f"T_sched LPT {lpt['scheduling_duration_ms']:.3f} ms vs RR {rr['scheduling_duration_ms']:.3f} ms")

    report = "\n".join(lines)
    print(report)
    (results_dir / "laporan_ringkasan.txt").write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()