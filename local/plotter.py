import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from metrics_collector import ALGOS, WORKERS, load_logs

COLORS = {"LPT": "#2b6cb0", "RR": "#dd6b20"}


def bar(df, col, ylabel, title, path):
    fig, ax = plt.subplots(figsize=(5, 4))
    bars = ax.bar(df["algorithm_name"], df[col], color=[COLORS[a] for a in df["algorithm_name"]])
    ax.bar_label(bars, fmt="%.2f")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def vm_load(results_dir, out_dir):
    log = load_logs(results_dir)
    rt = log.groupby(["algorithm", "assigned_vm_id"])["estimated_finish_ms"].max().unstack(0)
    rt = rt.reindex(list(WORKERS))[ALGOS].fillna(0.0)
    ax = rt.plot(kind="bar", figsize=(7, 4), color=[COLORS[a] for a in rt.columns])
    ax.set_ylabel("Waktu siap (ms)")
    ax.set_xlabel("")
    ax.set_title("Beban per VM")
    ax.spines[["top", "right"]].set_visible(False)
    plt.xticks(rotation=0)
    plt.tight_layout()
    plt.savefig(out_dir / "vm_load.png", dpi=150)
    plt.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--results", default="results")
    a = p.parse_args()
    results_dir = Path(a.results)
    out_dir = results_dir / "grafik"
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(results_dir / "metrics_summary.csv")
    bar(df, "makespan_ms", "Makespan (ms)", "Perbandingan Makespan", out_dir / "makespan_comparison.png")
    bar(df, "degree_of_imbalance", "Degree of Imbalance", "Perbandingan Degree of Imbalance", out_dir / "imbalance_chart.png")
    vm_load(results_dir, out_dir)
    print(f"grafik tersimpan di {out_dir}")


if __name__ == "__main__":
    main()