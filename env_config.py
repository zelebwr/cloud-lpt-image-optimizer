# env_config.py
# Berkas konfigurasi jaringan & spesifikasi VM Worker untuk Peran 2 dan Peran 4

WORKER_NODES = [
    {
        "vm_id": "vm-worker-1",
        "host_id": "host-a",
        "url": "http://vm-worker-1:8000",
        "capacity_multiplier": 2.0,
        "total_cost_per_sec": 0.0000116
    },
    {
        "vm_id": "vm-worker-2",
        "host_id": "host-a",
        "url": "http://vm-worker-2:8000",
        "capacity_multiplier": 1.0,
        "total_cost_per_sec": 0.0000058
    },
    {
        "vm_id": "vm-worker-3",
        "host_id": "host-b",
        "url": "http://vm-worker-3:8000",
        "capacity_multiplier": 1.5,
        "total_cost_per_sec": 0.0000116
    },
    {
        "vm_id": "vm-worker-4",
        "host_id": "host-b",
        "url": "http://vm-worker-4:8000",
        "capacity_multiplier": 0.8,
        "total_cost_per_sec": 0.0000058
    }
]

MASTER_DISPATCHER_URL = "http://master-dispatcher:8000"
REST_PORT = 8000
