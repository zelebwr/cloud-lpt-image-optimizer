"""
dataset_generator.py
====================
Pembuat dataset sintetis untuk pengujian algoritma penjadwalan task
(LPT dan Round Robin) pada simulasi Cloud Computing.

Menghasilkan gambar JPEG sintetis dengan berbagai resolusi beserta
metadata dalam format CSV dan JSON.

Penggunaan:
    python dataset_generator.py --count 50 --seed 42
    python dataset_generator.py --count 100 --seed 42 --output dataset

Catatan:
    Program ini hanya membuat dataset lokal.
    Tidak terhubung ke Azure atau layanan cloud manapun.
    Implementasi algoritma LPT/Round Robin dilakukan oleh anggota lain.
"""

import argparse
import csv
import json
import logging
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw

# ──────────────────────────────────────────────────────────────────────────────
# KONFIGURASI LOGGING
# ──────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# DEFINISI KATEGORI WORKLOAD
# ──────────────────────────────────────────────────────────────────────────────

# Setiap kategori berisi daftar resolusi (lebar, tinggi) yang valid.
# Resolusi dipilih secara acak dari daftar ini saat membuat gambar.
WORKLOAD_CATEGORIES = {
    "small": [
        (640, 480),
        (720, 480),
        (768, 576),
        (800, 480),
        (800, 600),
    ],
    "medium": [
        (1024, 600),
        (1024, 768),
        (1152, 648),
        (1280, 600),
        (1280, 720),
    ],
    "large": [
        (1366, 768),
        (1440, 900),
        (1600, 900),
        (1920, 800),
        (1920, 1080),
    ],
}

# Bobot probabilitas untuk setiap kategori.
# Angka ini menentukan seberapa sering setiap kategori muncul.
# Rasio 40:35:25 membuat distribusi workload cukup bervariasi.
CATEGORY_WEIGHTS = {
    "small": 40,
    "medium": 35,
    "large": 25,
}

# Rentang kualitas JPEG per kategori.
# Kualitas yang lebih rendah menghasilkan file lebih kecil.
JPEG_QUALITY_RANGE = {
    "small": (70, 88),
    "medium": (72, 90),
    "large": (75, 92),
}

# Header kolom CSV
CSV_HEADER = [
    "task_id",
    "file_name",
    "file_path",
    "width_px",
    "height_px",
    "file_size_bytes",
    "workload_category",
    "estimated_processing_time_ms",
]


# ──────────────────────────────────────────────────────────────────────────────
# FUNGSI PEMBANTU
# ──────────────────────────────────────────────────────────────────────────────


def hitung_estimasi_waktu(width: int, height: int) -> int:
    """
    Menghitung estimasi waktu pemrosesan dalam milidetik.

    Rumus: (lebar * tinggi) / 10000, dibulatkan ke integer positif.

    CATATAN PENTING:
        Nilai ini adalah ESTIMASI SINTETIS yang dibuat berdasarkan jumlah
        piksel, semata-mata untuk keperluan penjadwalan task (input algoritma
        LPT/Round Robin). Nilai ini BUKAN waktu pemrosesan aktual dan tidak
        boleh digunakan sebagai pengganti hasil pengukuran benchmark nyata.

    Args:
        width: Lebar gambar dalam piksel.
        height: Tinggi gambar dalam piksel.

    Returns:
        Estimasi waktu pemrosesan dalam milidetik (integer positif).
    """
    estimasi = (width * height) / 10_000
    return max(1, round(estimasi))


def pilih_resolusi_dan_kategori(rng: random.Random) -> tuple:
    """
    Memilih kategori workload dan resolusi secara acak berdasarkan bobot.

    Args:
        rng: Instance random.Random dengan seed tetap.

    Returns:
        Tuple berisi (kategori, lebar, tinggi).
    """
    kategori_list = list(CATEGORY_WEIGHTS.keys())
    bobot_list = [CATEGORY_WEIGHTS[k] for k in kategori_list]

    # Pilih kategori sesuai bobot probabilitas
    kategori = rng.choices(kategori_list, weights=bobot_list, k=1)[0]

    # Pilih resolusi secara acak dari daftar resolusi kategori tersebut
    width, height = rng.choice(WORKLOAD_CATEGORIES[kategori])

    return kategori, width, height


def buat_pola_visual(rng: random.Random, width: int, height: int) -> Image.Image:
    """
    Membuat gambar sintetis dengan pola visual yang bervariasi menggunakan Pillow.

    Setiap gambar memiliki latar belakang berwarna acak dan beberapa
    bentuk geometris (persegi panjang, elips, garis) dengan warna acak.
    Pola ini memastikan setiap gambar memiliki konten berbeda.

    Args:
        rng: Instance random.Random dengan seed tetap.
        width: Lebar gambar dalam piksel.
        height: Tinggi gambar dalam piksel.

    Returns:
        Objek Image Pillow mode RGB.
    """
    # Buat warna latar belakang acak (menghindari warna terlalu gelap agar terlihat)
    warna_bg = (
        rng.randint(30, 200),
        rng.randint(30, 200),
        rng.randint(30, 200),
    )
    gambar = Image.new("RGB", (width, height), color=warna_bg)
    draw = ImageDraw.Draw(gambar)

    # Tentukan jumlah bentuk yang akan digambar (proporsional terhadap ukuran)
    jumlah_bentuk = rng.randint(8, 20)

    for _ in range(jumlah_bentuk):
        # Pilih jenis bentuk secara acak
        jenis_bentuk = rng.choice(["rectangle", "ellipse", "line", "polygon"])

        # Pilih warna acak untuk bentuk ini
        warna_bentuk = (
            rng.randint(0, 255),
            rng.randint(0, 255),
            rng.randint(0, 255),
        )

        # Tentukan koordinat acak di dalam batas gambar
        x1 = rng.randint(0, width - 1)
        y1 = rng.randint(0, height - 1)
        x2 = rng.randint(x1, min(x1 + width // 2, width - 1))
        y2 = rng.randint(y1, min(y1 + height // 2, height - 1))

        if jenis_bentuk == "rectangle":
            draw.rectangle([x1, y1, x2, y2], fill=warna_bentuk)

        elif jenis_bentuk == "ellipse":
            draw.ellipse([x1, y1, x2, y2], fill=warna_bentuk)

        elif jenis_bentuk == "line":
            lebar_garis = rng.randint(1, max(2, width // 80))
            draw.line([x1, y1, x2, y2], fill=warna_bentuk, width=lebar_garis)

        elif jenis_bentuk == "polygon":
            # Buat poligon dengan 3-6 titik acak di dalam batas gambar
            jumlah_titik = rng.randint(3, 6)
            titik = [
                (rng.randint(0, width - 1), rng.randint(0, height - 1))
                for _ in range(jumlah_titik)
            ]
            draw.polygon(titik, fill=warna_bentuk)

    return gambar


def simpan_gambar(
    gambar: Image.Image,
    path_file: Path,
    kualitas_jpeg: int,
) -> int:
    """
    Menyimpan gambar ke disk dalam format JPEG.

    Args:
        gambar: Objek Image Pillow.
        path_file: Path lengkap file tujuan.
        kualitas_jpeg: Kualitas JPEG (1-95).

    Returns:
        Ukuran file aktual dalam byte setelah disimpan.

    Raises:
        IOError: Jika file gagal disimpan.
    """
    gambar.save(path_file, format="JPEG", quality=kualitas_jpeg, optimize=True)
    return path_file.stat().st_size


def validasi_gambar(path_file: Path) -> bool:
    """
    Memvalidasi bahwa file gambar dapat dibuka kembali menggunakan Pillow.

    Args:
        path_file: Path file gambar yang akan divalidasi.

    Returns:
        True jika file valid, False jika tidak bisa dibuka.
    """
    try:
        with Image.open(path_file) as img:
            img.verify()  # Verifikasi integritas file
        return True
    except Exception as e:
        logger.error(f"Validasi gagal untuk {path_file.name}: {e}")
        return False


# ──────────────────────────────────────────────────────────────────────────────
# FUNGSI UTAMA PEMBUATAN DATASET
# ──────────────────────────────────────────────────────────────────────────────


def buat_struktur_direktori(output_dir: Path) -> Path:
    """
    Membuat struktur direktori output yang diperlukan.

    Struktur yang dibuat:
        <output_dir>/
        +-images/
        +-metadata.csv  (dibuat kemudian)
        +-metadata.json (dibuat kemudian)

    Args:
        output_dir: Direktori root output dataset.

    Returns:
        Path direktori images/.

    Raises:
        OSError: Jika direktori gagal dibuat.
    """
    dir_images = output_dir / "images"
    dir_images.mkdir(parents=True, exist_ok=True)
    logger.info(f"Direktori output: {output_dir.resolve()}")
    return dir_images


def generate_dataset(
    jumlah_gambar: int,
    seed: int,
    output_dir: Path,
) -> list:
    """
    Fungsi utama untuk menghasilkan seluruh dataset.

    Alur kerja:
        1. Buat struktur direktori.
        2. Untuk setiap gambar: pilih resolusi, buat pola visual, simpan JPEG.
        3. Kumpulkan metadata setiap gambar.
        4. Validasi semua gambar yang dihasilkan.
        5. Simpan metadata ke CSV dan JSON.
        6. Tampilkan ringkasan.

    Args:
        jumlah_gambar: Jumlah gambar yang akan dibuat.
        seed: Seed untuk random number generator (agar dapat direproduksi).
        output_dir: Direktori root output dataset.

    Returns:
        List berisi dict metadata setiap gambar yang berhasil dibuat.
    """
    # Inisialisasi RNG dengan seed tetap untuk hasil yang dapat direproduksi
    rng = random.Random(seed)
    logger.info(f"Random seed: {seed}")
    logger.info(f"Jumlah gambar yang akan dibuat: {jumlah_gambar}")

    # Buat struktur direktori
    dir_images = buat_struktur_direktori(output_dir)

    semua_metadata = []
    gagal = []

    # ── Buat setiap gambar ────────────────────────────────────────────────────
    for i in range(1, jumlah_gambar + 1):
        nama_file = f"image_{i:03d}.jpg"
        path_file = dir_images / nama_file

        # Pilih kategori dan resolusi secara acak
        kategori, width, height = pilih_resolusi_dan_kategori(rng)

        # Pilih kualitas JPEG secara acak sesuai rentang kategori
        min_q, max_q = JPEG_QUALITY_RANGE[kategori]
        kualitas = rng.randint(min_q, max_q)

        try:
            # Buat gambar sintetis
            gambar = buat_pola_visual(rng, width, height)

            # Simpan ke disk dan dapatkan ukuran file aktual
            ukuran_bytes = simpan_gambar(gambar, path_file, kualitas)

            # Hitung estimasi waktu pemrosesan (nilai sintetis, bukan aktual)
            estimasi_ms = hitung_estimasi_waktu(width, height)

            # Path relatif menggunakan forward slash agar kompatibel lintas OS
            path_relatif = f"images/{nama_file}"

            metadata = {
                "task_id": f"TASK-{i:03d}",
                "file_name": nama_file,
                "file_path": path_relatif,
                "width_px": width,
                "height_px": height,
                "file_size_bytes": ukuran_bytes,
                "workload_category": kategori,
                "estimated_processing_time_ms": estimasi_ms,
            }
            semua_metadata.append(metadata)

            logger.info(
                f"[{i:3d}/{jumlah_gambar}] {nama_file} | "
                f"{width}x{height} | {kategori:6s} | "
                f"{ukuran_bytes:,} bytes | ~{estimasi_ms} ms"
            )

        except Exception as e:
            logger.error(f"Gagal membuat gambar {nama_file}: {e}")
            gagal.append(nama_file)

    # ── Validasi semua gambar yang berhasil dibuat ────────────────────────────
    logger.info("Memvalidasi gambar yang telah dibuat...")
    gambar_invalid = []
    for meta in semua_metadata:
        path_gambar = output_dir / meta["file_path"]
        if not validasi_gambar(path_gambar):
            gambar_invalid.append(meta["file_name"])

    if gambar_invalid:
        logger.warning(
            f"{len(gambar_invalid)} gambar tidak lolos validasi: {gambar_invalid}"
        )
    else:
        logger.info(f"Semua {len(semua_metadata)} gambar berhasil divalidasi.")

    # ── Simpan metadata ───────────────────────────────────────────────────────
    if semua_metadata:
        simpan_metadata_csv(semua_metadata, output_dir / "metadata.csv")
        simpan_metadata_json(semua_metadata, output_dir / "metadata.json")

    # ── Tampilkan ringkasan ───────────────────────────────────────────────────
    tampilkan_ringkasan(semua_metadata, output_dir, gagal)

    return semua_metadata


# ──────────────────────────────────────────────────────────────────────────────
# FUNGSI PENYIMPANAN METADATA
# ──────────────────────────────────────────────────────────────────────────────


def simpan_metadata_csv(metadata_list: list, path_csv: Path) -> None:
    """
    Menyimpan metadata ke file CSV.

    Menggunakan newline='' dan encoding UTF-8 agar kompatibel di Windows
    dan Linux tanpa masalah karakter CRLF atau encoding.

    Args:
        metadata_list: List dict berisi metadata setiap gambar.
        path_csv: Path file CSV tujuan.
    """
    try:
        with open(path_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADER)
            writer.writeheader()
            writer.writerows(metadata_list)
        logger.info(f"Metadata CSV disimpan: {path_csv}")
    except OSError as e:
        logger.error(f"Gagal menyimpan metadata CSV: {e}")
        raise


def simpan_metadata_json(metadata_list: list, path_json: Path) -> None:
    """
    Menyimpan metadata ke file JSON.

    Format: array JSON berisi objek metadata setiap gambar.
    Nilai dalam JSON dijamin konsisten dengan nilai di CSV.

    Args:
        metadata_list: List dict berisi metadata setiap gambar.
        path_json: Path file JSON tujuan.
    """
    try:
        with open(path_json, "w", encoding="utf-8") as f:
            json.dump(metadata_list, f, indent=2, ensure_ascii=False)
        logger.info(f"Metadata JSON disimpan: {path_json}")
    except OSError as e:
        logger.error(f"Gagal menyimpan metadata JSON: {e}")
        raise


# ──────────────────────────────────────────────────────────────────────────────
# FUNGSI RINGKASAN
# ──────────────────────────────────────────────────────────────────────────────


def tampilkan_ringkasan(
    metadata_list: list,
    output_dir: Path,
    gagal: list,
) -> None:
    """
    Menampilkan ringkasan hasil pembuatan dataset ke konsol.

    Informasi yang ditampilkan:
        - Jumlah gambar berhasil / gagal.
        - Jumlah gambar per kategori workload.
        - Estimasi waktu pemrosesan per kategori.
        - Total ukuran dataset.
        - Lokasi file metadata.

    Args:
        metadata_list: List dict metadata gambar yang berhasil.
        output_dir: Direktori root output dataset.
        gagal: List nama file yang gagal dibuat.
    """
    print("\n" + "=" * 60)
    print("  RINGKASAN DATASET")
    print("=" * 60)
    print(f"  Gambar berhasil dibuat : {len(metadata_list)}")
    print(f"  Gambar gagal           : {len(gagal)}")

    if metadata_list:
        # Hitung distribusi per kategori
        distribusi = {"small": [], "medium": [], "large": []}
        total_bytes = 0

        for meta in metadata_list:
            kat = meta["workload_category"]
            distribusi[kat].append(meta["estimated_processing_time_ms"])
            total_bytes += meta["file_size_bytes"]

        print("\n  Distribusi Kategori Workload:")
        print(f"  {'Kategori':<10} {'Jumlah':>7} {'Total Est. Time':>16}")
        print(f"  {'-'*10} {'-'*7} {'-'*16}")
        for kat in ["small", "medium", "large"]:
            jml = len(distribusi[kat])
            total_ms = sum(distribusi[kat])
            print(f"  {kat:<10} {jml:>7} {total_ms:>13,} ms")

        # Total ukuran dataset
        total_mb = total_bytes / (1024 * 1024)
        print(f"\n  Total ukuran dataset   : {total_bytes:,} bytes ({total_mb:.2f} MB)")

        # Lokasi file metadata
        print(f"\n  Lokasi output          : {output_dir.resolve()}")
        print(f"  metadata.csv           : {(output_dir / 'metadata.csv').resolve()}")
        print(f"  metadata.json          : {(output_dir / 'metadata.json').resolve()}")

    if gagal:
        print(f"\n  File yang gagal        : {', '.join(gagal)}")

    print("=" * 60)


# ──────────────────────────────────────────────────────────────────────────────
# COMMAND-LINE INTERFACE
# ──────────────────────────────────────────────────────────────────────────────


def parse_argumen() -> argparse.Namespace:
    """
    Mendefinisikan dan mem-parsing argumen command-line.

    Argumen yang tersedia:
        --count   : Jumlah gambar yang akan dibuat (default: 50).
        --seed    : Seed untuk random number generator (default: 42).
        --output  : Direktori output dataset (default: dataset).

    Returns:
        Namespace berisi nilai argumen yang telah di-parse.
    """
    parser = argparse.ArgumentParser(
        prog="dataset_generator.py",
        description=(
            "Generator dataset sintetis untuk pengujian algoritma "
            "penjadwalan LPT dan Round Robin pada simulasi Cloud Computing."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Contoh:\n"
            "  python dataset_generator.py\n"
            "  python dataset_generator.py --count 50 --seed 42\n"
            "  python dataset_generator.py --count 100 --seed 42 --output dataset\n"
        ),
    )

    parser.add_argument(
        "--count",
        type=int,
        default=50,
        metavar="N",
        help="Jumlah gambar yang akan dibuat (default: 50, maks disarankan: 100)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        metavar="S",
        help="Seed untuk random number generator agar dataset dapat direproduksi (default: 42)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="dataset",
        metavar="DIR",
        help="Direktori root untuk menyimpan dataset (default: dataset)",
    )

    return parser.parse_args()


def validasi_argumen(args: argparse.Namespace) -> None:
    """
    Memvalidasi nilai argumen command-line sebelum eksekusi.

    Raises:
        SystemExit: Jika nilai argumen tidak valid.
    """
    if args.count < 1:
        logger.error("--count harus bernilai minimal 1.")
        sys.exit(1)

    if args.count > 500:
        logger.warning(
            f"--count {args.count} sangat besar. "
            "Proses mungkin membutuhkan waktu lama."
        )


# ──────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────────────────────────────────────


def main() -> None:
    """
    Entry point program dataset_generator.

    Alur:
        1. Parse dan validasi argumen CLI.
        2. Tentukan direktori output (relatif terhadap lokasi script).
        3. Jalankan fungsi generate_dataset().
        4. Keluar dengan kode 0 jika sukses, 1 jika ada kegagalan.
    """
    args = parse_argumen()
    validasi_argumen(args)

    # Direktori output relatif terhadap lokasi script agar portabel
    script_dir = Path(__file__).parent
    output_dir = script_dir / args.output

    logger.info("=" * 50)
    logger.info("  Cloud LPT Image Optimizer - Dataset Generator")
    logger.info("=" * 50)

    try:
        hasil = generate_dataset(
            jumlah_gambar=args.count,
            seed=args.seed,
            output_dir=output_dir,
        )

        # Kode keluar: 0 = semua berhasil, 1 = ada sebagian yang gagal
        if len(hasil) < args.count:
            sys.exit(1)

    except Exception as e:
        logger.error(f"Terjadi kesalahan tidak terduga: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
