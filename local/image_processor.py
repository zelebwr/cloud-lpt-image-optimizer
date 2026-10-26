"""
image_processor.py
==================
Logika pemrosesan gambar (resize + kompresi) berbasis Pillow.
Dipisah dari worker_service.py agar mudah diuji tanpa menjalankan server.
 
Dipakai oleh: worker_service.py (Anggota 3).
"""
 
import os
import time
from dataclasses import dataclass
 
from PIL import Image, UnidentifiedImageError
 
 
class ImageProcessingError(Exception):
    """Error saat memproses gambar (file tidak valid, parameter salah, dll)."""
 
 
@dataclass
class ProcessResult:
    actual_duration_ms: float   # ET_real, diukur dengan time.perf_counter()
    original_size: tuple        # (width, height)
    new_size: tuple             # (width, height) setelah resize
    input_bytes: int
    output_bytes: int
 
 
def process_image(
    input_path: str,
    output_path: str,
    target_scale: float = 0.5,
    quality: int = 85,
) -> ProcessResult:
    """
    Resize gambar dengan LANCZOS lalu simpan dengan optimize=True.
 
    Waktu yang diukur mencakup: buka -> resize -> simpan (seluruh proses
    pengolahan), sesuai Langkah 4 pada proposal.
    """
    if not (0 < target_scale <= 1.0):
        raise ImageProcessingError(
            f"target_scale harus di antara 0 (eksklusif) dan 1.0, diterima: {target_scale}"
        )
    if not (1 <= quality <= 95):
        raise ImageProcessingError(f"quality harus 1-95, diterima: {quality}")
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"Input image file not found: {input_path}")
 
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
 
    start = time.perf_counter()
    try:
        with Image.open(input_path) as img:
            orig_size = img.size
            new_w = max(1, int(img.width * target_scale))
            new_h = max(1, int(img.height * target_scale))
 
            # JPEG tidak mendukung alpha/palette -> paksa RGB
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
 
            resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            resized.save(output_path, format="JPEG", optimize=True, quality=quality)
    except UnidentifiedImageError as e:
        raise ImageProcessingError(f"File bukan gambar yang valid: {input_path}") from e
    actual_ms = (time.perf_counter() - start) * 1000.0
 
    return ProcessResult(
        actual_duration_ms=actual_ms,
        original_size=orig_size,
        new_size=(new_w, new_h),
        input_bytes=os.path.getsize(input_path),
        output_bytes=os.path.getsize(output_path),
    )