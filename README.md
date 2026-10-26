# Cloud LPT Image Optimizer

Simulasi penjadwalan task pada Cloud Computing menggunakan algoritma **Longest Processing Time (LPT)** dan **Round Robin** dengan studi kasus pemrosesan gambar di Microsoft Azure.

---

## Bagian: Workload Generator & QA Test Orchestrator

Repositori ini berisi komponen **dataset generator** yang bertugas menghasilkan workload berupa gambar sintetis beserta metadata untuk digunakan sebagai input pengujian algoritma penjadwalan.

---

## Struktur Proyek

```
cloud-lpt-image-optimizer/
├── dataset_generator.py   # Generator dataset sintetis
├── requirements.txt       # Dependensi Python
└── dataset/               # Hasil output (dibuat otomatis)
    ├── images/
    │   ├── image_001.jpg
    │   ├── image_002.jpg
    │   └── ...
    ├── metadata.csv
    └── metadata.json
```

---

## Prasyarat

- Python 3.11
- pip

---

## Instalasi

```powershell
pip install -r requirements.txt
```

---

## Cara Menjalankan

### Generate 50 gambar (default)

```powershell
python dataset_generator.py
```

### Generate 50 gambar dengan seed tertentu

```powershell
python dataset_generator.py --count 50 --seed 42
```

### Generate 100 gambar

```powershell
python dataset_generator.py --count 100 --seed 42
```

### Simpan ke folder custom

```powershell
python dataset_generator.py --count 100 --seed 42 --output dataset
```

### Lihat semua opsi

```powershell
python dataset_generator.py --help
```

---

## Opsi CLI

| Argumen | Default | Keterangan |
|---------|---------|------------|
| `--count N` | `50` | Jumlah gambar yang akan dibuat |
| `--seed S` | `42` | Seed random untuk hasil yang dapat direproduksi |
| `--output DIR` | `dataset` | Direktori output dataset |

---

## Kategori Workload

| Kategori | Resolusi | Est. Time |
|----------|----------|-----------|
| `small` | 640×480 s/d 800×600 | ~31–48 ms |
| `medium` | 1024×600 s/d 1280×720 | ~61–92 ms |
| `large` | 1366×768 s/d 1920×1080 | ~105–207 ms |

> **Catatan:** `estimated_processing_time_ms` adalah nilai sintetis berbasis jumlah piksel `(w × h) / 10000`. Nilai ini digunakan sebagai bobot input algoritma penjadwalan, **bukan** waktu pemrosesan aktual.

---

## Verifikasi Hasil

```powershell
# Hitung jumlah file gambar
(Get-ChildItem dataset\images\*.jpg).Count

# Lihat isi metadata CSV
Get-Content dataset\metadata.csv

# Lihat metadata JSON
Get-Content dataset\metadata.json
```

---

## Contoh Output metadata.csv

```
task_id,file_name,file_path,width_px,height_px,file_size_bytes,workload_category,estimated_processing_time_ms
TASK-001,image_001.jpg,images/image_001.jpg,1024,600,34292,medium,61
TASK-002,image_002.jpg,images/image_002.jpg,640,480,18787,small,31
```
