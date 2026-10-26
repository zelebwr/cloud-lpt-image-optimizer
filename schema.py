"""
schema.py
=========
Definisi model data bersama (shared data contract) untuk seluruh komponen
sistem Cloud LPT Image Optimizer.

File ini TIDAK boleh diubah tanpa koordinasi seluruh anggota tim, karena
digunakan oleh:
  - dataset_generator.py   (Anggota 4 - menghasilkan ImageTask)
  - scheduler_engine.py    (Anggota 2 - mengonsumsi ImageTask, WorkerNode)
  - worker_service.py      (Anggota 3 - mengonsumsi ExecuteTaskRequest)
  - benchmark_runner.py    (Anggota 4 - mengonsumsi TaskAssignment)
  - metrics_collector.py   (Anggota 5 - mengonsumsi BenchmarkMetrics)

Referensi: Proposal Teknis - Bagian 2: Skema Data Bersama & API Contracts.
"""

from pydantic import BaseModel


# ──────────────────────────────────────────────────────────────────────────────
# MODEL TASK GAMBAR
# ──────────────────────────────────────────────────────────────────────────────


class ImageTask(BaseModel):
    """
    Representasi satu task pemrosesan gambar.

    Field estimated_processing_time_ms dihitung dengan rumus:
        (width_px * height_px) / 10000

    Nilai ini merupakan estimasi sintetis untuk keperluan penjadwalan,
    bukan waktu eksekusi aktual.
    """

    task_id: str
    file_path: str           # Path relatif ke gambar input (misal: raw_images/image_001.jpg)
    width_px: int
    height_px: int
    file_size_bytes: int
    estimated_processing_time_ms: float  # Formula: (width_px * height_px) / 10000
    target_scale: float = 0.5           # Rasio skala untuk resize (default: 50%)


# ──────────────────────────────────────────────────────────────────────────────
# MODEL VM WORKER
# ──────────────────────────────────────────────────────────────────────────────


class WorkerNode(BaseModel):
    """
    Representasi satu VM Worker dengan kapasitas dan status beban kerja.

    capacity_multiplier menentukan kecepatan relatif VM:
      - vm-worker-1: 2.0x (Host A, High Computation)
      - vm-worker-2: 1.0x (Host A, Standard)
      - vm-worker-3: 1.5x (Host B, Medium)
      - vm-worker-4: 0.8x (Host B, Light)
    """

    vm_id: str
    host_id: str
    capacity_multiplier: float           # Faktor kecepatan VM
    ready_time_ms: float = 0.0          # Akumulasi waktu kerja VM (diperbarui oleh scheduler)
    current_cpu_utilization: float = 0.0
    current_ram_utilization: float = 0.0
    total_cost_per_sec: float           # Tarif biaya simulasi (unit: G$/detik)


# ──────────────────────────────────────────────────────────────────────────────
# MODEL HASIL PENJADWALAN
# ──────────────────────────────────────────────────────────────────────────────


class TaskAssignment(BaseModel):
    """
    Hasil penjadwalan: satu task yang telah dialokasikan ke satu VM.

    Dikembalikan oleh endpoint /schedule pada Master Node.
    """

    task_id: str
    assigned_vm_id: str
    estimated_start_time_ms: float
    estimated_finish_time_ms: float


# ──────────────────────────────────────────────────────────────────────────────
# MODEL METRIK EVALUASI
# ──────────────────────────────────────────────────────────────────────────────


class BenchmarkMetrics(BaseModel):
    """
    Kumpulan metrik evaluasi performa algoritma penjadwalan.

    Digunakan oleh metrics_collector.py (Anggota 5) untuk membandingkan
    hasil LPT vs Round Robin.

    Penjelasan field:
      - algorithm_name       : "LPT" atau "RoundRobin"
      - makespan_ms          : C_max = max(RT_j) — waktu selesai seluruh batch
      - degree_of_imbalance  : DI = (RT_max - RT_min) / RT_avg
      - avg_cpu_utilization  : U = (sum(RT_j) / (M * C_max)) * 100%
      - throughput_tasks_per_sec : N / C_max (dalam detik)
      - total_cost           : sum(RT_j * tarif_j)
      - scheduling_duration_ms : T_sched — waktu konvergensi algoritma
    """

    algorithm_name: str
    makespan_ms: float
    degree_of_imbalance: float
    avg_cpu_utilization_pct: float
    avg_ram_utilization_pct: float
    throughput_tasks_per_sec: float
    total_cost: float
    scheduling_duration_ms: float
