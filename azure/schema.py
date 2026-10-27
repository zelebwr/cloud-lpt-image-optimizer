# schema.py
# Definisi model data bersama (shared contract) untuk seluruh anggota tim.
# JANGAN diubah tanpa koordinasi — semua anggota mengimpor dari sini.

from pydantic import BaseModel
from typing import Optional


# ──────────────────────────────────────────────────────────────────────────────
# Model untuk satu task pemrosesan gambar
# ──────────────────────────────────────────────────────────────────────────────
class ImageTask(BaseModel):
    task_id: str                              # Identifikasi unik task, mis. "TASK-001"
    file_path: str                            # Path relatif file input, mis. "raw_images/image_001.jpg"
    width_px: int                             # Lebar gambar dalam piksel
    height_px: int                            # Tinggi gambar dalam piksel
    file_size_bytes: int                      # Ukuran file dalam byte
    estimated_processing_time_ms: float       # Estimasi waktu proses = (width*height)/10000
    target_scale: float = 0.5                 # Faktor scaling output (default 50%)


# ──────────────────────────────────────────────────────────────────────────────
# Model untuk satu VM worker node
# ──────────────────────────────────────────────────────────────────────────────
class WorkerNode(BaseModel):
    vm_id: str                                # Identifikasi VM, mis. "vm-worker-1"
    host_id: str                              # Subnet host, mis. "subnet-host-a"
    private_ip: str                           # Private IP dalam VNet Azure, mis. "10.0.1.4"
    capacity_multiplier: float                # Pengganda kapasitas relatif terhadap baseline
    ready_time_ms: float = 0.0                # Waktu VM siap menerima task berikutnya (ms)
    current_cpu_utilization: float = 0.0      # Utilisasi CPU saat ini (0.0–1.0)
    current_ram_utilization: float = 0.0      # Utilisasi RAM saat ini (0.0–1.0)
    total_cost_per_sec: float                 # Biaya per detik (USD), mis. 0.0000116


# ──────────────────────────────────────────────────────────────────────────────
# Model untuk satu penugasan task ke VM tertentu
# ──────────────────────────────────────────────────────────────────────────────
class TaskAssignment(BaseModel):
    task_id: str                              # task_id yang ditugaskan
    assigned_vm_id: str                       # VM yang menerima task ini
    estimated_start_time_ms: float            # Estimasi waktu mulai (ms dari t=0)
    estimated_finish_time_ms: float           # Estimasi waktu selesai (ms dari t=0)


# ──────────────────────────────────────────────────────────────────────────────
# Model ringkasan metrik benchmark satu algoritma
# ──────────────────────────────────────────────────────────────────────────────
class BenchmarkMetrics(BaseModel):
    algorithm_name: str                       # Nama algoritma: "lpt" atau "rr"
    makespan_ms: float                        # Makespan C_max: waktu selesai task terakhir (ms)
    degree_of_imbalance: float                # DI: (makespan - avg_load) / makespan
    avg_cpu_utilization_pct: float            # Rata-rata utilisasi CPU seluruh worker (%)
    avg_ram_utilization_pct: float            # Rata-rata utilisasi RAM seluruh worker (%)
    throughput_tasks_per_sec: float           # TP: total_tasks / (makespan_ms / 1000)
    total_cost: float                         # TC: total biaya eksekusi (USD)
    scheduling_duration_ms: float             # Durasi proses penjadwalan di master (ms)
