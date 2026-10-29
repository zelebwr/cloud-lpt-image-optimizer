# benchmark_runner.py
# Peran 4: Workload Generator & QA Test Orchestrator
# Fungsi: mengorkestrasi benchmark LPT vs Round Robin lewat REST API master + worker.

# ── Impor stdlib ──────────────────────────────────────────────────────────────
import argparse
import csv
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

# ── Impor library eksternal ──────────────────────────────────────────────────
import requests
from PIL import Image

# ── Impor model dari schema.py (JANGAN definisikan ulang) ─────────────────────
from schema import ImageTask, TaskAssignment

# ──────────────────────────────────────────────────────────────────────────────
# KONSTANTA & KONFIGURASI DEFAULT
# ──────────────────────────────────────────────────────────────────────────────

# Mapping vm_id -> URL worker untuk mode Docker lokal.
# Override lewat --workers atau env var WORKER_URLS (format sama: "vm-worker-1=http://IP:PORT,...").
DEFAULT_WORKER_URLS: dict[str, str] = {
    "vm-worker-1": "http://localhost:8001",
    "vm-worker-2": "http://localhost:8002",
    "vm-worker-3": "http://localhost:8003",
    "vm-worker-4": "http://localhost:8004",
}

# URL worker Azure (Public IP) — dipakai saat --mode azure atau --workers tidak diberikan
# dan env var AZURE_MODE=1 diset.
AZURE_MASTER_URL: str = "http://20.244.12.15:8000"
AZURE_WORKER_URLS: dict[str, str] = {
    "vm-worker-1": "http://98.70.42.52:8000",    # Public IP: 98.70.42.52  | Private: 10.0.1.4
    "vm-worker-2": "http://135.235.195.95:8000",  # Public IP: 135.235.195.95 | Private: 10.0.1.5
    "vm-worker-3": "http://70.153.24.61:8000",    # Public IP: 70.153.24.61 | Private: 10.0.2.4
    "vm-worker-4": "http://70.153.24.25:8000",    # Public IP: 70.153.24.25 | Private: 10.0.2.5
}

# Kualitas JPEG untuk output hasil pemrosesan worker
DEFAULT_QUALITY = 85

# Timeout request HTTP (detik)
REQUEST_TIMEOUT = 120

# Toleransi dimensi output (±10% dari target)
DIMENSION_TOLERANCE = 0.10

# True = kirim gambar lewat multipart ke /execute_task_upload (diatur di main())
USE_UPLOAD = False


# ──────────────────────────────────────────────────────────────────────────────
# FUNGSI HELPER
# ──────────────────────────────────────────────────────────────────────────────

def parse_args():
    """Parsing argumen CLI."""
    parser = argparse.ArgumentParser(
        description="Benchmark runner LPT vs Round Robin via REST API."
    )
    parser.add_argument(
        "--master", type=str, default=None,
        help=(
            "URL Master Node dispatcher. "
            "Default: http://localhost:8000 (mode local) atau http://20.244.12.15:8000 (mode azure)."
        )
    )
    parser.add_argument(
        "--mode", type=str, default="local", choices=["local", "azure"],
        help=(
            "Mode deployment: 'local' pakai Docker lokal (port 8001-8004), "
            "'azure' pakai Public IP VM Azure yang sudah dikonfigurasi. (default: local)"
        )
    )
    parser.add_argument(
        "--dataset", type=str, default="data",
        help="Direktori dataset berisi metadata.json (default: data)"
    )
    parser.add_argument(
        "--output", type=str, default="data/processed_images",
        help="Direktori output gambar hasil proses (default: data/processed_images)"
    )
    parser.add_argument(
        "--results", type=str, default="results",
        help="Direktori output log dan metrik CSV (default: results)"
    )
    parser.add_argument(
        "--algorithms", nargs="+", default=["lpt", "rr"],
        choices=["lpt", "rr"],
        help="Algoritma yang diuji: lpt, rr, atau keduanya (default: lpt rr)"
    )
    parser.add_argument(
        "--workers", type=str, default=None,
        help=(
            "Override URL worker secara manual, format: "
            "'vm-worker-1=http://IP:PORT,vm-worker-2=http://IP:PORT,...' "
            "Jika diisi, mengabaikan --mode."
        )
    )
    parser.add_argument(
        "--transport", type=str, default="auto", choices=["auto", "path", "upload"],
        help=(
            "Cara mengirim gambar ke worker: 'upload' (multipart ke /execute_task_upload, "
            "untuk VM terpisah seperti Azure), 'path' (kirim path file ke /execute_task, "
            "untuk worker yang berbagi folder dengan runner). "
            "'auto' = upload jika --mode azure, selain itu path. (default: auto)"
        )
    )
    return parser.parse_args()


def parse_worker_urls(workers_str: str) -> dict[str, str]:
    """
    Parse string --workers menjadi dict {vm_id: url}.
    Format input: "vm-worker-1=http://1.2.3.4:8000,vm-worker-2=http://5.6.7.8:8000"
    """
    result = {}
    for pair in workers_str.split(","):
        pair = pair.strip()
        if "=" in pair:
            vm_id, url = pair.split("=", 1)
            result[vm_id.strip()] = url.strip()
    return result


def resolve_worker_urls(args) -> dict[str, str]:
    """
    Tentukan mapping vm_id -> URL worker dengan prioritas:
    1. --workers CLI  (manual override, mengabaikan --mode)
    2. Env var WORKER_URLS
    3. --mode azure   -> pakai AZURE_WORKER_URLS (Public IP Azure)
    4. --mode local   -> pakai DEFAULT_WORKER_URLS (Docker lokal, port 8001-8004)
    """
    # Cek argumen CLI --workers lebih dulu
    if args.workers:
        return parse_worker_urls(args.workers)

    # Cek env var WORKER_URLS
    env_workers = os.environ.get("WORKER_URLS", "")
    if env_workers:
        return parse_worker_urls(env_workers)

    # Pilih berdasarkan --mode
    if args.mode == "azure":
        return AZURE_WORKER_URLS.copy()

    # Fallback: mode local / Docker
    return DEFAULT_WORKER_URLS.copy()


def resolve_master_url(args) -> str:
    """
    Tentukan URL master dispatcher:
    - Jika --master diisi eksplisit, pakai itu.
    - Jika --mode azure dan --master tidak diisi, pakai AZURE_MASTER_URL.
    - Fallback: localhost:8000.
    """
    if args.master:
        return args.master
    if args.mode == "azure":
        return AZURE_MASTER_URL
    return "http://localhost:8000"


def baca_metadata(dataset_dir: str) -> list[ImageTask]:
    """
    Baca metadata.json dari direktori dataset dan ubah menjadi list ImageTask.
    """
    json_path = os.path.join(dataset_dir, "metadata.json")
    if not os.path.exists(json_path):
        print(f"[ERROR] metadata.json tidak ditemukan di '{json_path}'")
        print("        Jalankan dataset_generator.py terlebih dahulu.")
        raise FileNotFoundError(json_path)

    with open(json_path, "r", encoding="utf-8") as f:
        raw_list = json.load(f)

    tasks = [ImageTask(**row) for row in raw_list]
    print(f"[INFO] Membaca {len(tasks)} task dari {json_path}")
    return tasks


def minta_jadwal(master_url: str, algorithm: str, tasks: list[ImageTask]) -> tuple[list[TaskAssignment], float]:
    """
    POST ke {master_url}/schedule untuk mendapatkan jadwal assignment.
    Mengembalikan (list[TaskAssignment], scheduling_duration_ms).
    """
    payload = {
        "algorithm": algorithm,
        "tasks": [t.model_dump() for t in tasks],
    }

    print(f"[INFO] POST {master_url}/schedule (algoritma={algorithm}, {len(tasks)} task)...")
    resp = requests.post(
        f"{master_url}/schedule",
        json=payload,
        timeout=REQUEST_TIMEOUT
    )
    resp.raise_for_status()
    data = resp.json()

    # Parsing response: {"assignments": [...], "scheduling_duration_ms": float}
    assignments = [TaskAssignment(**a) for a in data["assignments"]]
    sched_duration_ms = float(data.get("scheduling_duration_ms", 0.0))

    print(f"[INFO] Menerima {len(assignments)} assignment (jadwal selesai dalam {sched_duration_ms:.2f} ms)")
    return assignments, sched_duration_ms


def kelompokkan_per_vm(assignments: list[TaskAssignment]) -> dict[str, list[TaskAssignment]]:
    """
    Kelompokkan list TaskAssignment menjadi dict {vm_id: [assignment, ...]},
    diurutkan berdasarkan estimated_start_time_ms agar eksekusi berurutan per VM.
    """
    grouped: dict[str, list[TaskAssignment]] = {}
    for asgn in assignments:
        grouped.setdefault(asgn.assigned_vm_id, []).append(asgn)

    # Urutkan per VM berdasarkan estimasi waktu mulai
    for vm_id in grouped:
        grouped[vm_id].sort(key=lambda a: a.estimated_start_time_ms)

    return grouped


def validasi_output(output_path: str, expected_width: float, expected_height: float) -> tuple[bool, str]:
    """
    Validasi file output hasil worker dengan Pillow:
    - File harus ada
    - Bisa dibuka (tidak korup)
    - Dimensi aktual ±DIMENSION_TOLERANCE dari ekspektasi
    Mengembalikan (valid: bool, pesan: str).
    """
    if not os.path.exists(output_path):
        return False, f"File output tidak ditemukan: {output_path}"

    try:
        with Image.open(output_path) as img:
            img.verify()  # Verifikasi integritas file

        # Buka ulang untuk baca dimensi (verify() menutup file)
        with Image.open(output_path) as img:
            actual_w, actual_h = img.size

        # Cek toleransi dimensi ±10%
        w_ok = abs(actual_w - expected_width) <= expected_width * DIMENSION_TOLERANCE
        h_ok = abs(actual_h - expected_height) <= expected_height * DIMENSION_TOLERANCE

        if w_ok and h_ok:
            return True, f"OK ({actual_w}x{actual_h})"
        else:
            return False, (
                f"Dimensi tidak sesuai: aktual={actual_w}x{actual_h}, "
                f"ekspektasi≈{int(expected_width)}x{int(expected_height)}"
            )
    except Exception as e:
        return False, f"File tidak valid: {e}"


def eksekusi_task_di_vm(
    asgn: TaskAssignment,
    worker_url: str,
    task_map: dict[str, ImageTask],
    dataset_dir: str,
    output_dir: str,
) -> dict:
    """
    POST ke {worker_url}/execute_task untuk satu task.
    Mengembalikan dict log untuk satu baris CSV execution_log.
    """
    task = task_map[asgn.task_id]

    # Path input absolut (di mesin yang menjalankan script ini)
    input_file_abs = os.path.join(dataset_dir, task.file_path)

    # Path output untuk hasil worker (dibuat relatif terhadap output_dir)
    output_file_name = os.path.basename(task.file_path).replace(".jpg", "_processed.jpg")
    output_file_abs = os.path.join(output_dir, output_file_name)

    # Payload yang dikirim ke worker
    payload = {
        "task_id":          task.task_id,
        "input_file_path":  input_file_abs,
        "output_file_path": output_file_abs,
        "target_scale":     task.target_scale,
        "quality":          DEFAULT_QUALITY,
    }

    # Template log baris: akan diisi sesuai hasil
    log_row = {
        "task_id":        task.task_id,
        "assigned_vm_id": asgn.assigned_vm_id,
        "input_file":     input_file_abs,
        "output_file":    output_file_abs,
        "estimated_ms":   task.estimated_processing_time_ms,
        "actual_ms":      0.0,
        "output_valid":   False,
        "status":         "pending",
        "error":          "",
    }

    try:
        # ── Catat waktu sebelum request ────────────────────────────────────
        t_start = time.perf_counter()

        if USE_UPLOAD:
            # Kirim gambar lewat multipart; hasil resize kembali sebagai bytes JPEG
            with open(input_file_abs, "rb") as fh:
                resp = requests.post(
                    f"{worker_url}/execute_task_upload",
                    data={
                        "task_id": task.task_id,
                        "target_scale": task.target_scale,
                        "quality": DEFAULT_QUALITY,
                    },
                    files={"file": (os.path.basename(input_file_abs), fh, "image/jpeg")},
                    timeout=REQUEST_TIMEOUT
                )
            resp.raise_for_status()

            os.makedirs(os.path.dirname(output_file_abs) or ".", exist_ok=True)
            with open(output_file_abs, "wb") as out:
                out.write(resp.content)

            t_end = time.perf_counter()
            elapsed_ms = (t_end - t_start) * 1000
            header_ms = resp.headers.get("X-Actual-Duration-Ms")
            actual_ms = float(header_ms) if header_ms else elapsed_ms
        else:
            resp = requests.post(
                f"{worker_url}/execute_task",
                json=payload,
                timeout=REQUEST_TIMEOUT
            )
            resp.raise_for_status()

            t_end = time.perf_counter()
            elapsed_ms = (t_end - t_start) * 1000

            resp_data = resp.json()
            actual_ms = float(
                resp_data.get("actual_duration_ms")
                or resp_data.get("processing_duration_ms")
                or resp_data.get("duration_ms")
                or resp_data.get("actual_ms")
                or elapsed_ms
            )

        # ── Validasi file output ───────────────────────────────────────────
        exp_w = task.width_px * task.target_scale
        exp_h = task.height_px * task.target_scale
        valid, valid_msg = validasi_output(output_file_abs, exp_w, exp_h)

        log_row.update({
            "actual_ms":    round(actual_ms, 2),
            "output_valid": valid,
            "status":       "success" if valid else "invalid_output",
            "error":        "" if valid else valid_msg,
        })

    except Exception as e:
        # Error per task: catat dan lanjutkan — jangan crash
        log_row.update({
            "status": "failed",
            "error":  str(e),
        })

    return log_row


def proses_satu_vm(
    vm_id: str,
    assignments: list[TaskAssignment],
    worker_url: str,
    task_map: dict[str, ImageTask],
    dataset_dir: str,
    output_dir: str,
) -> list[dict]:
    """
    Proses semua task yang ditugaskan ke satu VM secara SEQUENTIAL.
    Dipanggil dari thread terpisah (satu thread per VM).
    Mengembalikan list log_row untuk semua task di VM ini.
    """
    logs = []
    print(f"  [VM {vm_id}] Memulai {len(assignments)} task (worker: {worker_url})")

    for asgn in assignments:
        log_row = eksekusi_task_di_vm(asgn, worker_url, task_map, dataset_dir, output_dir)
        logs.append(log_row)

        status_icon = "✓" if log_row["status"] == "success" else "✗"
        print(
            f"    {status_icon} {log_row['task_id']} | "
            f"actual={log_row['actual_ms']:.1f}ms | "
            f"valid={log_row['output_valid']} | "
            f"{log_row['status']}"
        )

    return logs


def jalankan_satu_algoritma(
    algorithm: str,
    master_url: str,
    worker_urls: dict[str, str],
    tasks: list[ImageTask],
    dataset_dir: str,
    output_dir: str,
    results_dir: str,
    timestamp: str,
) -> dict:
    """
    Orkestrasi penuh untuk satu algoritma (lpt atau rr):
    1. Minta jadwal dari master
    2. Jalankan task paralel antar-VM (sequential dalam satu VM)
    3. Tulis execution_log ke CSV
    Mengembalikan dict ringkasan metrik algoritma ini.
    """
    print(f"\n{'='*60}")
    print(f"  ALGORITMA: {algorithm.upper()}")
    print(f"{'='*60}")

    # ── Langkah 1: Minta jadwal dari master ───────────────────────────────
    assignments, sched_duration_ms = minta_jadwal(master_url, algorithm, tasks)

    # ── Buat dict task_id -> ImageTask untuk lookup cepat ─────────────────
    task_map = {t.task_id: t for t in tasks}

    # ── Kelompokkan assignment per VM ──────────────────────────────────────
    grouped = kelompokkan_per_vm(assignments)

    print(f"\n[INFO] Distribusi task per VM:")
    for vm_id, vm_asgns in grouped.items():
        print(f"  {vm_id}: {len(vm_asgns)} task")

    # ── Langkah 2: Jalankan per VM secara paralel (satu thread per VM) ────
    all_logs: list[dict] = []
    print(f"\n[INFO] Memulai eksekusi paralel antar-VM...")

    t_wall_start = time.perf_counter()

    with ThreadPoolExecutor(max_workers=len(grouped)) as executor:
        futures = {}
        for vm_id, vm_asgns in grouped.items():
            # Pilih URL worker untuk VM ini; fallback ke vm-worker-1 jika tidak ditemukan
            worker_url = worker_urls.get(vm_id, worker_urls.get("vm-worker-1", "http://localhost:8001"))
            fut = executor.submit(
                proses_satu_vm,
                vm_id, vm_asgns, worker_url, task_map, dataset_dir, output_dir
            )
            futures[fut] = vm_id

        for fut in as_completed(futures):
            vm_id = futures[fut]
            try:
                vm_logs = fut.result()
                all_logs.extend(vm_logs)
            except Exception as e:
                print(f"[ERROR] Thread VM {vm_id} crash: {e}")

    t_wall_end = time.perf_counter()
    wall_clock_ms = (t_wall_end - t_wall_start) * 1000

    # ── Langkah 3: Tulis execution_log CSV ────────────────────────────────
    log_filename = f"execution_log_{algorithm}_{timestamp}.csv"
    log_path = os.path.join(results_dir, log_filename)

    fieldnames = [
        "task_id", "assigned_vm_id", "input_file", "output_file",
        "estimated_ms", "actual_ms", "output_valid", "status", "error"
    ]
    with open(log_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_logs)

    print(f"\n[OK] Execution log -> {log_path}")

    # ── Hitung ringkasan ───────────────────────────────────────────────────
    success_count = sum(1 for r in all_logs if r["status"] == "success")
    failed_count  = sum(1 for r in all_logs if r["status"] != "success")

    summary = {
        "algorithm":              algorithm,
        "total_tasks":            len(all_logs),
        "success_count":          success_count,
        "failed_count":           failed_count,
        "wall_clock_makespan_ms": round(wall_clock_ms, 2),
        "scheduling_duration_ms": round(sched_duration_ms, 2),
    }

    print(
        f"\n[RINGKASAN {algorithm.upper()}] "
        f"total={summary['total_tasks']} | "
        f"sukses={success_count} | "
        f"gagal={failed_count} | "
        f"makespan={wall_clock_ms:.1f}ms | "
        f"jadwal={sched_duration_ms:.2f}ms"
    )

    return summary


def tulis_benchmark_summary(summaries: list[dict], results_dir: str, timestamp: str) -> None:
    """
    Tulis benchmark_summary_<timestamp>.csv dengan satu baris per algoritma.
    """
    summary_path = os.path.join(results_dir, f"benchmark_summary_{timestamp}.csv")
    fieldnames = [
        "algorithm", "total_tasks", "success_count", "failed_count",
        "wall_clock_makespan_ms", "scheduling_duration_ms"
    ]
    with open(summary_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(summaries)
    print(f"\n[OK] Benchmark summary -> {summary_path}")


def cetak_perbandingan(summaries: list[dict]) -> None:
    """
    Cetak tabel perbandingan LPT vs Round Robin di terminal.
    """
    print("\n" + "=" * 65)
    print("  PERBANDINGAN HASIL BENCHMARK")
    print("=" * 65)
    header = f"{'Metrik':<32}"
    for s in summaries:
        header += f"  {s['algorithm'].upper():>12}"
    print(header)
    print("-" * 65)

    # Baris yang ditampilkan
    rows = [
        ("Total Task",          "total_tasks",            lambda v: str(v)),
        ("Sukses",              "success_count",           lambda v: str(v)),
        ("Gagal",               "failed_count",            lambda v: str(v)),
        ("Wall-clock Makespan", "wall_clock_makespan_ms",  lambda v: f"{v:.1f} ms"),
        ("Scheduling Duration", "scheduling_duration_ms",  lambda v: f"{v:.2f} ms"),
    ]

    for label, key, fmt in rows:
        line = f"  {label:<30}"
        for s in summaries:
            line += f"  {fmt(s[key]):>12}"
        print(line)

    # Kesimpulan makespan (algoritma mana yang lebih cepat)
    if len(summaries) == 2:
        s0, s1 = summaries[0], summaries[1]
        if s0["wall_clock_makespan_ms"] < s1["wall_clock_makespan_ms"]:
            pemenang = s0["algorithm"].upper()
        elif s1["wall_clock_makespan_ms"] < s0["wall_clock_makespan_ms"]:
            pemenang = s1["algorithm"].upper()
        else:
            pemenang = "DRAW"
        print("-" * 65)
        print(f"  ► Makespan lebih pendek: {pemenang}")

    print("=" * 65)


# ──────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────────────────────────────────────

def main():
    """Fungsi utama: parse args, baca dataset, jalankan benchmark, simpan hasil."""
    args = parse_args()

    global USE_UPLOAD
    USE_UPLOAD = (args.transport == "upload") or (args.transport == "auto" and args.mode == "azure")

    # ── Resolve URL master dan worker berdasarkan --mode / --workers ───────
    master_url  = resolve_master_url(args)
    worker_urls = resolve_worker_urls(args)

    print(f"[INFO] Mode deployment : {args.mode.upper()}")
    print(f"[INFO] Transport gambar: {'UPLOAD (multipart)' if USE_UPLOAD else 'PATH (shared folder)'}")
    print(f"[INFO] Master URL      : {master_url}")
    print("[INFO] Worker URLs yang digunakan:")
    for vm_id, url in worker_urls.items():
        print(f"  {vm_id} -> {url}")

    # ── Buat folder output jika belum ada ─────────────────────────────────
    os.makedirs(args.output,  exist_ok=True)
    os.makedirs(args.results, exist_ok=True)

    # ── Baca dataset ───────────────────────────────────────────────────────
    tasks = baca_metadata(args.dataset)

    # ── Timestamp untuk penamaan file output ──────────────────────────────
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # ── Jalankan benchmark untuk setiap algoritma ──────────────────────────
    all_summaries: list[dict] = []

    for algo in args.algorithms:
        summary = jalankan_satu_algoritma(
            algorithm=algo,
            master_url=master_url,       # Pakai URL master yang sudah di-resolve
            worker_urls=worker_urls,
            tasks=tasks,
            dataset_dir=args.dataset,
            output_dir=args.output,
            results_dir=args.results,
            timestamp=timestamp,
        )
        all_summaries.append(summary)

    # ── Tulis benchmark_summary CSV ────────────────────────────────────────
    tulis_benchmark_summary(all_summaries, args.results, timestamp)

    # ── Cetak perbandingan LPT vs RR di terminal ───────────────────────────
    cetak_perbandingan(all_summaries)


if __name__ == "__main__":
    main()