"""
lpt_logic.py
============
Implementasi Algoritma Penjadwalan Longest Processing Time (LPT)
untuk Lingkungan Cloud Computing Heterogen.

Peran: Anggota 2 (Core Algorithm & Scheduler Developer)
Referensi: Proposal Teknis - Bagian 3 (Peran 2) & Bagian 4.1 (Metodologi LPT)

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

    Formula:
        ET_i = (width_px * height_px) / 10000

    Jika task sudah memiliki estimated_processing_time_ms > 0, nilai tersebut
    digunakan. Jika belum atau bernilai 0, dihitung langsung dari dimensi piksel.

    Args:
        task: Objek ImageTask.

    Returns:
        Estimasi waktu pemrosesan dalam milidetik (ms).
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
    pada kumpulan task gambar terhadap VM worker yang heterogen.

    Langkah-langkah:
    1. Validasi input worker dan task.
    2. Duplikasi data worker agar tidak memutasi state eksternal secara tidak sengaja.
    3. Urutkan daftar task secara descending berdasarkan ET_i (Longest Task First).
    4. Untuk setiap task, evaluasi waktu penyelesaian (completion time)
       pada masing-masing worker:
           completion_time = ready_time_ms + (ET_i / capacity_multiplier)
       Pilih worker dengan waktu penyelesaian paling minimum (earliest finish time).
       Jika terdapat nilai completion time yang sama (tie-breaking), pilih VM
       dengan capacity_multiplier lebih tinggi (worker lebih cepat).
    5. Catat start time dan finish time pada TaskAssignment.
    6. Perbarui akumulasi ready_time_ms worker terpilih.

    Args:
        tasks: Daftar ImageTask yang akan dijadwalkan.
        workers: Daftar WorkerNode (VM Azure dengan capacity_multiplier heterogen).

    Returns:
        Tuple berisi:
            - List[TaskAssignment]: Hasil alokasi setiap task ke VM.
            - List[WorkerNode]: Salinan daftar worker dengan ready_time_ms terbarui.

    Raises:
        ValueError: Jika daftar worker kosong atau capacity_multiplier <= 0.
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

        # Cari worker yang menghasilkan completion time paling awal:
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
