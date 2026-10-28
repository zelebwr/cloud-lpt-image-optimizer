"""
lpt_logic.py
============
Implementasi Algoritma Penjadwalan Longest Processing Time (LPT)
untuk Lingkungan Cloud Heterogen di Microsoft Azure.

Peran: Anggota 2 (Core Algorithm & Scheduler Developer)
Referensi: Azure Project Planning.pdf - Bagian 3 (Peran 2) & Bagian 4 (Logika Pengurutan & Alokasi LPT)

Prinsip Algoritma LPT:
----------------------
1. Estimasi waktu eksekusi task gambar:
       ET_i = (width_px * height_px) / 10000
2. Urutkan seluruh task secara menurun (descending):
       ET_1 >= ET_2 >= ... >= ET_N
3. Untuk setiap task T_i, alokasikan ke VM R_k yang meminimalkan waktu selesai:
       R_k = argmin_{1 <= j <= M} ( RT_j + ET_i / capacity_multiplier_j )
4. Perbarui waktu siap VM terpilih:
       RT_k <- RT_k + ET_i / capacity_multiplier_k
"""

from typing import List, Tuple
from schema import ImageTask, WorkerNode, TaskAssignment


def calculate_estimated_time(task: ImageTask) -> float:
    """
    Menghitung atau memvalidasi estimasi waktu pemrosesan task gambar (ET_i).
    Formula: ET_i = (width_px * height_px) / 10000
    """
    if task.estimated_processing_time_ms and task.estimated_processing_time_ms > 0:
        return float(task.estimated_processing_time_ms)
    return float((task.width_px * task.height_px) / 10000.0)


def run_lpt(
    tasks: List[ImageTask],
    workers: List[WorkerNode],
) -> Tuple[List[TaskAssignment], List[WorkerNode]]:
    """
    Mengeksekusi algoritma penjadwalan Longest Processing Time (LPT)
    pada kumpulan task gambar terhadap VM worker heterogen di Azure.
    """
    if not workers:
        raise ValueError("Daftar worker tidak boleh kosong untuk penjadwalan LPT.")

    for w in workers:
        if w.capacity_multiplier <= 0:
            raise ValueError(
                f"Worker '{w.vm_id}' memiliki capacity_multiplier tidak valid "
                f"({w.capacity_multiplier}). Nilai harus > 0."
            )

    if not tasks:
        cloned_workers = [w.model_copy() for w in workers]
        return [], cloned_workers

    # Duplikasi worker agar state aman dan siap dilacak
    worker_pool = [w.model_copy() for w in workers]

    # Urutkan task secara descending berdasarkan estimasi waktu (Longest first)
    sorted_tasks = sorted(
        tasks,
        key=lambda t: (calculate_estimated_time(t), t.task_id),
        reverse=True,
    )

    assignments: List[TaskAssignment] = []

    for task in sorted_tasks:
        base_et = calculate_estimated_time(task)

        # Evaluasi waktu penyelesaian (completion time) pada masing-masing worker:
        # completion_time = ready_time_ms + (base_et / capacity_multiplier)
        best_worker_idx = -1
        min_finish_time = float("inf")
        best_multiplier = -1.0

        for idx, worker in enumerate(worker_pool):
            duration_on_worker = base_et / worker.capacity_multiplier
            potential_finish = worker.ready_time_ms + duration_on_worker

            if (potential_finish < min_finish_time - 1e-9) or (
                abs(potential_finish - min_finish_time) <= 1e-9
                and worker.capacity_multiplier > best_multiplier
            ):
                min_finish_time = potential_finish
                best_worker_idx = idx
                best_multiplier = worker.capacity_multiplier

        chosen_worker = worker_pool[best_worker_idx]
        start_time_ms = round(chosen_worker.ready_time_ms, 3)
        finish_time_ms = round(min_finish_time, 3)

        # Perbarui akumulasi ready_time worker
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
