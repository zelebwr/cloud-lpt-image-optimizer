import argparse
from pathlib import Path

import pandas as pd

from metrics_collector import WORKERS, load_logs

p = argparse.ArgumentParser()
p.add_argument("--results", default="results")
results_dir = Path(p.parse_args().results)

log = load_logs(results_dir)
res = pd.read_csv(results_dir / "metrics_summary.csv").set_index("algorithm_name")
cm = {v: c["capacity_multiplier"] for v, c in WORKERS.items()}
errors = []


def check(cond, msg):
    print(("OK    " if cond else "GAGAL ") + msg)
    if not cond:
        errors.append(msg)


check(set(log["assigned_vm_id"]) <= set(WORKERS), "semua vm_id di log ada di daftar worker")
counts = log.groupby("algorithm").size()
check(counts.nunique() == 1, f"jumlah task sama di kedua algoritma ({counts.to_dict()})")
check(log["task_id"].groupby(log["algorithm"]).nunique().eq(counts).all(), "tidak ada task_id ganda")

for algo, df in log.groupby("algorithm"):
    rt = pd.Series({v: 0.0 for v in cm})
    for vm, g in df.groupby("assigned_vm_id"):
        rt[vm] = (g["estimated_finish_ms"] - g["estimated_start_ms"]).sum()

    cmax = rt.max()
    di = (rt.max() - rt.min()) / rt.mean()
    util = rt.sum() / (len(cm) * cmax) * 100
    tp = len(df) / (cmax / 1000)
    r = res.loc[algo]

    check(abs(r["makespan_ms"] - cmax) < 1e-3, f"{algo}: makespan cocok ({cmax:.2f})")
    check(abs(r["degree_of_imbalance"] - di) < 1e-3, f"{algo}: DI cocok ({di:.4f})")
    check(abs(r["avg_cpu_utilization_pct"] - util) < 1e-3, f"{algo}: utilization cocok ({util:.2f}%)")
    check(abs(r["throughput_tasks_per_sec"] - tp) < 1e-3, f"{algo}: throughput cocok ({tp:.2f})")
    check(0 < util <= 100, f"{algo}: utilization di rentang 0-100")
    check(di >= 0, f"{algo}: DI tidak negatif")
    check((df["status"] == "SUCCESS").all(), f"{algo}: semua task SUCCESS")
    check((df["validation_status"] == "VALID").all(), f"{algo}: semua gambar output VALID")

check(res.loc["LPT", "makespan_ms"] <= res.loc["RR", "makespan_ms"], "makespan LPT <= RR")
check(res.loc["LPT", "degree_of_imbalance"] <= res.loc["RR", "degree_of_imbalance"], "DI LPT <= RR")

for f in ["grafik/makespan_comparison.png", "grafik/imbalance_chart.png", "grafik/vm_load.png", "laporan_ringkasan.txt"]:
    fp = results_dir / f
    check(fp.exists() and fp.stat().st_size > 0, f"file {f} terbentuk")

print()
print("SEMUA LOLOS" if not errors else f"{len(errors)} pengecekan gagal")