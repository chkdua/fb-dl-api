from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
import subprocess
import json
import re
import os

app = FastAPI(
    title="Facebook Video Downloader API",
    description="API untuk mendapatkan informasi dan URL download video Facebook menggunakan yt-dlp.",
    version="1.0.0"
)

@app.get("/")
async def read_root():
    return {"message": "Selamat datang di Facebook Video Downloader API. Gunakan /fb-dl?url=[video_url]"}

@app.get("/fb-dl", summary="Download Facebook Video Info")
async def download_fb_video_info(
    url: str = Query(..., description="URL video Facebook yang ingin diunduh informasinya.")
):
    if not re.match(r"^(https?://)?(www\.)?(facebook\.com|fb\.watch)/", url):
        raise HTTPException(
            status_code=400,
            detail="URL yang diberikan bukan URL video Facebook yang valid."
        )

    try:
        # PENTING: yt-dlp harus ada di PATH atau di direktori yang bisa diakses.
        # Karena kita install via pip, harusnya sudah di PATH (di venv).
        # Kita panggil yt-dlp sebagai sub-proses.
        
        # Argumen:
        # - --dump-json: Mendapatkan semua metadata dalam format JSON.
        # - --no-warnings: Sembunyikan warning yang tidak perlu.
        # - --ignore-errors: Lanjutkan meskipun ada error (untuk video tertentu).
        # - --format bestvideo[ext=mp4]+bestaudio[ext=m4a]/best: Coba format MP4 terbaik.
        
        # Contoh penggunaan umum:
        # subprocess.run(["yt-dlp", "--dump-json", url], capture_output=True, text=True, check=True)
        
        # Untuk Facebook, kadang perlu user-agent, tapi yt-dlp biasanya sudah pintar.
        # Kita fokus pada JSON output untuk mendapatkan link download.

        command = ["yt-dlp", "--dump-json", "--no-warnings", "--ignore-errors", url]
        
        # Menjalankan perintah dan menangkap output
        process = subprocess.run(
            command, 
            capture_output=True, 
            text=True, 
            check=True,  # Akan raise CalledProcessError jika perintah gagal
            encoding='utf-8' # Pastikan encoding yang benar
        )

        # Output dari yt-dlp adalah JSON string
        info = json.loads(process.stdout)

        # Ekstrak informasi yang paling relevan
        extracted_info = {
            "title": info.get("title"),
            "thumbnail": info.get("thumbnail"),
            "description": info.get("description"),
            "duration_seconds": info.get("duration"),
            "uploader": info.get("uploader"),
            "upload_date": info.get("upload_date"), # Format YYYYMMDD
            "webpage_url": info.get("webpage_url"),
            "formats": []
        }

        # Cari URL download yang paling sesuai (biasanya format.url)
        # yt-dlp menyediakan banyak format, kita ambil yang "best" atau mp4
        best_quality_url = None
        
        # Urutkan format berdasarkan kualitas (misalnya, semakin tinggi height semakin baik)
        # dan prefer MP4.
        sorted_formats = sorted(
            [f for f in info.get("formats", []) if f.get("url")],
            key=lambda x: x.get("height", 0) if x.get("ext") == "mp4" else -1, # Prioritaskan MP4 tertinggi
            reverse=True
        )

        # Coba cari format video+audio terbaik, atau video saja.
        # yt-dlp sudah melakukan muxing untuk format "best" jika memungkinkan.
        for fmt in sorted_formats:
            format_info = {
                "format_id": fmt.get("format_id"),
                "ext": fmt.get("ext"),
                "resolution": f"{fmt.get('width')}x{fmt.get('height')}" if fmt.get('width') and fmt.get('height') else None,
                "vcodec": fmt.get("vcodec"),
                "acodec": fmt.get("acodec"),
                "filesize": fmt.get("filesize"),
                "url": fmt.get("url")
            }
            extracted_info["formats"].append(format_info)
            
            # Kita ambil URL dari format yang dianggap "best" oleh yt-dlp
            # atau yang pertama dengan ekstensi mp4 dan ada URL-nya.
            if best_quality_url is None and fmt.get("ext") == "mp4" and fmt.get("url"):
                best_quality_url = fmt.get("url")
            
            # Jika ada format dengan quality_tag (misalnya 1080p, 720p) dan itu mp4
            if best_quality_url is None and fmt.get("quality_tag") and fmt.get("ext") == "mp4" and fmt.get("url"):
                best_quality_url = fmt.get("url")
        
        # Tambahkan URL kualitas terbaik secara eksplisit di root JSON
        extracted_info["download_url_best_quality_mp4"] = best_quality_url

        return JSONResponse(content=extracted_info)

    except subprocess.CalledProcessError as e:
        # yt-dlp gagal menjalankan perintah
        error_output = e.stderr.strip()
        print(f"Error executing yt-dlp: {error_output}")
        raise HTTPException(
            status_code=500,
            detail=f"Gagal memproses video: {error_output}"
        )
    except json.JSONDecodeError:
        # Output yt-dlp bukan JSON yang valid
        raise HTTPException(
            status_code=500,
            detail="Gagal mengurai output dari yt-dlp. Mungkin ada masalah dengan video atau yt-dlp."
        )
    except Exception as e:
        # Kesalahan umum lainnya
        print(f"An unexpected error occurred: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Terjadi kesalahan internal: {str(e)}"
        )