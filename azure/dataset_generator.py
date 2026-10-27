# dataset_generator.py
# Peran 4: Workload Generator & QA Test Orchestrator
# Fungsi: membuat gambar sintetis JPEG + metadata CSV/JSON sebagai workload benchmark.

# ── Impor stdlib ──────────────────────────────────────────────────────────────
import argparse
import csv
import json
import os
import random
import sys

# ── Impor library eksternal ──────────────────────────────────────────────────
import numpy as np
from PIL import Image

# ──────────────────────────────────────────────────────────────────────────────
# KONSTANTA
# ──────────────────────────────────────────────────────────────────────────────

# Tiga kategori workload: (nama, (min_w, max_w, min_h, max_h))
WORKLOAD_CATEGORIES = {
    "small":  (640,  800,  480, 600),
    "medium": (1024, 1280, 600, 720),
    "large":  (1366, 1920, 768, 1080),
}

# Kualitas JPEG saat menyimpan gambar
JPEG_QUALITY = 85


# ──────────────────────────────────────────────────────────────────────────────
# FUNGSI UTAMA
# ──────────────────────────────────────────────────────────────────────────────

def parse_args():
    """Parsing argumen CLI."""
    parser = argparse.ArgumentParser(
        description="Generator dataset gambar sintetis untuk benchmark LPT vs Round Robin."
    )
    parser.add_argument("--count",  type=int, default=50,   help="Jumlah gambar (default: 50)")
    parser.add_argument("--seed",   type=int, default=42,   help="Seed random (default: 42)")
    parser.add_argument("--output", type=str, default="data", help="Direktori output (default: data)")
    return parser.parse_args()


def pilih_dimensi(kategori: str, rng: random.Random) -> tuple[int, int]:
    """
    Pilih dimensi gambar secara acak dalam rentang kategori yang dipilih.
    Mengembalikan (width, height).
    """
    min_w, max_w, min_h, max_h = WORKLOAD_CATEGORIES[kategori]
    width  = rng.randint(min_w, max_w)
    height = rng.randint(min_h, max_h)
    return width, height


def buat_gambar_sintetis(width: int, height: int, rng: random.Random) -> Image.Image:
    """
    Buat gambar RGB berisi noise warna acak dengan Pillow + NumPy.
    Gambar diisi noise agar ukuran file JPEG realistis (bukan solid color).
    """
    # Buat seed numpy dari seed random Python agar konsisten
    np_seed = rng.randint(0, 2**31 - 1)
    np_rng = np.random.default_rng(np_seed)

    # Array noise acak: shape (height, width, 3) berisi nilai 0–255
    pixel_array = np_rng.integers(0, 256, (height, width, 3), dtype=np.uint8)

    # Buat gambar dari array numpy
    img = Image.fromarray(pixel_array, mode="RGB")
    return img


def hitung_estimated_ms(width: int, height: int) -> float:
    """
    Hitung estimasi waktu proses berdasarkan jumlah piksel.
    Formula: (width * height) / 10000
    """
    return round((width * height) / 10000, 4)


def generate_dataset(count: int, seed: int, output_dir: str) -> None:
    """
    Fungsi utama: generate `count` gambar sintetis, simpan ke disk,
    dan tulis metadata.csv + metadata.json.
    """
    # ── 1. Persiapan direktori output ──────────────────────────────────────
    raw_images_dir = os.path.join(output_dir, "raw_images")
    os.makedirs(raw_images_dir, exist_ok=True)

    # ── 2. Inisialisasi RNG dengan seed ────────────────────────────────────
    rng = random.Random(seed)

    # ── 3. Daftar kategori untuk distribusi acak ────────────────────────────
    kategori_list = list(WORKLOAD_CATEGORIES.keys())

    # ── 4. Kontainer metadata ───────────────────────────────────────────────
    metadata_rows = []
    count_per_kategori = {"small": 0, "medium": 0, "large": 0}

    print(f"[INFO] Generating {count} gambar sintetis ke '{output_dir}/' (seed={seed})...")

    for i in range(1, count + 1):
        # ── 4a. Pilih kategori acak ─────────────────────────────────────────
        kategori = rng.choice(kategori_list)

        # ── 4b. Tentukan dimensi ────────────────────────────────────────────
        width, height = pilih_dimensi(kategori, rng)

        # ── 4c. Buat gambar sintetis ────────────────────────────────────────
        img = buat_gambar_sintetis(width, height, rng)

        # ── 4d. Simpan sebagai JPEG ─────────────────────────────────────────
        file_name = f"image_{i:03d}.jpg"
        file_path_abs = os.path.join(raw_images_dir, file_name)
        img.save(file_path_abs, format="JPEG", quality=JPEG_QUALITY)

        # ── 4e. Ambil ukuran file aktual setelah disimpan ───────────────────
        file_size_bytes = os.path.getsize(file_path_abs)

        # ── 4f. Hitung estimasi waktu proses ────────────────────────────────
        estimated_ms = hitung_estimated_ms(width, height)

        # ── 4g. Path relatif untuk metadata ────────────────────────────────
        file_path_rel = f"raw_images/{file_name}"

        # ── 4h. Simpan baris metadata ────────────────────────────────────────
        task_id = f"TASK-{i:03d}"
        row = {
            "task_id":                    task_id,
            "file_name":                  file_name,
            "file_path":                  file_path_rel,
            "width_px":                   width,
            "height_px":                  height,
            "file_size_bytes":            file_size_bytes,
            "workload_category":          kategori,
            "estimated_processing_time_ms": estimated_ms,
        }
        metadata_rows.append(row)
        count_per_kategori[kategori] += 1

        # ── 4i. Progress setiap 10 gambar ────────────────────────────────────
        if i % 10 == 0 or i == count:
            print(f"  [{i:>3}/{count}] {file_name} | {kategori:6s} | {width}x{height} | {file_size_bytes:,} bytes")

    # ── 5. Tulis metadata.csv ──────────────────────────────────────────────
    csv_path = os.path.join(output_dir, "metadata.csv")
    fieldnames = [
        "task_id", "file_name", "file_path",
        "width_px", "height_px", "file_size_bytes",
        "workload_category", "estimated_processing_time_ms"
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(metadata_rows)
    print(f"\n[OK] Metadata CSV  -> {csv_path}")

    # ── 6. Tulis metadata.json ─────────────────────────────────────────────
    json_path = os.path.join(output_dir, "metadata.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(metadata_rows, f, indent=2, ensure_ascii=False)
    print(f"[OK] Metadata JSON -> {json_path}")

    # ── 7. Cetak ringkasan ─────────────────────────────────────────────────
    print("\n" + "=" * 50)
    print("RINGKASAN DATASET")
    print("=" * 50)
    print(f"  Total gambar : {count}")
    for kat, jumlah in count_per_kategori.items():
        print(f"  {kat:8s}     : {jumlah} gambar")
    print(f"  Output dir   : {os.path.abspath(output_dir)}")
    print("=" * 50)


# ──────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    args = parse_args()
    generate_dataset(
        count=args.count,
        seed=args.seed,
        output_dir=args.output,
    )
