# backend.py
# Deploy with: modal deploy backend.py

from __future__ import annotations

from fastapi import Request
from fastapi.responses import Response, JSONResponse

import io, os, base64, tempfile, time, math, json
from pathlib import Path

import modal

app = modal.App("ltx23-video-app")

volume        = modal.Volume.from_name("ltx23-cache",   create_if_missing=True)
result_volume = modal.Volume.from_name("ltx23-results", create_if_missing=True)

VOLUME_MOUNT_PATH = Path("/model-cache")
RESULT_MOUNT_PATH = Path("/job-results")

# ---------------------------------------------------------------------------
# Image — use Modal's official CUDA image, install on top of it
# This avoids the PyTorch/CUDA version mismatch entirely
# ---------------------------------------------------------------------------
image = (
    # Official Modal GPU image
    modal.Image.from_registry(
        "nvcr.io/nvidia/pytorch:24.12-py3",
        add_python="3.12",
    )
    .apt_install(
        "git", "wget", "ffmpeg",
        "libgl1", "libglib2.0-0",
        "libsndfile1", "libsox-fmt-all",
    )
    .pip_install(
        "transformers>=4.52.0",
        "tokenizers>=0.22.0",
        "sentencepiece>=0.2.0",
        "accelerate>=1.3.0",
        "huggingface_hub>=0.27.0",
        "safetensors>=0.4.5",
        "diffusers @ git+https://github.com/huggingface/diffusers.git",
        "peft>=0.12.0",
        "av",
    )
    # ── PATCH THE LIGHTRICKS BUG ─────────────────────────────────────────
    # We clone their repo, inject the missing __init__.py file, and install
    # ── PATCH THE LIGHTRICKS BUG ─────────────────────────────────────────
    .run_commands(
        "git clone https://github.com/Lightricks/LTX-2.git /opt/LTX-2",
        "mkdir -p /opt/LTX-2/packages/ltx-pipelines/src/ltx_pipelines/multigpu",
        "touch /opt/LTX-2/packages/ltx-pipelines/src/ltx_pipelines/multigpu/__init__.py",
        "pip install /opt/LTX-2/packages/ltx-core /opt/LTX-2/packages/ltx-pipelines"
    )
    # ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
    .pip_install(
        "soundfile>=0.12.1",
        "librosa>=0.10.2",
        "scipy>=1.13.0",
        "imageio[ffmpeg]>=2.34.0",
        "imageio-ffmpeg>=0.5.1",
        "Pillow>=10.4.0",
        "opencv-python-headless>=4.10.0",
        "numpy>=1.26.0",
        "fastapi>=0.115.0",
        "python-multipart>=0.0.9",
        "quanto>=0.2.0",
    )
)

HF_HOME_IN_VOLUME = str(VOLUME_MOUNT_PATH / "hf_home")
MODEL_ID          = "Lightricks/LTX-2"
CHUNK_FRAMES      = 73
MAX_DURATION      = 60.0

DEFAULT_NEGATIVE = (
    "shaky, glitchy, low quality, worst quality, deformed, distorted, disfigured, "
    "motion smear, motion artifacts, fused fingers, bad anatomy, weird hand, ugly, "
    "transition, static, watermark, text, blurry, overexposed, silence, muted."
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def b64_to_pil(b64_str: str):
    from PIL import Image
    return Image.open(io.BytesIO(base64.b64decode(b64_str))).convert("RGB")


def snap_frames(n: int) -> int:
    k = max(1, round((n - 1) / 8))
    return k * 8 + 1


def clamp_duration(s: float) -> float:
    return max(1.0, min(float(s), MAX_DURATION))


def enhance_audio_in_mp4(input_path: str, output_path: str) -> None:
    import subprocess

    result = subprocess.run(
        ["ffmpeg", "-y", "-i", input_path,
         "-af", "aresample=resampler=soxr:out_sample_rate=44100,"
                "loudnorm=I=-14:TP=-1:LRA=11:print_format=json",
         "-f", "null", "-"],
        capture_output=True, text=True,
    )
    stats: dict = {}
    try:
        s = result.stderr
        js, je = s.rfind("{"), s.rfind("}") + 1
        if js >= 0:
            stats = json.loads(s[js:je])
    except Exception:
        pass

    lnorm = (
        f"loudnorm=I=-14:TP=-1:LRA=11"
        f":measured_I={stats['input_i']}"
        f":measured_TP={stats['input_tp']}"
        f":measured_LRA={stats['input_lra']}"
        f":measured_thresh={stats['input_thresh']}"
        f":offset={stats['target_offset']}"
        f":linear=true:print_format=none"
        if stats.get("input_i") else
        "loudnorm=I=-14:TP=-1:LRA=11:linear=true:print_format=none"
    )
    af = ",".join([
        "aresample=resampler=soxr:out_sample_rate=44100",
        lnorm,
        "equalizer=f=120:t=h:width=80:g=3",
        "equalizer=f=3000:t=h:width=2000:g=2",
        "equalizer=f=8000:t=h:width=4000:g=1.5",
        "dynaudnorm=p=0.9:m=20",
    ])
    subprocess.run(
        ["ffmpeg", "-y", "-i", input_path,
         "-vcodec", "copy", "-af", af,
         "-acodec", "aac", "-b:a", "192k", "-ar", "44100",
         output_path],
        check=True, capture_output=True,
    )


def concat_mp4_chunks(paths: list[str], out: str) -> None:
    import subprocess
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        lp = f.name
        for p in paths:
            f.write(f"file '{p}'\n")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lp,
         "-vcodec", "copy", "-acodec", "aac", "-b:a", "192k", "-ar", "44100", out],
        check=True, capture_output=True,
    )
    os.unlink(lp)


# ---------------------------------------------------------------------------
# Keep-warm
# ---------------------------------------------------------------------------

@app.function(image=image, schedule=modal.Period(minutes=3), timeout=20)
def keep_warm():
    print("[keep-warm] ping")


# ---------------------------------------------------------------------------
# GPU smoke-test — run with: modal run backend.py::test_gpu
# ---------------------------------------------------------------------------

@app.function(
    image=image,
    gpu="A100-80GB",
    volumes={str(VOLUME_MOUNT_PATH): volume},
    timeout=300,
)
def test_gpu():
    import torch
    print(f"PyTorch: {torch.__version__}")
    print(f"CUDA: {torch.cuda.is_available()} | GPU: {torch.cuda.get_device_name(0)}")

    import transformers
    print(f"transformers: {transformers.__version__}")

    for name, stmt in [
        ("transformers.Gemma3ForConditionalGeneration",
         "from transformers import Gemma3ForConditionalGeneration"),
        ("diffusers LTX2Pipeline",
         "from diffusers.pipelines.ltx2 import LTX2Pipeline"),
        ("ltx_pipelines.DistilledPipeline",
         "from ltx_pipelines import DistilledPipeline"),
    ]:
        try:
            exec(stmt)
            print(f"  ✓ {name}")
        except Exception as e:
            print(f"  ✗ {name}: {e}")


# ---------------------------------------------------------------------------
# Inference class
# ---------------------------------------------------------------------------

@app.cls(
    image=image,
    gpu="A100-80GB",
    volumes={
        str(VOLUME_MOUNT_PATH): volume,
        str(RESULT_MOUNT_PATH): result_volume,
    },
    timeout=3600,
    scaledown_window=300,
)
@modal.concurrent(max_inputs=1)
class LTX23Inference:

    @modal.enter()
    def load_models(self):
        import torch

        os.environ["HF_HOME"]            = HF_HOME_IN_VOLUME
        os.environ["TRANSFORMERS_CACHE"] = HF_HOME_IN_VOLUME

        dtype = torch.bfloat16
        cache = HF_HOME_IN_VOLUME
        distilled_exc = None

        # ── Try DistilledPipeline (fast path) ──────────────────────────
        try:
            from ltx_pipelines import DistilledPipeline
            from ltx_pipelines.quantization import QuantizationPolicy

            print("[LTX-2] Loading DistilledPipeline + FP8 …")
            self.distilled_pipe = DistilledPipeline.from_pretrained(
                MODEL_ID,
                torch_dtype=dtype,
                cache_dir=cache,
                quantization=QuantizationPolicy.fp8_cast(),
            )
            self.distilled_pipe.enable_sequential_cpu_offload(device="cuda")
            self._use_distilled = True
            print("[LTX-2] DistilledPipeline ready ✓")
            return

        except Exception as exc:
            distilled_exc = exc
            print(f"[LTX-2] DistilledPipeline failed: {exc}")

        # ── Fallback: diffusers LTX2Pipeline ──────────────────────────
        try:
            from diffusers import FlowMatchEulerDiscreteScheduler
            from diffusers.pipelines.ltx2 import (
                LTX2Pipeline,
                LTX2ImageToVideoPipeline,
                LTX2LatentUpsamplePipeline,
            )
            from diffusers.pipelines.ltx2.latent_upsampler import (
                LTX2LatentUpsamplerModel,
            )

            print("[LTX-2] Loading T2V pipeline …")
            self.t2v_pipe = LTX2Pipeline.from_pretrained(
                MODEL_ID, torch_dtype=dtype, cache_dir=cache
            )
            self.t2v_pipe.enable_sequential_cpu_offload(device="cuda")

            print("[LTX-2] Loading I2V pipeline …")
            self.i2v_pipe = LTX2ImageToVideoPipeline.from_pretrained(
                MODEL_ID, torch_dtype=dtype, cache_dir=cache
            )
            self.i2v_pipe.enable_sequential_cpu_offload(device="cuda")

            print("[LTX-2] Loading upsampler …")
            lu = LTX2LatentUpsamplerModel.from_pretrained(
                MODEL_ID, subfolder="latent_upsampler",
                torch_dtype=dtype, cache_dir=cache,
            )
            self.upsample_pipe = LTX2LatentUpsamplePipeline(
                vae=self.t2v_pipe.vae, latent_upsampler=lu,
            )
            self.upsample_pipe.enable_model_cpu_offload(device="cuda")
            self._scheduler_cls = FlowMatchEulerDiscreteScheduler
            self._cache         = cache
            self._use_distilled = False
            print("[LTX-2] Fallback pipelines ready ✓")

        except Exception as exc2:
            raise RuntimeError(
                f"Both pipelines failed.\n"
                f"DistilledPipeline: {distilled_exc}\n"
                f"Diffusers: {exc2}"
            ) from exc2

    def _run_distilled_chunk(
        self, prompt_embeds, negative_embeds,
        conditioning_image, width, height,
        n_frames, frame_rate, generator,
    ) -> str:
        from diffusers.pipelines.ltx2.export_utils import encode_video

        fd, out = tempfile.mkstemp(suffix="_raw.mp4")
        os.close(fd)

        video_np, audio_tensor = self.distilled_pipe(
            prompt_embeds=prompt_embeds,
            negative_prompt_embeds=negative_embeds,
            image=conditioning_image,
            width=width, height=height,
            num_frames=n_frames, frame_rate=frame_rate,
            num_inference_steps=8,
            guidance_scale=1.0,
            generator=generator,
            output_type="np",
            return_dict=False,
        )
        encode_video(
            video_np[0], fps=frame_rate,
            audio=audio_tensor[0].float().cpu(),
            audio_sample_rate=self.distilled_pipe.vocoder.config.output_sampling_rate,
            output_path=out,
        )
        return out

    def _run_fallback_chunk(
        self, is_first_t2v, conditioning_image,
        prompt, negative_prompt,
        width, height, n_frames, frame_rate,
        num_inference_steps, guidance_scale,
        generator,
    ) -> str:
        from diffusers.pipelines.ltx2.utils import STAGE_2_DISTILLED_SIGMA_VALUES
        from diffusers.pipelines.ltx2.export_utils import encode_video

        pipe = self.t2v_pipe if is_first_t2v else self.i2v_pipe
        kw = dict(
            prompt=prompt, negative_prompt=negative_prompt,
            width=width, height=height,
            num_frames=n_frames, frame_rate=frame_rate,
            num_inference_steps=num_inference_steps,
            sigmas=None, guidance_scale=guidance_scale,
            output_type="latent", return_dict=False,
            generator=generator,
        )
        if not is_first_t2v:
            kw["image"] = conditioning_image

        vl, al = pipe(**kw)

        upscaled = self.upsample_pipe(
            latents=vl, output_type="latent", return_dict=False
        )[0]
        pipe.load_lora_weights(
            MODEL_ID, adapter_name="s2",
            weight_name="ltx-2-19b-distilled-lora-384.safetensors",
            cache_dir=self._cache,
        )
        pipe.set_adapters("s2", 1.0)
        pipe.vae.enable_tiling()
        pipe.scheduler = self._scheduler_cls.from_config(
            pipe.scheduler.config,
            use_dynamic_shifting=False, shift_terminal=None,
        )
        video_np, audio_tensor = pipe(
            latents=upscaled, audio_latents=al,
            prompt=prompt, negative_prompt=negative_prompt,
            num_inference_steps=3,
            noise_scale=STAGE_2_DISTILLED_SIGMA_VALUES[0],
            sigmas=STAGE_2_DISTILLED_SIGMA_VALUES,
            guidance_scale=1.0, output_type="np", return_dict=False,
        )
        pipe.unload_lora_weights()
        pipe.vae.disable_tiling()

        fd, out = tempfile.mkstemp(suffix="_raw.mp4")
        os.close(fd)
        encode_video(
            video_np[0], fps=frame_rate,
            audio=audio_tensor[0].float().cpu(),
            audio_sample_rate=pipe.vocoder.config.output_sampling_rate,
            output_path=out,
        )
        return out

    def _last_frame(self, mp4: str, w: int, h: int):
        import cv2
        from PIL import Image as PILImage
        cap   = cv2.VideoCapture(mp4)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, total - 1))
        ret, frame = cap.read()
        cap.release()
        if not ret:
            raise RuntimeError(f"Cannot read last frame of {mp4}")
        return PILImage.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)).resize((w, h))

    def _write_status(self, job_id, chunk, total, stage, error=""):
        RESULT_MOUNT_PATH.mkdir(parents=True, exist_ok=True)
        status = "error" if error else ("done" if stage == "done" else "running")
        (RESULT_MOUNT_PATH / f"{job_id}.status.json").write_text(
            json.dumps({
                "job_id": job_id, "status": status,
                "stage": stage, "chunk": chunk,
                "total": total, "error": error,
            })
        )
        result_volume.commit()

    @modal.method()
    def generate(
        self,
        job_id: str,
        prompt: str,
        negative_prompt: str = DEFAULT_NEGATIVE,
        width: int = 768,
        height: int = 512,
        duration_seconds: float = 5.0,
        frame_rate: float = 24.0,
        num_inference_steps: int = 8,
        guidance_scale: float = 1.0,
        seed: int = -1,
        image_b64: str | None = None,
    ) -> str:
        import torch

        RESULT_MOUNT_PATH.mkdir(parents=True, exist_ok=True)
        duration_seconds = clamp_duration(duration_seconds)

        total_frames = snap_frames(int(duration_seconds * frame_rate))
        chunks: list[int] = []
        remaining = total_frames
        while remaining > 0:
            c = snap_frames(min(CHUNK_FRAMES, remaining))
            chunks.append(c)
            remaining -= (c - 1)
        num_chunks = len(chunks)

        print(
            f"[LTX-2] Job {job_id[:8]} | {duration_seconds:.0f}s | "
            f"{num_chunks} chunks | "
            f"{'Distilled' if self._use_distilled else 'Fallback'}"
        )
        self._write_status(job_id, 0, num_chunks, "encoding_text")

        if self._use_distilled:
            with torch.no_grad():
                prompt_embeds, neg_embeds = self.distilled_pipe.encode_prompt(
                    prompt=prompt, negative_prompt=negative_prompt, device="cpu",
                )
        else:
            prompt_embeds = neg_embeds = None

        last_frame_pil = (
            b64_to_pil(image_b64).resize((width, height)) if image_b64 else None
        )
        raw_paths: list[str] = []

        try:
            for idx, n_frames in enumerate(chunks):
                chunk_seed = (
                    (seed + idx * 997) % (2 ** 31)
                    if seed >= 0
                    else int(time.time() * 1000 + idx) % (2 ** 31)
                )
                generator    = torch.Generator("cuda").manual_seed(chunk_seed)
                is_first_t2v = (idx == 0 and last_frame_pil is None)

                print(f"[LTX-2] Chunk {idx+1}/{num_chunks} ({n_frames} frames)")
                self._write_status(job_id, idx, num_chunks, f"chunk_{idx+1}")

                if self._use_distilled:
                    raw = self._run_distilled_chunk(
                        prompt_embeds=prompt_embeds,
                        negative_embeds=neg_embeds,
                        conditioning_image=last_frame_pil,
                        width=width, height=height,
                        n_frames=n_frames, frame_rate=frame_rate,
                        generator=generator,
                    )
                else:
                    raw = self._run_fallback_chunk(
                        is_first_t2v=is_first_t2v,
                        conditioning_image=last_frame_pil,
                        prompt=prompt, negative_prompt=negative_prompt,
                        width=width, height=height,
                        n_frames=n_frames, frame_rate=frame_rate,
                        num_inference_steps=num_inference_steps,
                        guidance_scale=guidance_scale,
                        generator=generator,
                    )

                raw_paths.append(raw)
                if idx < num_chunks - 1:
                    last_frame_pil = self._last_frame(raw, width, height)

            self._write_status(job_id, num_chunks, num_chunks, "enhancing_audio")
            enhanced: list[str] = []
            for raw in raw_paths:
                fd, enh = tempfile.mkstemp(suffix="_enh.mp4")
                os.close(fd)
                try:
                    enhance_audio_in_mp4(raw, enh)
                    enhanced.append(enh)
                except Exception as exc:
                    print(f"[LTX-2] Audio enhancement failed: {exc}")
                    enhanced.append(raw)

            self._write_status(job_id, num_chunks, num_chunks, "stitching")
            final = str(RESULT_MOUNT_PATH / f"{job_id}.mp4")
            if len(enhanced) == 1:
                import shutil
                shutil.copy(enhanced[0], final)
            else:
                concat_mp4_chunks(enhanced, final)

            for p in raw_paths + enhanced:
                try: os.unlink(p)
                except Exception: pass

            self._write_status(job_id, num_chunks, num_chunks, "done")
            result_volume.commit()
            print(f"[LTX-2] Job {job_id[:8]} done — {Path(final).stat().st_size/1024:.0f} KB")
            return job_id

        except Exception as exc:
            self._write_status(job_id, 0, num_chunks, "error", str(exc))
            result_volume.commit()
            raise


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.function(image=image, timeout=60, min_containers=1)
@modal.fastapi_endpoint(method="POST", label="ltx23-submit")
async def submit_endpoint(request: Request):
    import uuid
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body."}, status_code=400)

    prompt = body.get("prompt", "").strip()
    if not prompt:
        return JSONResponse({"error": "'prompt' is required."}, status_code=422)

    mode      = body.get("mode", "t2v").lower()
    image_b64 = body.get("image_b64", None)
    if mode == "i2v" and not image_b64:
        return JSONResponse({"error": "image_b64 required for i2v."}, status_code=422)

    duration = clamp_duration(float(body.get("duration_seconds", 5.0)))
    job_id   = str(uuid.uuid4()).replace("-", "")

    params = {
        "job_id":              job_id,
        "prompt":              prompt,
        "negative_prompt":     body.get("negative_prompt", DEFAULT_NEGATIVE),
        "width":               int(body.get("width",  768)),
        "height":              int(body.get("height", 512)),
        "duration_seconds":    duration,
        "frame_rate":          float(body.get("frame_rate", 24.0)),
        "num_inference_steps": 8,
        "guidance_scale":      1.0,
        "seed":                int(body.get("seed", -1)),
        "image_b64":           image_b64,
    }

    LTX23Inference().generate.spawn(**params)

    num_chunks = max(1, math.ceil(duration / (CHUNK_FRAMES / 24.0)))
    return JSONResponse({
        "job_id":            job_id,
        "status":            "queued",
        "num_chunks":        num_chunks,
        "estimated_minutes": round(num_chunks * 1.5 + 1),
        "message":           f"Queued. Poll /status?job_id={job_id}",
    })


@app.function(image=image, timeout=60, min_containers=1)
@modal.fastapi_endpoint(method="POST", label="ltx23-submit-image")
async def submit_image_endpoint(request: Request):
    import uuid
    try:
        form = await request.form()
    except Exception:
        return JSONResponse({"error": "Could not parse form."}, status_code=400)

    prompt = (form.get("prompt") or "").strip()
    if not prompt:
        return JSONResponse({"error": "'prompt' is required."}, status_code=422)

    image_file = form.get("image")
    if image_file is None:
        return JSONResponse({"error": "'image' file is required."}, status_code=422)

    image_b64 = base64.b64encode(await image_file.read()).decode()
    duration  = clamp_duration(float(form.get("duration_seconds", 5.0)))
    job_id    = str(uuid.uuid4()).replace("-", "")

    params = {
        "job_id":              job_id,
        "prompt":              prompt,
        "negative_prompt":     form.get("negative_prompt", DEFAULT_NEGATIVE),
        "width":               int(form.get("width",  768)),
        "height":              int(form.get("height", 512)),
        "duration_seconds":    duration,
        "frame_rate":          float(form.get("frame_rate", 24.0)),
        "num_inference_steps": 8,
        "guidance_scale":      1.0,
        "seed":                int(form.get("seed", -1)),
        "image_b64":           image_b64,
    }

    LTX23Inference().generate.spawn(**params)

    num_chunks = max(1, math.ceil(duration / (CHUNK_FRAMES / 24.0)))
    return JSONResponse({
        "job_id":            job_id,
        "status":            "queued",
        "num_chunks":        num_chunks,
        "estimated_minutes": round(num_chunks * 1.5 + 1),
    })


@app.function(
    image=image, timeout=30, min_containers=2,
    volumes={str(RESULT_MOUNT_PATH): result_volume},
)
@modal.fastapi_endpoint(method="GET", label="ltx23-status")
async def status_endpoint(request: Request):
    job_id = request.query_params.get("job_id", "")
    if not job_id:
        return JSONResponse({"error": "job_id required."}, status_code=400)
    result_volume.reload()
    sf = RESULT_MOUNT_PATH / f"{job_id}.status.json"
    if not sf.exists():
        return JSONResponse({
            "job_id": job_id, "status": "queued",
            "stage": "waiting_for_gpu", "chunk": 0, "total": 0, "error": "",
        })
    try:
        return JSONResponse(json.loads(sf.read_text()))
    except Exception:
        return JSONResponse({
            "job_id": job_id, "status": "queued",
            "stage": "starting", "chunk": 0, "total": 0, "error": "",
        })


@app.function(
    image=image, timeout=60, min_containers=1,
    volumes={str(RESULT_MOUNT_PATH): result_volume},
)
@modal.fastapi_endpoint(method="GET", label="ltx23-result")
async def result_endpoint(request: Request):
    job_id = request.query_params.get("job_id", "")
    if not job_id:
        return JSONResponse({"error": "job_id required."}, status_code=400)
    result_volume.reload()
    mp4 = RESULT_MOUNT_PATH / f"{job_id}.mp4"
    if not mp4.exists():
        return JSONResponse({"error": "Not ready yet."}, status_code=404)
    content = mp4.read_bytes()
    try:
        (RESULT_MOUNT_PATH / f"{job_id}.status.json").unlink(missing_ok=True)
        result_volume.commit()
    except Exception:
        pass
    return Response(
        content=content, media_type="video/mp4",
        headers={
            "Content-Disposition": f'attachment; filename="ltx23_{job_id[:8]}.mp4"',
            "X-Audio-Synced": "true", "X-Job-Id": job_id,
        },
    )


@app.local_entrypoint()
def main():
    print("Smoke-test: 5 s T2V …")
    job = LTX23Inference().generate.remote(
        job_id="smoke001",
        prompt="A jazz pianist in a smoky New York club, amber spotlights, upbeat jazz piano.",
        duration_seconds=5.0, seed=42,
    )
    out = Path("smoke.mp4")
    out.write_bytes((RESULT_MOUNT_PATH / f"{job}.mp4").read_bytes())
    print(f"Saved {out.stat().st_size/1024:.1f} KB → {out}")