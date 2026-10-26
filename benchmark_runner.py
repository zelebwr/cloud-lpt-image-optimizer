"""
benchmark_runner.py
===================
QA Test Orchestrator — Anggota 4 (Workload Generator & QA Test Orchestrator)

Skrip ini mengorkestrasi eksekusi benchmark end-to-end untuk membandingkan
algoritma penjadwalan LPT dan Round Robin pada lingkungan Docker Compose.

Alur kerja:
    1. Muat daftar task dari metadata.json (output dataset_generator.py).
    2. Kirim batch task ke Master Node (/schedule) untuk dijadwalkan.
    3. Eksekusi setiap task ke VM Worker (/execute_task) sesuai alokasi.
    4. Validasi integritas semua gambar output menggunakan Pillow.
    5. Simpan log eksekusi lengkap ke results/execution_log_<algorithm>.csv.
    6. Tampilkan ringkasan perbandingan LPT vs Round Robin.

Penggunaan:
    python benchmark_runner.py
    python benchmark_runner.py --master http://localhost:8000
    python benchmark_runner.py --dataset data --algorithms lpt rr
    python benchmark_runner.py --help

Prasyarat:
    - Docker Compose harus sudah berjalan (docker-compose up -d).
    - dataset_generator.py sudah dijalankan terlebih dahulu.

Catatan:
    Skrip ini TIDAK mengimplementasikan algoritma LPT/RR secara langsung.
    Logika penjadwalan ada di scheduler_engine.py (Anggota 2).
    Skrip ini hanya berperan sebagai HTTP client dan QA orchestrator.
"""

import argparse
import csv
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from PIL import Image

# ──────────────────────────────────────────────────────────────────────────────
# KONFIGURASI LOGGING
# ──────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# KONFIGURASI DEFAULT
# ──────────────────────────────────────────────────────────────────────────────

# URL Master Node dispatcher (FastAPI, Anggota 2)
# Sesuaikan dengan port yang didefinisikan di docker-compose.yml
DEFAULT_MASTER_URL = "http://localhost:8000"

# URL setiap VM Worker (Anggota 3), sesuai docker-compose.yml
# Format: {vm_id: base_url}
DEFAULT_WORKER_URLS = {
    "vm-worker-1": "http://localhost:8001",
    "vm-worker-2": "http://localhost:8002",
    "vm-worker-3": "http://localhost:8003",
    "vm-worker-4": "http://localhost:8004",
}

# Konfigurasi VM Worker (harus konsisten dengan docker-compose.yml & scheduler)
# Format: {vm_id: {host_id, capacity_multiplier, total_cost_per_sec}}
VM_CONFIG = {
    "vm-worker-1": {"host_id": "host-a", "capacity_multiplier": 2.0, "total_cost_per_sec": 0.004},
    "vm-worker-2": {"host_id": "host-a", "capacity_multiplier": 1.0, "total_cost_per_sec": 0.002},
    "vm-worker-3": {"host_id": "host-b", "capacity_multiplier": 1.5, "total_cost_per_sec": 0.003},
    "vm-worker-4": {"host_id": "host-b", "capacity_multiplier": 0.8, "total_cost_per_sec": 0.0016},
}

# Timeout HTTP request dalam detik
HTTP_TIMEOUT = 30

# Header CSV log eksekusi per task
LOG_CSV_HEADER = [
    "algorithm",
    "task_id",
    "assigned_vm_id",
    "estimated_start_ms",
    "estimated_finish_ms",
    "actual_duration_ms",
    "output_file_path",
    "validation_status",
    "status",
    "error_message",
]

# Header CSV ringkasan metrik per algoritma
METRICS_CSV_HEADER = [
    "algorithm",
    "makespan_ms",
    "degree_of_imbalance",
    "avg_utilization_pct",
    "throughput_tasks_per_sec",
    "tasks_total",
    "tasks_succeeded",
    "tasks_failed",
    "scheduling_duration_ms",
]


# ──────────────────────────────────────────────────────────────────────────────
# FUNGSI MUAT DATA
# ──────────────────────────────────────────────────────────────────────────────


def muat_tasks_dari_metadata(dataset_dir: Path) -> list:
    """
    Memuat daftar task dari file metadata.json yang dihasilkan dataset_generator.py.

    Metadata JSON diutamakan karena lebih mudah di-parse dan konsisten
    dengan field schema.py (ImageTask).

    Args:
        dataset_dir: Direktori root dataset (biasanya 'data/').

    Returns:
        List berisi dict metadata setiap task/gambar.

    Raises:
        FileNotFoundError: Jika metadata.json tidak ditemukan.
        SystemExit: Jika file tidak dapat dibaca.
    """
    path_json = dataset_dir / "metadata.json"

    if not path_json.exists():
        logger.error(
            f"File metadata tidak ditemukan: {path_json}\n"
            "Pastikan dataset_generator.py sudah dijalankan terlebih dahulu:\n"
            "  python dataset_generator.py --count 50 --seed 42"
        )
        sys.exit(1)

    try:
        with open(path_json, "r", encoding="utf-8") as f:
            tasks = json.load(f)
        logger.info(f"Berhasil memuat {len(tasks)} task dari {path_json}")
        return tasks
    except json.JSONDecodeError as e:
        logger.error(f"Format metadata.json tidak valid: {e}")
        sys.exit(1)


def bangun_payload_tasks(tasks: list) -> list:
    """
    Mengonversi list metadata dict ke format payload yang dikirim ke /schedule.

    Menyaring field agar sesuai dengan schema ImageTask:
        task_id, file_path, width_px, height_px, file_size_bytes,
        estimated_processing_time_ms, target_scale

    Args:
        tasks: List dict metadata dari metadata.json.

    Returns:
        List dict yang siap dikirim sebagai JSON ke endpoint /schedule.
    """
    payload = []
    for t in tasks:
        payload.append({
            "task_id": t["task_id"],
            "file_path": t["file_path"],
            "width_px": t["width_px"],
            "height_px": t["height_px"],
            "file_size_bytes": t["file_size_bytes"],
            "estimated_processing_time_ms": float(t["estimated_processing_time_ms"]),
            "target_scale": 0.5,  # Rasio resize default sesuai proposal
        })
    return payload


# ──────────────────────────────────────────────────────────────────────────────
# FUNGSI HTTP CLIENT — MASTER NODE
# ──────────────────────────────────────────────────────────────────────────────


def request_penjadwalan(
    master_url: str,
    tasks_payload: list,
    algorithm: str,
) -> tuple:
    """
    Mengirim daftar task ke Master Node untuk dijadwalkan.

    Memanggil endpoint POST /schedule pada Master Node (Anggota 2).

    Request body:
        {
            "algorithm": "lpt" | "rr",
            "tasks": [ list of ImageTask dict ]
        }

    Response yang diharapkan:
        {
            "assignments": [ list of TaskAssignment dict ],
            "scheduling_duration_ms": float
        }

    Args:
        master_url: Base URL Master Node, contoh: http://localhost:8000.
        tasks_payload: List dict task sesuai schema ImageTask.
        algorithm: Nama algoritma — "lpt" atau "rr".

    Returns:
        Tuple berisi (list TaskAssignment dict, scheduling_duration_ms float).
        Mengembalikan ([], 0.0) jika terjadi kegagalan koneksi.
    """
    endpoint = f"{master_url}/schedule"
    body = {
        "algorithm": algorithm,
        "tasks": tasks_payload,
    }

    logger.info(f"[{algorithm.upper()}] Mengirim {len(tasks_payload)} task ke {endpoint} ...")

    try:
        resp = requests.post(endpoint, json=body, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        assignments = data.get("assignments", [])
        sched_ms = data.get("scheduling_duration_ms", 0.0)
        logger.info(
            f"[{algorithm.upper()}] Penjadwalan selesai: {len(assignments)} assignment, "
            f"waktu konvergensi: {sched_ms:.3f} ms"
        )
        return assignments, sched_ms

    except requests.exceptions.ConnectionError:
        logger.error(
            f"Gagal terhubung ke Master Node ({endpoint}).\n"
            "Pastikan Docker Compose sudah berjalan:\n"
            "  docker-compose up -d"
        )
        return [], 0.0

    except requests.exceptions.Timeout:
        logger.error(f"Request ke {endpoint} timeout setelah {HTTP_TIMEOUT} detik.")
        return [], 0.0

    except requests.exceptions.HTTPError as e:
        logger.error(f"Master Node mengembalikan error HTTP: {e}")
        return [], 0.0

    except Exception as e:
        logger.error(f"Error tidak terduga saat menghubungi Master Node: {e}")
        return [], 0.0


# ──────────────────────────────────────────────────────────────────────────────
# FUNGSI HTTP CLIENT — VM WORKER
# ──────────────────────────────────────────────────────────────────────────────


def eksekusi_task_pada_worker(
    worker_url: str,
    task_id: str,
    input_file_path: str,
    output_file_path: str,
    target_scale: float = 0.5,
    quality: int = 85,
) -> dict:
    """
    Mengirim satu task ke VM Worker untuk dieksekusi.

    Memanggil endpoint POST /execute_task pada Worker Service (Anggota 3).

    Request body:
        {
            "task_id": str,
            "input_file_path": str,
            "output_file_path": str,
            "target_scale": float,
            "quality": int
        }

    Response yang diharapkan:
        {
            "status": "SUCCESS" | "FAILED",
            "task_id": str,
            "actual_duration_ms": float,
            "output_file_path": str
        }

    Args:
        worker_url: Base URL VM Worker, contoh: http://localhost:8001.
        task_id: ID task yang akan dieksekusi.
        input_file_path: Path absolut gambar input (diakses dari dalam container).
        output_file_path: Path absolut tujuan gambar output.
        target_scale: Rasio resize (default: 0.5).
        quality: Kualitas JPEG output (default: 85).

    Returns:
        Dict berisi hasil eksekusi dari worker.
        Mengembalikan dict error jika terjadi kegagalan koneksi.
    """
    endpoint = f"{worker_url}/execute_task"
    body = {
        "task_id": task_id,
        "input_file_path": input_file_path,
        "output_file_path": output_file_path,
        "target_scale": target_scale,
        "quality": quality,
    }

    try:
        resp = requests.post(endpoint, json=body, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
        return resp.json()

    except requests.exceptions.ConnectionError:
        logger.warning(
            f"Gagal terhubung ke worker {worker_url} untuk task {task_id}.\n"
            "Pastikan container worker sudah berjalan."
        )
        return {
            "status": "FAILED",
            "task_id": task_id,
            "actual_duration_ms": 0.0,
            "error": f"ConnectionError ke {worker_url}",
        }

    except requests.exceptions.HTTPError as e:
        logger.warning(f"Worker {worker_url} mengembalikan HTTP error untuk {task_id}: {e}")
        return {
            "status": "FAILED",
            "task_id": task_id,
            "actual_duration_ms": 0.0,
            "error": str(e),
        }

    except Exception as e:
        logger.warning(f"Error tidak terduga saat eksekusi {task_id} di {worker_url}: {e}")
        return {
            "status": "FAILED",
            "task_id": task_id,
            "actual_duration_ms": 0.0,
            "error": str(e),
        }


# ──────────────────────────────────────────────────────────────────────────────
# FUNGSI VALIDASI INTEGRITAS OUTPUT
# ──────────────────────────────────────────────────────────────────────────────


def validasi_integritas_output(log_eksekusi: list) -> dict:
    """
    Memvalidasi semua gambar output dapat dibuka menggunakan Pillow.

    Memastikan:
    - File gambar output benar-benar ada di disk.
    - File tidak korup dan dapat dibuka oleh Pillow.
    - Dimensi gambar output sesuai (tidak kosong).

    Args:
        log_eksekusi: List dict hasil eksekusi setiap task.

    Returns:
        Dict berisi:
            - "valid": list nama file yang lolos validasi.
            - "invalid": list nama file yang gagal validasi.
            - "missing": list nama file yang tidak ditemukan.
    """
    valid_files = []
    invalid_files = []
    missing_files = []

    for log in log_eksekusi:
        if log["status"] != "SUCCESS":
            # Lewati task yang sudah gagal di tahap eksekusi
            continue

        output_path = log.get("output_file_path", "")
        if not output_path:
            missing_files.append(log["task_id"])
            continue

        path = Path(output_path)
        if not path.exists():
            logger.warning(f"File output tidak ditemukan: {output_path}")
            missing_files.append(log["task_id"])
            continue

        try:
            with Image.open(path) as img:
                img.verify()  # Verifikasi integritas file JPEG
            valid_files.append(log["task_id"])
        except Exception as e:
            logger.warning(f"File output korup ({path.name}): {e}")
            invalid_files.append(log["task_id"])

    return {
        "valid": valid_files,
        "invalid": invalid_files,
        "missing": missing_files,
    }


# ──────────────────────────────────────────────────────────────────────────────
# FUNGSI PENYIMPANAN LOG
# ──────────────────────────────────────────────────────────────────────────────


def simpan_log_eksekusi_csv(log_eksekusi: list, path_csv: Path) -> None:
    """
    Menyimpan log eksekusi seluruh task ke file CSV.

    Setiap baris mewakili satu task dengan informasi:
    algoritma, task_id, vm yang mengerjakan, waktu estimasi,
    waktu aktual, status, dan pesan error jika ada.

    Args:
        log_eksekusi: List dict hasil eksekusi.
        path_csv: Path file CSV tujuan.
    """
    try:
        path_csv.parent.mkdir(parents=True, exist_ok=True)
        with open(path_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=LOG_CSV_HEADER, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(log_eksekusi)
        logger.info(f"Log eksekusi disimpan: {path_csv}")
    except OSError as e:
        logger.error(f"Gagal menyimpan log CSV: {e}")


def simpan_metrik_csv(semua_metrik: list, path_csv: Path) -> None:
    """
    Menyimpan ringkasan metrik perbandingan LPT vs Round Robin ke CSV.

    Args:
        semua_metrik: List dict metrik per algoritma.
        path_csv: Path file CSV tujuan.
    """
    try:
        path_csv.parent.mkdir(parents=True, exist_ok=True)
        with open(path_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=METRICS_CSV_HEADER, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(semua_metrik)
        logger.info(f"Metrik ringkasan disimpan: {path_csv}")
    except OSError as e:
        logger.error(f"Gagal menyimpan metrik CSV: {e}")


# ──────────────────────────────────────────────────────────────────────────────
# FUNGSI HITUNG METRIK SEDERHANA (untuk keperluan log & tampilan ringkasan)
# ──────────────────────────────────────────────────────────────────────────────


def hitung_metrik_dari_log(
    algorithm: str,
    log_eksekusi: list,
    scheduling_duration_ms: float,
) -> dict:
    """
    Menghitung metrik performa dasar dari log eksekusi.

    Catatan: Metrik lengkap (Degree of Imbalance, biaya, dll.) dihitung oleh
    Anggota 5 menggunakan metrics_collector.py. Fungsi ini hanya untuk
    keperluan ringkasan di benchmark_runner.

    Metrik yang dihitung:
        - makespan_ms: waktu finish task terakhir (max estimated_finish_ms)
        - avg_utilization_pct: estimasi utilisasi berdasarkan waktu estimasi
        - throughput_tasks_per_sec: jumlah task sukses / makespan (detik)

    Args:
        algorithm: Nama algoritma ("lpt" atau "rr").
        log_eksekusi: List dict log eksekusi per task.
        scheduling_duration_ms: Waktu konvergensi algoritma dari master node.

    Returns:
        Dict berisi metrik ringkasan.
    """
    sukses = [r for r in log_eksekusi if r["status"] == "SUCCESS"]
    gagal = [r for r in log_eksekusi if r["status"] != "SUCCESS"]

    # Makespan = waktu finish estimasi task terakhir (dalam ms)
    finish_times = [r.get("estimated_finish_ms", 0) for r in log_eksekusi]
    makespan_ms = max(finish_times) if finish_times else 0.0

    throughput = (len(sukses) / (makespan_ms / 1000.0)) if makespan_ms > 0 else 0.0

    return {
        "algorithm": algorithm.upper(),
        "makespan_ms": round(makespan_ms, 3),
        "degree_of_imbalance": 0.0,   # Dihitung lengkap oleh Anggota 5
        "avg_utilization_pct": 0.0,   # Dihitung lengkap oleh Anggota 5
        "throughput_tasks_per_sec": round(throughput, 4),
        "tasks_total": len(log_eksekusi),
        "tasks_succeeded": len(sukses),
        "tasks_failed": len(gagal),
        "scheduling_duration_ms": round(scheduling_duration_ms, 3),
    }


# ──────────────────────────────────────────────────────────────────────────────
# FUNGSI UTAMA SATU SIKLUS BENCHMARK
# ──────────────────────────────────────────────────────────────────────────────


def jalankan_benchmark_satu_algoritma(
    algorithm: str,
    tasks: list,
    tasks_payload: list,
    master_url: str,
    worker_urls: dict,
    dataset_dir: Path,
    output_dir: Path,
    results_dir: Path,
) -> tuple:
    """
    Menjalankan satu siklus benchmark lengkap untuk satu algoritma.

    Alur:
        1. Kirim tasks ke master /schedule → dapatkan assignments.
        2. Buat index task_id → metadata task (untuk resolusi path input).
        3. Untuk setiap assignment, tentukan URL worker dan eksekusi task.
        4. Kumpulkan log eksekusi.
        5. Simpan log ke CSV.

    Args:
        algorithm: Nama algoritma — "lpt" atau "rr".
        tasks: List dict raw metadata (dari metadata.json).
        tasks_payload: List dict task payload untuk dikirim ke master.
        master_url: URL Master Node.
        worker_urls: Dict {vm_id: url} untuk setiap VM Worker.
        dataset_dir: Direktori root dataset (berisi raw_images/).
        output_dir: Direktori untuk menyimpan gambar hasil pemrosesan.
        results_dir: Direktori untuk menyimpan file CSV log.

    Returns:
        Tuple berisi (list log_eksekusi, scheduling_duration_ms, dict metrik).
    """
    logger.info(f"\n{'='*55}")
    logger.info(f"  Memulai benchmark: {algorithm.upper()}")
    logger.info(f"{'='*55}")

    # ── Langkah 1: Minta penjadwalan ke Master Node ───────────────────────────
    assignments, sched_ms = request_penjadwalan(master_url, tasks_payload, algorithm)

    if not assignments:
        logger.error(f"[{algorithm.upper()}] Tidak ada assignment yang diterima. Benchmark dibatalkan.")
        return [], 0.0, {}

    # ── Langkah 2: Buat index task_id → task metadata untuk lookup cepat ─────
    task_index = {t["task_id"]: t for t in tasks}

    # ── Langkah 3: Buat direktori output untuk algoritma ini ─────────────────
    alg_output_dir = output_dir / algorithm.lower()
    alg_output_dir.mkdir(parents=True, exist_ok=True)

    # ── Langkah 4: Eksekusi setiap task ke VM Worker yang ditugaskan ─────────
    log_eksekusi = []
    total = len(assignments)

    for idx, assignment in enumerate(assignments, 1):
        task_id = assignment["task_id"]
        vm_id = assignment["assigned_vm_id"]
        est_start = assignment.get("estimated_start_time_ms", 0.0)
        est_finish = assignment.get("estimated_finish_time_ms", 0.0)

        # Dapatkan metadata task asli
        task_meta = task_index.get(task_id, {})
        if not task_meta:
            logger.warning(f"[{idx}/{total}] Task {task_id} tidak ada di metadata. Dilewati.")
            log_eksekusi.append({
                "algorithm": algorithm.upper(),
                "task_id": task_id,
                "assigned_vm_id": vm_id,
                "estimated_start_ms": est_start,
                "estimated_finish_ms": est_finish,
                "actual_duration_ms": 0.0,
                "output_file_path": "",
                "validation_status": "SKIPPED",
                "status": "FAILED",
                "error_message": "Task tidak ditemukan di metadata",
            })
            continue

        # Resolusi path absolut gambar input dan output
        # Path ini harus dapat diakses dari dalam Docker container (volume mount)
        input_abs = str((dataset_dir / task_meta["file_path"]).resolve())
        output_filename = Path(task_meta["file_path"]).name
        output_abs = str((alg_output_dir / output_filename).resolve())

        # Dapatkan URL worker berdasarkan vm_id
        worker_url = worker_urls.get(vm_id)
        if not worker_url:
            logger.warning(f"[{idx}/{total}] URL untuk {vm_id} tidak diketahui. Dilewati.")
            log_eksekusi.append({
                "algorithm": algorithm.upper(),
                "task_id": task_id,
                "assigned_vm_id": vm_id,
                "estimated_start_ms": est_start,
                "estimated_finish_ms": est_finish,
                "actual_duration_ms": 0.0,
                "output_file_path": "",
                "validation_status": "SKIPPED",
                "status": "FAILED",
                "error_message": f"URL untuk {vm_id} tidak diketahui",
            })
            continue

        # Eksekusi task ke worker
        logger.info(
            f"[{idx:3d}/{total}] {task_id} → {vm_id} "
            f"(est: {est_start:.0f}–{est_finish:.0f} ms)"
        )
        hasil = eksekusi_task_pada_worker(
            worker_url=worker_url,
            task_id=task_id,
            input_file_path=input_abs,
            output_file_path=output_abs,
            target_scale=task_meta.get("target_scale", 0.5),
        )

        log_eksekusi.append({
            "algorithm": algorithm.upper(),
            "task_id": task_id,
            "assigned_vm_id": vm_id,
            "estimated_start_ms": est_start,
            "estimated_finish_ms": est_finish,
            "actual_duration_ms": hasil.get("actual_duration_ms", 0.0),
            "output_file_path": hasil.get("output_file_path", output_abs),
            "validation_status": "",   # Diisi setelah validasi
            "status": hasil.get("status", "FAILED"),
            "error_message": hasil.get("error", ""),
        })

    # ── Langkah 5: Validasi integritas gambar output ──────────────────────────
    logger.info(f"[{algorithm.upper()}] Memvalidasi integritas gambar output...")
    hasil_validasi = validasi_integritas_output(log_eksekusi)

    # Update status validasi di log
    valid_set = set(hasil_validasi["valid"])
    invalid_set = set(hasil_validasi["invalid"])
    missing_set = set(hasil_validasi["missing"])
    for log in log_eksekusi:
        tid = log["task_id"]
        if tid in valid_set:
            log["validation_status"] = "VALID"
        elif tid in invalid_set:
            log["validation_status"] = "CORRUPT"
        elif tid in missing_set:
            log["validation_status"] = "MISSING"

    logger.info(
        f"[{algorithm.upper()}] Validasi selesai: "
        f"{len(hasil_validasi['valid'])} valid, "
        f"{len(hasil_validasi['invalid'])} korup, "
        f"{len(hasil_validasi['missing'])} tidak ditemukan"
    )

    # ── Langkah 6: Simpan log CSV ─────────────────────────────────────────────
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path_log_csv = results_dir / f"execution_log_{algorithm.lower()}_{timestamp}.csv"
    simpan_log_eksekusi_csv(log_eksekusi, path_log_csv)

    # ── Hitung metrik ringkasan ───────────────────────────────────────────────
    metrik = hitung_metrik_dari_log(algorithm, log_eksekusi, sched_ms)

    return log_eksekusi, sched_ms, metrik


# ──────────────────────────────────────────────────────────────────────────────
# FUNGSI TAMPILAN RINGKASAN AKHIR
# ──────────────────────────────────────────────────────────────────────────────


def tampilkan_ringkasan_perbandingan(semua_metrik: list) -> None:
    """
    Menampilkan tabel ringkasan perbandingan metrik LPT vs Round Robin.

    Args:
        semua_metrik: List dict metrik per algoritma.
    """
    if not semua_metrik:
        return

    print("\n" + "=" * 65)
    print("  RINGKASAN PERBANDINGAN: LPT vs Round Robin")
    print("=" * 65)
    print(f"  {'Metrik':<35} {'LPT':>12} {'RR':>12}")
    print(f"  {'-'*35} {'-'*12} {'-'*12}")

    # Buat dict untuk lookup cepat
    metrik_map = {m["algorithm"]: m for m in semua_metrik}
    lpt = metrik_map.get("LPT", {})
    rr = metrik_map.get("RR", {})

    def fmt(val, suffix=""):
        return f"{val:,.2f}{suffix}" if val else "N/A"

    rows = [
        ("Makespan (ms)",               "makespan_ms",              ""),
        ("Throughput (tasks/sec)",       "throughput_tasks_per_sec", ""),
        ("Scheduling Time (ms)",         "scheduling_duration_ms",   ""),
        ("Tasks Sukses",                 "tasks_succeeded",          ""),
        ("Tasks Gagal",                  "tasks_failed",             ""),
    ]

    for label, key, suffix in rows:
        lpt_val = lpt.get(key, "N/A")
        rr_val = rr.get(key, "N/A")
        lv = f"{lpt_val:,.3f}{suffix}" if isinstance(lpt_val, float) else str(lpt_val)
        rv = f"{rr_val:,.3f}{suffix}" if isinstance(rr_val, float) else str(rr_val)
        print(f"  {label:<35} {lv:>12} {rv:>12}")

    print("=" * 65)
    print("  Catatan: Metrik lengkap (DI, Utilization, Cost) dihitung")
    print("           oleh metrics_collector.py (Anggota 5).")
    print("=" * 65)


# ──────────────────────────────────────────────────────────────────────────────
# COMMAND-LINE INTERFACE
# ──────────────────────────────────────────────────────────────────────────────


def parse_argumen() -> argparse.Namespace:
    """
    Mendefinisikan dan mem-parsing argumen command-line.

    Returns:
        Namespace berisi nilai argumen yang telah di-parse.
    """
    parser = argparse.ArgumentParser(
        prog="benchmark_runner.py",
        description=(
            "QA Test Orchestrator — mengorkestrasi benchmark LPT vs Round Robin "
            "melalui REST API Master Node dan VM Worker."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Contoh:\n"
            "  python benchmark_runner.py\n"
            "  python benchmark_runner.py --master http://localhost:8000\n"
            "  python benchmark_runner.py --algorithms lpt rr --dataset data\n"
            "\n"
            "Prasyarat:\n"
            "  docker-compose up -d         (jalankan seluruh container)\n"
            "  python dataset_generator.py  (generate dataset terlebih dahulu)\n"
        ),
    )

    parser.add_argument(
        "--master",
        type=str,
        default=DEFAULT_MASTER_URL,
        metavar="URL",
        help=f"URL Master Node dispatcher (default: {DEFAULT_MASTER_URL})",
    )
    parser.add_argument(
        "--dataset",
        type=str,
        default="data",
        metavar="DIR",
        help="Direktori root dataset yang berisi metadata.json (default: data)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/processed_images",
        metavar="DIR",
        help="Direktori untuk menyimpan gambar hasil pemrosesan (default: data/processed_images)",
    )
    parser.add_argument(
        "--results",
        type=str,
        default="results",
        metavar="DIR",
        help="Direktori untuk menyimpan file log dan metrik CSV (default: results)",
    )
    parser.add_argument(
        "--algorithms",
        nargs="+",
        default=["lpt", "rr"],
        choices=["lpt", "rr"],
        metavar="ALG",
        help="Algoritma yang akan diuji: lpt, rr, atau keduanya (default: lpt rr)",
    )

    return parser.parse_args()


# ──────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────────────────────────────────────


def main() -> None:
    """
    Entry point benchmark_runner.

    Alur lengkap:
        1. Parse argumen CLI.
        2. Muat tasks dari metadata.json.
        3. Untuk setiap algoritma yang dipilih, jalankan satu siklus benchmark.
        4. Simpan metrik ringkasan ke CSV.
        5. Tampilkan perbandingan di konsol.
    """
    args = parse_argumen()
    script_dir = Path(__file__).parent

    dataset_dir = script_dir / args.dataset
    output_dir = script_dir / args.output
    results_dir = script_dir / args.results

    logger.info("=" * 55)
    logger.info("  Cloud LPT Image Optimizer - Benchmark Runner")
    logger.info("=" * 55)
    logger.info(f"Master Node     : {args.master}")
    logger.info(f"Dataset dir     : {dataset_dir.resolve()}")
    logger.info(f"Output dir      : {output_dir.resolve()}")
    logger.info(f"Results dir     : {results_dir.resolve()}")
    logger.info(f"Algoritma       : {', '.join(a.upper() for a in args.algorithms)}")

    # ── Muat tasks dari metadata ──────────────────────────────────────────────
    tasks = muat_tasks_dari_metadata(dataset_dir)
    tasks_payload = bangun_payload_tasks(tasks)

    # ── Jalankan benchmark per algoritma ─────────────────────────────────────
    semua_metrik = []

    for algorithm in args.algorithms:
        _, _, metrik = jalankan_benchmark_satu_algoritma(
            algorithm=algorithm,
            tasks=tasks,
            tasks_payload=tasks_payload,
            master_url=args.master,
            worker_urls=DEFAULT_WORKER_URLS,
            dataset_dir=dataset_dir,
            output_dir=output_dir,
            results_dir=results_dir,
        )
        if metrik:
            semua_metrik.append(metrik)

    # ── Simpan metrik ringkasan ke CSV ────────────────────────────────────────
    if semua_metrik:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path_metrik = results_dir / f"benchmark_summary_{timestamp}.csv"
        simpan_metrik_csv(semua_metrik, path_metrik)

    # ── Tampilkan perbandingan akhir ──────────────────────────────────────────
    tampilkan_ringkasan_perbandingan(semua_metrik)

    logger.info("Benchmark runner selesai.")


if __name__ == "__main__":
    main()
