"""
worker_service.py
=================
Microservice Worker (Anggota 3) - berjalan di dalam setiap container VM.

Endpoint:
    GET  /health         -> cek status VM (dipakai tes ping dari Master)
    POST /execute_task   -> resize + kompres satu gambar

Konfigurasi lewat environment variable (diatur di docker-compose.yml):
    VM_ID                 default "vm-unknown"
    CAPACITY_MULTIPLIER   default 1.0 (dipakai untuk simulasi kecepatan VM)
    SIMULATE_SPEED        default "1" - aktifkan simulasi kecepatan VM
    REFERENCE_MULTIPLIER  default 2.0 - multiplier tercepat (kecepatan asli)
    DATA_DIR              default "/data" - root volume data di dalam container

Menjalankan lokal:
    uvicorn worker_service:app --host 0.0.0.0 --port 8000
"""

import os
import time
from pathlib import Path

import tempfile

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from image_processor import ImageProcessingError, process_image

VM_ID = os.getenv("VM_ID", "vm-unknown")
CAPACITY_MULTIPLIER = float(os.getenv("CAPACITY_MULTIPLIER", "1.0"))
DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
SIMULATE_SPEED = os.getenv("SIMULATE_SPEED", "0") == "1"
REFERENCE_MULTIPLIER = float(os.getenv("REFERENCE_MULTIPLIER", "2.0"))

app = FastAPI(title=f"Image Processing Worker Service ({VM_ID})")
_started_at = time.time()
_tasks_done = 0


class ExecuteTaskRequest(BaseModel):
    task_id: str
    input_file_path: str
    output_file_path: str
    target_scale: float = 0.5
    quality: int = 85


def _remap(path_str: str, marker: str) -> Path:
    """Ubah path host menjadi path di dalam container: DATA_DIR/<marker>/..."""
    parts = path_str.replace("\\", "/").split("/")
    if marker not in parts:
        return Path(path_str)
    idx = len(parts) - 1 - parts[::-1].index(marker)  # kemunculan terakhir
    return DATA_DIR.joinpath(*parts[idx:])


def _resolve_paths(req: "ExecuteTaskRequest"):
    """
    benchmark_runner mengirim path ABSOLUT milik mesin host
    (mis. C:\\proyek\\data\\raw_images\\image_001.jpg), padahal di dalam
    container file ada di DATA_DIR (mis. /data/raw_images/image_001.jpg).

    - Mode native (dijalankan di mesin yang sama, path langsung ada)
      -> pakai path apa adanya.
    - Mode container (path host tidak ada) -> remap ke DATA_DIR.
    """
    if os.path.isfile(req.input_file_path):
        return Path(req.input_file_path), Path(req.output_file_path)
    return (
        _remap(req.input_file_path, "raw_images"),
        _remap(req.output_file_path, "processed_images"),
    )


@app.get("/health")
def health():
    return {
        "status": "OK",
        "vm_id": VM_ID,
        "capacity_multiplier": CAPACITY_MULTIPLIER,
        "tasks_done": _tasks_done,
        "uptime_s": round(time.time() - _started_at, 1),
    }


@app.post("/execute_task")
def execute_task(req: ExecuteTaskRequest):
    global _tasks_done

    in_path, out_path = _resolve_paths(req)

    try:
        result = process_image(
            str(in_path), str(out_path), req.target_scale, req.quality
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Input image file not found")
    except ImageProcessingError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Gagal memproses gambar: {e}")

    # Simulasi VM heterogen: worker dengan multiplier lebih kecil ditahan
    # sebanding, karena container Docker aslinya berkecepatan sama.
    duration_ms = result.actual_duration_ms
    if SIMULATE_SPEED and CAPACITY_MULTIPLIER > 0:
        target_ms = duration_ms * (REFERENCE_MULTIPLIER / CAPACITY_MULTIPLIER)
        if target_ms > duration_ms:
            time.sleep((target_ms - duration_ms) / 1000.0)
        duration_ms = target_ms

    _tasks_done += 1
    return {
        "status": "SUCCESS",
        "task_id": req.task_id,
        "vm_id": VM_ID,
        "actual_duration_ms": duration_ms,
        # kembalikan path ASLI dari request agar validasi di host menemukan filenya
        "output_file_path": req.output_file_path,
        "original_size": list(result.original_size),
        "new_size": list(result.new_size),
        "input_bytes": result.input_bytes,
        "output_bytes": result.output_bytes,
    }


@app.post("/execute_task_upload")
async def execute_task_upload(
    task_id: str = Form(...),
    target_scale: float = Form(0.5),
    quality: int = Form(85),
    file: UploadFile = File(...),
):
    """
    Mode Azure: worker ada di VM terpisah (tanpa shared volume), jadi gambar
    dikirim lewat multipart dan hasilnya dikembalikan sebagai bytes JPEG.
    Metadata ada di header respons (X-Actual-Duration-Ms, dst).
    """
    global _tasks_done
    with tempfile.TemporaryDirectory() as tmp:
        in_path = os.path.join(tmp, "input_" + os.path.basename(file.filename or "x.jpg"))
        out_path = os.path.join(tmp, "output.jpg")
        with open(in_path, "wb") as f:
            f.write(await file.read())
        try:
            result = process_image(in_path, out_path, target_scale, quality)
        except ImageProcessingError as e:
            raise HTTPException(status_code=422, detail=str(e))
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"Gagal memproses gambar: {e}")
        with open(out_path, "rb") as f:
            data = f.read()

    _tasks_done += 1
    return Response(
        content=data,
        media_type="image/jpeg",
        headers={
            "X-Task-Id": task_id,
            "X-Vm-Id": VM_ID,
            "X-Actual-Duration-Ms": f"{result.actual_duration_ms:.3f}",
            "X-New-Size": f"{result.new_size[0]}x{result.new_size[1]}",
        },
    )
