"""
rr_logic.py
===========
Implementasi Algoritma Penjadwalan Baseline Round Robin (RR)
untuk Lingkungan Cloud Computing.

Peran: Anggota 2 (Core Algorithm & Scheduler Developer)
Referensi: Proposal Teknis - Bagian 3 (Peran 2: Langkah 3)

Prinsip Algoritma Round Robin:
------------------------------
1. Seluruh task dialokasikan secara berurutan berputar menurut urutan kedatangan:
       T_i -> R_{(i mod M)}  (indeks 0..M-1)
2. Tidak melakukan pengurutan berdasarkan bobot/durasi tugas.
3. Waktu selesai task dihitung berdasarkan akumulasi ready_time VM dan multiplier kapasitasnya:
       duration = ET_i / capacity_multiplier_k
       finish_time = RT_k + duration
       RT_k <- finish_time
"""

from typing import List, Tuple
from schema import ImageTask, WorkerNode, TaskAssignment


def calculate_estimated_time(task: ImageTask) -> float:
    """
    Menghitung atau memvalidasi estimasi waktu pemrosesan task gambar (ET_i).

    Formula:
        ET_i = (width_px * height_px) / 10000

    Args:
        task: Objek ImageTask.

    Returns:
        Estimasi waktu pemrosesan dalam milidetik (ms).
    """
    if task.estimated_processing_time_ms and task.estimated_processing_time_ms > 0:
        return float(task.estimated_processing_time_ms)
    return float((task.width_px * task.height_px) / 10000.0)


def run_round_robin(
    tasks: List[ImageTask],
    workers: List[WorkerNode],
) -> Tuple[List[TaskAssignment], List[WorkerNode]]:
    """
    Mengeksekusi algoritma penjadwalan Round Robin (RR) baseline
    pada sekumpulan ImageTask terhadap WorkerNode yang tersedia.

    Langkah-langkah:
    1. Validasi daftar worker dan task.
    2. Duplikasi data worker agar tidak memutasi input asli.
    3. Iterasi setiap task sesuai urutan indeks aslinya (0 <= i < N).
    4. Alokasikan task ke VM pada indeks k = (i mod M).
    5. Hitung estimasi start time (ready_time_ms saat ini) dan
       finish time (ready_time_ms + ET_i / capacity_multiplier).
    6. Perbarui akumulasi ready_time_ms pada VM terpilih.

    Args:
        tasks: Daftar ImageTask yang akan dijadwalkan (urutan input dipertahankan).
        workers: Daftar WorkerNode VM yang tersedia.

    Returns:
        Tuple berisi:
            - List[TaskAssignment]: Hasil alokasi setiap task ke VM.
            - List[WorkerNode]: Salinan daftar worker dengan ready_time_ms terbarui.

    Raises:
        ValueError: Jika daftar worker kosong atau capacity_multiplier <= 0.
    """
    if not workers:
        raise ValueError("Daftar worker tidak boleh kosong untuk penjadwalan Round Robin.")

    for w in workers:
        if w.capacity_multiplier <= 0:
            raise ValueError(
                f"Worker '{w.vm_id}' memiliki capacity_multiplier tidak valid "
                f"({w.capacity_multiplier}). Nilai harus > 0."
            )

    if not tasks:
        cloned_workers = [w.model_copy() for w in workers]
        return [], cloned_workers

    worker_pool = [w.model_copy() for w in workers]
    num_workers = len(worker_pool)
    assignments: List[TaskAssignment] = []

    for idx, task in enumerate(tasks):
        worker_idx = idx % num_workers
        chosen_worker = worker_pool[worker_idx]

        base_et = calculate_estimated_time(task)
        duration_on_worker = base_et / chosen_worker.capacity_multiplier

        start_time_ms = round(chosen_worker.ready_time_ms, 3)
        finish_time_ms = round(start_time_ms + duration_on_worker, 3)

        # Perbarui waktu siap VM
        chosen_worker.ready_time_ms = finish_time_ms

        assignments.append(
            TaskAssignment(
                task_id=task.task_id,
                assigned_vm_id=chosen_worker.vm_id,
                estimated_start_time_ms=start_time_ms,
                estimated_finish_time_ms=finish_time_ms,
            )
        )

    return assignments, worker_pool
