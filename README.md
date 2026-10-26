# Cloud LPT Image Optimizer

Simulasi penjadwalan task pada Cloud Computing menggunakan algoritma
**Longest Processing Time (LPT)** dan **Round Robin (RR)** dengan studi kasus
pemrosesan gambar terdistribusi di lingkungan Docker (simulasi Microsoft Azure).

---

## Bagian: Workload Generator & QA Test Orchestrator (Anggota 4)

Repositori ini berisi komponen:

| File | Peran |
|------|-------|
| `dataset_generator.py` | Membuat dataset gambar sintetis sebagai workload pengujian |
| `benchmark_runner.py` | Mengorkestrasi eksekusi benchmark LPT vs Round Robin via REST API |
| `schema.py` | Definisi model data bersama (shared contract) seluruh anggota tim |
| `requirements.txt` | Dependensi Python |

---

## Struktur Proyek

```
cloud-lpt-image-optimizer/
├── dataset_generator.py     # Generator dataset sintetis
├── benchmark_runner.py      # QA Test Orchestrator
├── schema.py                # Shared Pydantic models
├── requirements.txt         # Dependensi Python
│
├── data/                    # Output dataset (dibuat otomatis)
│   ├── raw_images/          # Gambar sintetis JPEG (di-ignore git)
│   │   ├── image_001.jpg
│   │   └── ...
│   ├── metadata.csv         # Metadata seluruh gambar
│   └── metadata.json        # Metadata dalam format JSON
│
└── results/                 # Output benchmark (dibuat otomatis)
    ├── execution_log_lpt_<timestamp>.csv
    ├── execution_log_rr_<timestamp>.csv
    └── benchmark_summary_<timestamp>.csv
```

---

## Prasyarat

- Python 3.11
- Docker & Docker Compose (untuk `benchmark_runner.py`)
- pip

---

## Instalasi

```powershell
pip install -r requirements.txt
```

---

## Langkah 1 — Generate Dataset

Jalankan `dataset_generator.py` untuk membuat gambar sintetis dan metadata.

### Perintah dasar

```powershell
python dataset_generator.py
```

### Generate 50 gambar (default, seed 42)

```powershell
python dataset_generator.py --count 50 --seed 42
```

### Generate 100 gambar

```powershell
python dataset_generator.py --count 100 --seed 42
```

### Lihat semua opsi

```powershell
python dataset_generator.py --help
```

### Opsi CLI dataset_generator

| Argumen | Default | Keterangan |
|---------|---------|------------|
| `--count N` | `50` | Jumlah gambar yang akan dibuat |
| `--seed S` | `42` | Seed random — seed sama = dataset identik |
| `--output DIR` | `data` | Direktori output dataset |

### Kategori Workload

| Kategori | Resolusi | Est. Time |
|----------|----------|-----------|
| `small` | 640×480 s/d 800×600 | ~31–48 ms |
| `medium` | 1024×600 s/d 1280×720 | ~61–92 ms |
| `large` | 1366×768 s/d 1920×1080 | ~105–207 ms |

> **Catatan:** `estimated_processing_time_ms = (width × height) / 10000`
> Nilai ini **estimasi sintetis** untuk input penjadwalan, bukan waktu aktual.

---

## Langkah 2 — Jalankan Benchmark

`benchmark_runner.py` mengorkestrasi pengujian end-to-end melalui REST API.

### Prasyarat sebelum menjalankan

```powershell
# 1. Pastikan dataset sudah di-generate (Langkah 1)
# 2. Jalankan seluruh container Docker (Anggota 1)
docker-compose up -d
```

### Jalankan benchmark (LPT + Round Robin sekaligus)

```powershell
python benchmark_runner.py
```

### Jalankan hanya satu algoritma

```powershell
python benchmark_runner.py --algorithms lpt
python benchmark_runner.py --algorithms rr
```

### Dengan konfigurasi kustom

```powershell
python benchmark_runner.py --master http://localhost:8000 --dataset data --algorithms lpt rr
```

### Opsi CLI benchmark_runner

| Argumen | Default | Keterangan |
|---------|---------|------------|
| `--master URL` | `http://localhost:8000` | URL Master Node dispatcher |
| `--dataset DIR` | `data` | Direktori dataset (berisi metadata.json) |
| `--output DIR` | `data/processed_images` | Direktori gambar hasil pemrosesan |
| `--results DIR` | `results` | Direktori log dan metrik CSV |
| `--algorithms` | `lpt rr` | Algoritma yang diuji: `lpt`, `rr`, atau keduanya |

### Alur kerja benchmark_runner

```
metadata.json
     │
     ▼
POST /schedule (Master Node)    ← Anggota 2 mengimplementasikan
     │
     ▼ TaskAssignment list
     │
     ├──► POST /execute_task (vm-worker-1)  ← Anggota 3
     ├──► POST /execute_task (vm-worker-2)
     ├──► POST /execute_task (vm-worker-3)
     └──► POST /execute_task (vm-worker-4)
          │
          ▼
    Validasi output (Pillow)
          │
          ▼
    results/execution_log_<algo>_<timestamp>.csv
```

---

## Verifikasi Hasil Dataset

```powershell
# Hitung jumlah file gambar
(Get-ChildItem data\raw_images\*.jpg).Count

# Lihat metadata CSV
Get-Content data\metadata.csv

# Lihat metadata JSON
Get-Content data\metadata.json
```

### Contoh baris metadata.csv

```
task_id,file_name,file_path,width_px,height_px,file_size_bytes,workload_category,estimated_processing_time_ms
TASK-001,image_001.jpg,raw_images/image_001.jpg,1024,600,34292,medium,61
TASK-002,image_002.jpg,raw_images/image_002.jpg,640,480,18787,small,31
```

---

## Konfigurasi VM Worker

Port default yang digunakan `benchmark_runner.py` (harus sesuai `docker-compose.yml`):

| VM | Host | Multiplier | Port |
|----|------|-----------|------|
| `vm-worker-1` | Host A | 2.0x | 8001 |
| `vm-worker-2` | Host A | 1.0x | 8002 |
| `vm-worker-3` | Host B | 1.5x | 8003 |
| `vm-worker-4` | Host B | 0.8x | 8004 |

> Sesuaikan `DEFAULT_WORKER_URLS` di `benchmark_runner.py` jika port berbeda dengan `docker-compose.yml` milik Anggota 1.

---

## Hal Penting untuk Anggota Lain

- **Anggota 2 (Scheduler):** Endpoint `/schedule` harus menerima `{"algorithm": "lpt"|"rr", "tasks": [...]}` dan mengembalikan `{"assignments": [...], "scheduling_duration_ms": float}`.
- **Anggota 3 (Worker):** Endpoint `/execute_task` harus menerima `{"task_id", "input_file_path", "output_file_path", "target_scale", "quality"}`.
- **Anggota 5 (Metrics):** Gunakan `data/metadata.json` dan log CSV dari `results/` sebagai input `metrics_collector.py`.
- **Semua:** Import model dari `schema.py` — jangan mendefinisikan ulang `ImageTask`, `WorkerNode`, `TaskAssignment`, atau `BenchmarkMetrics` di file lain.
