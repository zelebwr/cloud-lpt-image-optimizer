"""
test_scheduler.py
=================
Unit test suite untuk memvalidasi deliverable Peran 2:
- lpt_logic.py
- rr_logic.py
- scheduler_engine.py
"""

from schema import ImageTask, WorkerNode, TaskAssignment
from lpt_logic import run_lpt, calculate_estimated_time
from rr_logic import run_round_robin
from scheduler_engine import SchedulerEngine, DEFAULT_AZURE_WORKERS


def sample_workers():
    return [
        WorkerNode(
            vm_id="vm-worker-1",
            host_id="host-a",
            capacity_multiplier=2.0,
            ready_time_ms=0.0,
            total_cost_per_sec=0.004,
        ),
        WorkerNode(
            vm_id="vm-worker-2",
            host_id="host-a",
            capacity_multiplier=1.0,
            ready_time_ms=0.0,
            total_cost_per_sec=0.002,
        ),
        WorkerNode(
            vm_id="vm-worker-3",
            host_id="host-b",
            capacity_multiplier=1.5,
            ready_time_ms=0.0,
            total_cost_per_sec=0.003,
        ),
        WorkerNode(
            vm_id="vm-worker-4",
            host_id="host-b",
            capacity_multiplier=0.8,
            ready_time_ms=0.0,
            total_cost_per_sec=0.0016,
        ),
    ]


def sample_tasks():
    return [
        ImageTask(
            task_id="TASK-001",
            file_path="raw_images/small.jpg",
            width_px=640,
            height_px=480,
            file_size_bytes=20000,
            estimated_processing_time_ms=30.72,
        ),
        ImageTask(
            task_id="TASK-002",
            file_path="raw_images/large.jpg",
            width_px=1920,
            height_px=1080,
            file_size_bytes=150000,
            estimated_processing_time_ms=207.36,
        ),
        ImageTask(
            task_id="TASK-003",
            file_path="raw_images/medium.jpg",
            width_px=1280,
            height_px=720,
            file_size_bytes=80000,
            estimated_processing_time_ms=92.16,
        ),
        ImageTask(
            task_id="TASK-004",
            file_path="raw_images/tiny.jpg",
            width_px=800,
            height_px=600,
            file_size_bytes=35000,
            estimated_processing_time_ms=48.0,
        ),
    ]


def test_calculate_estimated_time():
    task = ImageTask(
        task_id="T1",
        file_path="dummy.jpg",
        width_px=1000,
        height_px=1000,
        file_size_bytes=1000,
        estimated_processing_time_ms=0.0,
    )
    assert calculate_estimated_time(task) == 100.0

    task.estimated_processing_time_ms = 45.5
    assert calculate_estimated_time(task) == 45.5


def test_lpt_sorting_and_allocation():
    workers = sample_workers()
    tasks = sample_tasks()

    assignments, updated_workers = run_lpt(tasks, workers)

    assert len(assignments) == len(tasks)
    assert assignments[0].task_id == "TASK-002"
    assert assignments[0].assigned_vm_id == "vm-worker-1"
    assert assignments[0].estimated_start_time_ms == 0.0
    assert abs(assignments[0].estimated_finish_time_ms - 103.68) < 0.01

    assert assignments[1].task_id == "TASK-003"
    assert assignments[1].assigned_vm_id == "vm-worker-3"


def test_round_robin_allocation():
    workers = sample_workers()
    tasks = sample_tasks()

    assignments, updated_workers = run_round_robin(tasks, workers)

    assert len(assignments) == 4
    assert assignments[0].task_id == "TASK-001"
    assert assignments[0].assigned_vm_id == "vm-worker-1"

    assert assignments[1].task_id == "TASK-002"
    assert assignments[1].assigned_vm_id == "vm-worker-2"

    assert assignments[2].task_id == "TASK-003"
    assert assignments[2].assigned_vm_id == "vm-worker-3"

    assert assignments[3].task_id == "TASK-004"
    assert assignments[3].assigned_vm_id == "vm-worker-4"


def test_scheduler_engine_integration():
    engine = SchedulerEngine()
    tasks = sample_tasks()

    # Test LPT
    lpt_assignments, lpt_dur, lpt_makespan, algo_name = engine.schedule(tasks, "lpt")
    assert algo_name == "LPT"
    assert len(lpt_assignments) == 4
    assert lpt_dur >= 0.0
    assert lpt_makespan > 0.0

    # Test Round Robin
    rr_assignments, rr_dur, rr_makespan, algo_name = engine.schedule(tasks, "rr")
    assert algo_name == "RoundRobin"
    assert len(rr_assignments) == 4
    assert rr_dur >= 0.0
    assert rr_makespan > 0.0


def test_empty_tasks():
    engine = SchedulerEngine()
    assignments, dur, makespan, _ = engine.schedule([], "lpt")
    assert assignments == []
    assert makespan == 0.0


def test_invalid_worker_capacity():
    bad_workers = [
        WorkerNode(
            vm_id="vm-bad",
            host_id="host-x",
            capacity_multiplier=0.0,
            total_cost_per_sec=0.001,
        )
    ]
    engine = SchedulerEngine(workers=bad_workers)
    try:
        engine.schedule(sample_tasks(), "lpt")
        assert False, "Should raise ValueError for non-positive multiplier"
    except ValueError:
        pass


def test_fastapi_endpoints():
    from fastapi.testclient import TestClient
    from scheduler_engine import app

    client = TestClient(app)

    # 1. Test Root / Health
    resp = client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ONLINE"
    assert len(data["workers"]) == 4

    # 2. Test Get Workers
    resp = client.get("/workers")
    assert resp.status_code == 200
    assert len(resp.json()["workers"]) == 4

    # 3. Test POST /schedule with LPT
    payload_tasks = [t.model_dump() for t in sample_tasks()]
    resp = client.post("/schedule", json={"algorithm": "lpt", "tasks": payload_tasks})
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["algorithm"] == "LPT"
    assert len(res_data["assignments"]) == 4
    assert "scheduling_duration_ms" in res_data
    assert res_data["scheduling_duration_ms"] >= 0.0

    # 4. Test POST /schedule with RR
    resp = client.post("/schedule", json={"algorithm": "rr", "tasks": payload_tasks})
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["algorithm"] == "RoundRobin"
    assert len(res_data["assignments"]) == 4

    # 5. Test POST /schedule with invalid algorithm
    resp = client.post("/schedule", json={"algorithm": "unknown_algo", "tasks": payload_tasks})
    assert resp.status_code == 400

    # 6. Test POST /workers/reset
    resp = client.post("/workers/reset")
    assert resp.status_code == 200


if __name__ == "__main__":
    test_calculate_estimated_time()
    test_lpt_sorting_and_allocation()
    test_round_robin_allocation()
    test_scheduler_engine_integration()
    test_empty_tasks()
    test_invalid_worker_capacity()
    test_fastapi_endpoints()
    print("All unit and API integration tests passed successfully!")
