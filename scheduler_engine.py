"""
scheduler_engine.py
===================
Master Dispatcher Node - Core Algorithm & Scheduler Service.
Mengimplementasikan kelas SchedulerEngine dan Web Service FastAPI
untuk penjadwalan tugas kompresi/optimasi gambar terdistribusi di Azure.

Peran: Anggota 2 (Core Algorithm & Scheduler Developer)
Referensi: Proposal Teknis - Bagian 2 (schema.py), Bagian 3 (Peran 2), Bagian 4

Spesifikasi Endpoint:
    POST /schedule
    Request Body:
        {
            "algorithm": "lpt" | "rr",
            "tasks": [ ImageTask, ... ],
            "workers": [ WorkerNode, ... ]  (opsional, default: VM Azure Standar)
        }
    Response Body:
        {
            "assignments": [ TaskAssignment, ... ],
            "scheduling_duration_ms": float,
            "algorithm": str,
            "total_tasks": int,
            "makespan_ms": float
        }
"""

import logging
import time
from typing import List, Optional

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from lpt_logic import run_lpt
from rr_logic import run_round_robin
from schema import ImageTask, TaskAssignment, WorkerNode

# ──────────────────────────────────────────────────────────────────────────────
# LOGGING SETUP
# ──────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [MasterScheduler] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("MasterScheduler")


# ──────────────────────────────────────────────────────────────────────────────
# WORKER DEFAULT TOPOLOGI AZURE (Host A & Host B)
# ──────────────────────────────────────────────────────────────────────────────

DEFAULT_AZURE_WORKERS: List[WorkerNode] = [
    WorkerNode(
        vm_id="vm-worker-1",
        host_id="host-a",
        capacity_multiplier=2.0,  # Standard_B2s (2 vCPU, 4GB) - High Performance
        ready_time_ms=0.0,
        current_cpu_utilization=0.0,
        current_ram_utilization=0.0,
        total_cost_per_sec=0.004,
    ),
    WorkerNode(
        vm_id="vm-worker-2",
        host_id="host-a",
        capacity_multiplier=1.0,  # Standard_B1s (1 vCPU, 2GB) - Standard
        ready_time_ms=0.0,
        current_cpu_utilization=0.0,
        current_ram_utilization=0.0,
        total_cost_per_sec=0.002,
    ),
    WorkerNode(
        vm_id="vm-worker-3",
        host_id="host-b",
        capacity_multiplier=1.5,  # Standard_B2s (2 vCPU, 4GB) - Medium
        ready_time_ms=0.0,
        current_cpu_utilization=0.0,
        current_ram_utilization=0.0,
        total_cost_per_sec=0.003,
    ),
    WorkerNode(
        vm_id="vm-worker-4",
        host_id="host-b",
        capacity_multiplier=0.8,  # Standard_B1s (1 vCPU, 2GB) - Light Weight
        ready_time_ms=0.0,
        current_cpu_utilization=0.0,
        current_ram_utilization=0.0,
        total_cost_per_sec=0.0016,
    ),
]


# ──────────────────────────────────────────────────────────────────────────────
# REQUEST & RESPONSE MODEL UNTUK REST API
# ──────────────────────────────────────────────────────────────────────────────


class ScheduleRequest(BaseModel):
    """
    Model payload untuk request penjadwalan via POST /schedule.
    """

    algorithm: str = Field(
        ...,
        description="Pilihan algoritma: 'lpt' untuk Longest Processing Time, atau 'rr' untuk Round Robin",
        examples=["lpt", "rr"],
    )
    tasks: List[ImageTask] = Field(
        ...,
        description="Daftar objek ImageTask yang akan dijadwalkan",
    )
    workers: Optional[List[WorkerNode]] = Field(
        default=None,
        description="Daftar kustom WorkerNode. Jika tidak diisi, menggunakan default 4 VM Azure",
    )


class ScheduleResponse(BaseModel):
    """
    Model payload untuk respons hasil penjadwalan dari POST /schedule.
    """

    assignments: List[TaskAssignment] = Field(
        ...,
        description="Daftar alokasi tugas ke masing-masing VM Worker",
    )
    scheduling_duration_ms: float = Field(
        ...,
        description="Waktu konvergensi penjadwalan dalam milidetik (T_sched)",
    )
    algorithm: str = Field(
        ...,
        description="Nama algoritma yang digunakan ('LPT' atau 'RoundRobin')",
    )
    total_tasks: int = Field(
        ...,
        description="Jumlah task yang dijadwalkan",
    )
    makespan_ms: float = Field(
        ...,
        description="Estimasi makespan C_max (waktu penyelesaian task paling akhir)",
    )


# ──────────────────────────────────────────────────────────────────────────────
# KELAS SCHEDULER ENGINE
# ──────────────────────────────────────────────────────────────────────────────


class SchedulerEngine:
    """
    Mesin penjadwalan utama di Master Node.
    Mengelola worker dan mengeksekusi algoritma LPT atau Round Robin.
    """

    def __init__(self, workers: Optional[List[WorkerNode]] = None):
        """
        Inisialisasi SchedulerEngine dengan daftar worker default atau kustom.
        """
        self.workers: List[WorkerNode] = (
            [w.model_copy() for w in workers]
            if workers is not None
            else [w.model_copy() for w in DEFAULT_AZURE_WORKERS]
        )

    def reset_workers(self) -> None:
        """
        Mereset akumulasi ready_time_ms seluruh worker kembali ke 0.0.
        """
        for w in self.workers:
            w.ready_time_ms = 0.0

    def set_workers(self, workers: List[WorkerNode]) -> None:
        """
        Memperbarui daftar worker aktif pada engine.
        """
        if not workers:
            raise ValueError("Daftar worker tidak boleh kosong.")
        self.workers = [w.model_copy() for w in workers]

    def schedule(
        self,
        tasks: List[ImageTask],
        algorithm: str = "lpt",
        custom_workers: Optional[List[WorkerNode]] = None,
    ) -> tuple[List[TaskAssignment], float, float, str]:
        """
        Mengeksekusi algoritma penjadwalan dan mengukur durasi konvergensi T_sched.

        Args:
            tasks: Daftar ImageTask yang akan dialokasikan.
            algorithm: 'lpt' | 'rr' | 'roundrobin'.
            custom_workers: Opsional daftar worker spesifik untuk batch ini.

        Returns:
            Tuple berisi:
                - assignments: List[TaskAssignment]
                - scheduling_duration_ms: float (T_sched)
                - makespan_ms: float (C_max estimasi)
                - canonical_algorithm_name: str ("LPT" | "RoundRobin")
        """
        algo_normalized = algorithm.strip().lower()
        if algo_normalized in ("lpt", "longest_processing_time"):
            canonical_algo = "LPT"
        elif algo_normalized in ("rr", "roundrobin", "round_robin"):
            canonical_algo = "RoundRobin"
        else:
            raise ValueError(
                f"Algoritma '{algorithm}' tidak dikenali. Pilih 'lpt' atau 'rr'."
            )

        # Siapkan worker pool (gunakan custom_workers jika ada, atau salinan self.workers)
        active_workers = (
            [w.model_copy() for w in custom_workers]
            if custom_workers is not None
            else [w.model_copy() for w in self.workers]
        )

        # Pengukuran durasi konvergensi algoritma secara presisi (T_sched)
        t_start = time.perf_counter()

        if canonical_algo == "LPT":
            assignments, updated_workers = run_lpt(tasks, active_workers)
        else:
            assignments, updated_workers = run_round_robin(tasks, active_workers)

        t_end = time.perf_counter()
        scheduling_duration_ms = (t_end - t_start) * 1000.0

        # Hitung makespan estimasi: max(finish_time) dari semua assignment
        if assignments:
            makespan_ms = max(a.estimated_finish_time_ms for a in assignments)
        else:
            makespan_ms = 0.0

        return assignments, scheduling_duration_ms, makespan_ms, canonical_algo


# ──────────────────────────────────────────────────────────────────────────────
# INISIALISASI APLIKASI FASTAPI & INSTANCE ENGINE
# ──────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Cloud LPT Image Optimizer - Master Scheduler Service",
    description=(
        "REST API Master Node untuk penjadwalan task kompresi gambar terdistribusi "
        "menggunakan algoritma Longest Processing Time (LPT) dan Round Robin (RR)."
    ),
    version="1.0.0",
)

engine = SchedulerEngine()


# ──────────────────────────────────────────────────────────────────────────────
# FASTAPI ENDPOINTS
# ──────────────────────────────────────────────────────────────────────────────


@app.get("/", summary="Health Check & System Information")
def health_check():
    """
    Endpoint pemeriksaan status Master Node Dispatcher.
    """
    return {
        "status": "ONLINE",
        "service": "Master Scheduler Node",
        "supported_algorithms": ["lpt", "rr"],
        "default_workers_count": len(engine.workers),
        "workers": [
            {
                "vm_id": w.vm_id,
                "host_id": w.host_id,
                "capacity_multiplier": w.capacity_multiplier,
                "ready_time_ms": w.ready_time_ms,
            }
            for w in engine.workers
        ],
    }


@app.get("/workers", summary="Get Active Workers")
def get_workers():
    """
    Mendapatkan daftar worker aktif saat ini beserta konfigurasi kapasitasnya.
    """
    return {"workers": engine.workers}


@app.post("/workers/reset", summary="Reset Workers Ready Time")
def reset_workers():
    """
    Mereset akumulasi ready_time seluruh worker menjadi 0.
    """
    engine.reset_workers()
    logger.info("Ready time seluruh worker berhasil direset ke 0.0 ms.")
    return {"message": "Ready time worker berhasil direset.", "workers": engine.workers}


@app.post("/schedule", response_model=ScheduleResponse, summary="Schedule Image Tasks")
def schedule_tasks(request: ScheduleRequest):
    """
    Endpoint utama penjadwalan tugas pemrosesan gambar.

    Menerima batch ImageTask dan mengembalikan daftar TaskAssignment
    serta durasi konvergensi algoritma (scheduling_duration_ms).
    """
    logger.info(
        f"Menerima request penjadwalan: {len(request.tasks)} task, "
        f"algoritma='{request.algorithm}'"
    )

    try:
        assignments, duration_ms, makespan_ms, canonical_algo = engine.schedule(
            tasks=request.tasks,
            algorithm=request.algorithm,
            custom_workers=request.workers,
        )

        logger.info(
            f"Penjadwalan [{canonical_algo}] sukses: {len(assignments)} assignment, "
            f"T_sched={duration_ms:.3f} ms, Makespan={makespan_ms:.3f} ms"
        )

        return ScheduleResponse(
            assignments=assignments,
            scheduling_duration_ms=round(duration_ms, 4),
            algorithm=canonical_algo,
            total_tasks=len(assignments),
            makespan_ms=round(makespan_ms, 3),
        )

    except ValueError as e:
        logger.error(f"Validasi penjadwalan gagal: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.exception(f"Error internal pada saat penjadwalan: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Terjadi kesalahan saat memproses penjadwalan: {e}",
        )


# ──────────────────────────────────────────────────────────────────────────────
# ENTRYPOINT JIKA DIJALANKAN LANGSUNG VIA CLI
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    logger.info("Menjalankan Master Scheduler Service pada http://0.0.0.0:8000")
    uvicorn.run("scheduler_engine:app", host="0.0.0.0", port=8000, reload=True)
