# env_config.py
# Berkas konfigurasi pemetaan IP VM Azure untuk Peran 2 (Scheduler) dan Peran 4 (Benchmark Runner)

WORKER_NODES = [
    {
        "vm_id": "vm-worker-1",
        "host_id": "subnet-host-a",
        "public_ip": "98.70.42.52",
        "private_ip": "10.0.1.4",  # Atau gunakan Public IP jika diakses dari luar VNet
        "url": "http://98.70.42.52:8000",
        "capacity_multiplier": 2.0,
        "total_cost_per_sec": 0.0000116  # Tarif Standard_B2s (USD/detik)
    },
    {
        "vm_id": "vm-worker-2",
        "host_id": "subnet-host-a",
        "public_ip": "135.235.195.95",
        "private_ip": "10.0.1.5",
        "url": "http://135.235.195.95:8000",
        "capacity_multiplier": 1.0,
        "total_cost_per_sec": 0.0000058  # Tarif Standard_B1s (USD/detik)
    },
    {
        "vm_id": "vm-worker-3",
        "host_id": "subnet-host-b",
        "public_ip": "70.153.24.61",
        "private_ip": "10.0.2.4",
        "url": "http://70.153.24.61:8000",
        "capacity_multiplier": 1.5,
        "total_cost_per_sec": 0.0000116  # Tarif Standard_B2s (USD/detik)
    },
    {
        "vm_id": "vm-worker-4",
        "host_id": "subnet-host-b",
        "public_ip": "70.153.24.25",
        "private_ip": "10.0.2.5",
        "url": "http://70.153.24.25:8000",
        "capacity_multiplier": 0.8,
        "total_cost_per_sec": 0.0000058  # Tarif Standard_B1s (USD/detik)
    }
]

MASTER_DISPATCHER_IP = "20.244.12.15"
MASTER_DISPATCHER_URL = "http://20.244.12.15:8000"
REST_PORT = 8000
