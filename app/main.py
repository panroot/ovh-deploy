import os
import sys
import time
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, UploadFile, File, Request
from pydantic import BaseModel
from typing import Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MODEL_DIR = os.environ.get("MODEL_DIR", "/workspace/models")

# Auto-shutdown settings (env vars, in minutes)
IDLE_TIMEOUT = int(os.environ.get("IDLE_TIMEOUT", "30"))       # 30 min bez requestów = shutdown
MAX_UPTIME = int(os.environ.get("MAX_UPTIME", "1440"))         # 24h max uptime = shutdown
STARTUP_TIME = time.time()

loaded_models = {}
download_status = {}
last_request_time = time.time()


# ── Model registry ──────────────────────────────────────────────────────────

MODELS = {
    "llava-13b": {
        "repo": "llava-hf/llava-1.5-13b-hf",
        "type": "vlm",
    },
    "flux-schnell": {
        "repo": "black-forest-labs/FLUX.1-schnell",
        "type": "diffusion",
    },
    "flux-klein-4b": {
        "repo": "freepik/flux.1-lite-8B-alpha",
        "type": "diffusion",
    },
    "flux-vae": {
        "repo": "black-forest-labs/FLUX.1-schnell",
        "type": "vae",
    },
    "sdxl-base": {
        "repo": "stabilityai/stable-diffusion-xl-base-1.0",
        "type": "diffusion",
    },
    "sd-1.5": {
        "repo": "stable-diffusion-v1-5/stable-diffusion-v1-5",
        "type": "diffusion",
    },
    "birefnet": {
        "repo": "ZhengPeng7/BiRefNet",
        "type": "segmentation",
    },
    "qwen-2.5-14b": {
        "repo": "Qwen/Qwen2.5-14B-Instruct",
        "type": "llm",
    },
    "qwen-2.5-32b": {
        "repo": "Qwen/Qwen2.5-32B-Instruct",
        "type": "llm",
    },
    "qwen-2.5-72b": {
        "repo": "Qwen/Qwen2.5-72B-Instruct",
        "type": "llm",
    },
}


# ── Auto-download on startup ───────────────────────────────────────────────

HF_TOKEN = os.environ.get("HF_TOKEN", None)
MAX_RETRIES = 5


AUTO_DOWNLOAD = os.environ.get("AUTO_DOWNLOAD", "birefnet,qwen-2.5-14b,sd-1.5").split(",")


async def download_startup_models():
    """Download selected models on startup (from HuggingFace, no persistent storage)."""
    from huggingface_hub import snapshot_download

    # Mark all models
    for name in MODELS:
        local_dir = os.path.join(MODEL_DIR, name)
        if os.path.exists(local_dir) and os.listdir(local_dir):
            download_status[name] = {"status": "completed"}
        elif name in AUTO_DOWNLOAD:
            download_status[name] = {"status": "queued"}
        else:
            download_status[name] = {"status": "not_downloaded"}

    # Download auto-download models
    for name in AUTO_DOWNLOAD:
        name = name.strip()
        if name not in MODELS:
            continue
        if download_status.get(name, {}).get("status") == "completed":
            logger.info(f"SKIP: {name} already present")
            continue

        info = MODELS[name]
        local_dir = os.path.join(MODEL_DIR, name)
        download_status[name] = {"status": "downloading"}
        logger.info(f"DOWNLOADING: {name} (~startup)")

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                await asyncio.to_thread(
                    snapshot_download,
                    repo_id=info["repo"],
                    local_dir=local_dir,
                    ignore_patterns=["*.md", ".gitattributes"],
                    token=HF_TOKEN,
                    max_workers=4,
                    local_dir_use_symlinks=False,
                )
                download_status[name] = {"status": "completed"}
                logger.info(f"DONE: {name}")
                break
            except Exception as e:
                err = str(e)
                if "401" in err or "403" in err:
                    download_status[name] = {"status": "error", "error": f"Auth: {err[:200]}"}
                    logger.error(f"FAILED: {name}: auth error, skipping")
                    break
                wait = min(30 * attempt, 120)
                logger.warning(f"RETRY {attempt}/{MAX_RETRIES} for {name}: {err[:200]}")
                download_status[name] = {"status": "downloading", "retry": attempt}
                await asyncio.sleep(wait)
        else:
            if download_status[name].get("status") != "error":
                download_status[name] = {"status": "error", "error": f"Failed after {MAX_RETRIES} retries"}
                logger.error(f"FAILED: {name}")


async def idle_watchdog():
    """Auto-shutdown on idle or max uptime exceeded."""
    global last_request_time
    shutdown_requested = False
    while True:
        await asyncio.sleep(60)  # check every minute
        if shutdown_requested:
            continue
        idle_min = (time.time() - last_request_time) / 60
        uptime_min = (time.time() - STARTUP_TIME) / 60

        reason = None
        if IDLE_TIMEOUT > 0 and idle_min >= IDLE_TIMEOUT:
            reason = f"IDLE SHUTDOWN: No requests for {IDLE_TIMEOUT} min."
        elif MAX_UPTIME > 0 and uptime_min >= MAX_UPTIME:
            reason = f"MAX UPTIME SHUTDOWN: Running for {int(uptime_min)} min (limit: {MAX_UPTIME})."

        if reason:
            shutdown_requested = True
            logger.warning(f"{reason} Exiting. Watchdog will stop the app.")
            # Exit with code 1 - OVH moves to FAILED, watchdog does proper stop
            os._exit(1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting model server")
    logger.info(f"Auto-download: {AUTO_DOWNLOAD}")
    logger.info(f"Auto-shutdown: idle={IDLE_TIMEOUT}min, max_uptime={MAX_UPTIME}min")
    dl_task = asyncio.create_task(download_startup_models())
    wd_task = asyncio.create_task(idle_watchdog())
    yield
    dl_task.cancel()
    wd_task.cancel()


app = FastAPI(title="OVH Model Server", lifespan=lifespan)


@app.middleware("http")
async def track_activity(request: Request, call_next):
    global last_request_time
    if request.url.path != "/health":  # healthcheck nie resetuje idle timer
        last_request_time = time.time()
    response = await call_next(request)
    return response


# ── Requests ────────────────────────────────────────────────────────────────

class TextRequest(BaseModel):
    prompt: str
    model: str
    max_tokens: int = 2048
    temperature: float = 0.7


class ImageRequest(BaseModel):
    prompt: str
    model: str
    width: int = 1024
    height: int = 1024
    steps: int = 20
    guidance_scale: float = 7.5


# ── Health & status ─────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "loaded_models": list(loaded_models.keys())}


@app.get("/status")
async def server_status():
    now = time.time()
    idle_min = round((now - last_request_time) / 60, 1)
    uptime_min = round((now - STARTUP_TIME) / 60, 1)
    cost_pln = round(uptime_min / 60 * 7.24, 2)
    return {
        "uptime_min": uptime_min,
        "idle_min": idle_min,
        "idle_shutdown_at_min": IDLE_TIMEOUT,
        "max_uptime_shutdown_at_min": MAX_UPTIME,
        "idle_remaining_min": round(max(0, IDLE_TIMEOUT - idle_min), 1),
        "uptime_remaining_min": round(max(0, MAX_UPTIME - uptime_min), 1),
        "estimated_cost_pln": cost_pln,
    }


@app.get("/models")
async def list_models():
    result = {}
    for name, info in MODELS.items():
        result[name] = {
            "type": info["type"],
            "repo": info["repo"],
            "loaded": name in loaded_models,
            "download": download_status.get(name, {"status": "pending"}),
        }
    return result


@app.get("/models/{model_name}/status")
async def model_status(model_name: str):
    if model_name not in MODELS:
        raise HTTPException(status_code=404, detail=f"Unknown model: {model_name}")
    local_dir = os.path.join(MODEL_DIR, model_name)
    files = {}
    if os.path.exists(local_dir):
        for root, dirs, fnames in os.walk(local_dir):
            rel = os.path.relpath(root, local_dir)
            prefix = "" if rel == "." else rel + "/"
            for f in sorted(fnames):
                fp = os.path.join(root, f)
                try:
                    size = os.path.getsize(fp)
                except:
                    size = -1
                files[prefix + f] = size
    return {
        "model": model_name,
        "loaded": model_name in loaded_models,
        "download": download_status.get(model_name, {"status": "pending"}),
        "files": files,
    }


# ── Download single model (manual) ─────────────────────────────────────────

@app.post("/models/{model_name}/download")
async def download_model(model_name: str):
    from huggingface_hub import snapshot_download

    if model_name not in MODELS:
        raise HTTPException(status_code=404, detail=f"Unknown model: {model_name}")

    if download_status.get(model_name, {}).get("status") == "downloading":
        return {"status": "already_downloading"}

    async def _dl():
        info = MODELS[model_name]
        download_status[model_name] = {"status": "downloading"}
        try:
            local_dir = os.path.join(MODEL_DIR, model_name)
            await asyncio.to_thread(
                snapshot_download,
                repo_id=info["repo"],
                local_dir=local_dir,
                ignore_patterns=["*.md", ".gitattributes"],
                token=HF_TOKEN,
                max_workers=2,
                local_dir_use_symlinks=False,
            )
            download_status[model_name] = {"status": "completed"}
        except Exception as e:
            download_status[model_name] = {"status": "error", "error": str(e)}

    asyncio.create_task(_dl())
    return {"status": "download_started", "model": model_name}


@app.post("/models/{model_name}/redownload")
async def redownload_model(model_name: str):
    """Delete existing model files and re-download (fixes broken symlinks)."""
    import shutil
    from huggingface_hub import snapshot_download

    if model_name not in MODELS:
        raise HTTPException(status_code=404, detail=f"Unknown model: {model_name}")

    if model_name in loaded_models:
        raise HTTPException(status_code=400, detail="Unload model first")

    if download_status.get(model_name, {}).get("status") == "downloading":
        return {"status": "already_downloading"}

    async def _rdl():
        import subprocess
        info = MODELS[model_name]
        local_dir = os.path.join(MODEL_DIR, model_name)
        download_status[model_name] = {"status": "deleting"}
        try:
            if os.path.exists(local_dir):
                # Use rm -rf for FUSE compatibility (shutil.rmtree may not work on FUSE)
                await asyncio.to_thread(
                    subprocess.run, ["rm", "-rf", local_dir], check=True, timeout=300
                )
                logger.info(f"Deleted {local_dir}")
            download_status[model_name] = {"status": "downloading"}
            logger.info(f"RE-DOWNLOADING: {model_name} from {info['repo']}...")
            await asyncio.to_thread(
                snapshot_download,
                repo_id=info["repo"],
                local_dir=local_dir,
                ignore_patterns=["*.md", ".gitattributes"],
                token=HF_TOKEN,
                max_workers=2,
                local_dir_use_symlinks=False,
            )
            download_status[model_name] = {"status": "completed"}
            logger.info(f"RE-DOWNLOAD DONE: {model_name}")
        except Exception as e:
            download_status[model_name] = {"status": "error", "error": str(e)}
            logger.error(f"RE-DOWNLOAD FAILED: {model_name}: {e}")

    asyncio.create_task(_rdl())
    return {"status": "redownload_started", "model": model_name}


# ── Load / Unload ──────────────────────────────────────────────────────────

@app.post("/models/{model_name}/load")
async def load_model(model_name: str):
    if model_name not in MODELS:
        raise HTTPException(status_code=404, detail=f"Unknown model: {model_name}")

    if model_name in loaded_models:
        return {"status": "already_loaded"}

    local_dir = os.path.join(MODEL_DIR, model_name)
    if not os.path.exists(local_dir):
        raise HTTPException(status_code=400, detail="Model not downloaded yet. Check /models for status.")

    try:
        model = await asyncio.to_thread(_load_model_sync, model_name, MODELS[model_name], local_dir)
        loaded_models[model_name] = model
        return {"status": "loaded", "model": model_name}
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logger.error(f"Failed to load {model_name}: {e}\n{tb}")
        raise HTTPException(status_code=500, detail=str(e))


def _load_model_sync(model_name: str, info: dict, local_dir: str):
    import torch

    model_type = info["type"]

    if model_type == "llm":
        from transformers import AutoModelForCausalLM, AutoTokenizer
        tokenizer = AutoTokenizer.from_pretrained(local_dir, trust_remote_code=True)
        model = AutoModelForCausalLM.from_pretrained(
            local_dir, torch_dtype=torch.float16, device_map="auto", trust_remote_code=True,
        )
        return {"model": model, "tokenizer": tokenizer}

    elif model_type == "vlm":
        from transformers import AutoProcessor, LlavaForConditionalGeneration
        processor = AutoProcessor.from_pretrained(local_dir)
        model = LlavaForConditionalGeneration.from_pretrained(
            local_dir, torch_dtype=torch.float16, device_map="auto",
        )
        return {"model": model, "processor": processor}

    elif model_type == "diffusion":
        from diffusers import (
            DiffusionPipeline, StableDiffusionPipeline,
            StableDiffusionXLPipeline, FluxPipeline,
        )
        # Use specific pipeline classes to avoid auto-detection issues on FUSE mounts
        pipeline_map = {
            "sd-1.5": StableDiffusionPipeline,
            "sdxl-base": StableDiffusionXLPipeline,
            "flux-schnell": FluxPipeline,
            "flux-klein-4b": FluxPipeline,
        }
        pipe_cls = pipeline_map.get(model_name, DiffusionPipeline)
        logger.info(f"Loading {model_name} with {pipe_cls.__name__}")
        pipe = pipe_cls.from_pretrained(local_dir, torch_dtype=torch.float16, local_files_only=True)
        pipe.to("cuda")
        return {"pipeline": pipe}

    elif model_type == "segmentation":
        from transformers import AutoModelForImageSegmentation
        model = AutoModelForImageSegmentation.from_pretrained(local_dir, trust_remote_code=True)
        model.to("cuda")
        return {"model": model}

    elif model_type == "vae":
        from diffusers import AutoencoderKL
        vae_dir = os.path.join(local_dir, "vae")
        if os.path.exists(vae_dir):
            vae = AutoencoderKL.from_pretrained(vae_dir, torch_dtype=torch.float16)
        else:
            vae = AutoencoderKL.from_pretrained(local_dir, torch_dtype=torch.float16)
        vae.to("cuda")
        return {"vae": vae}

    raise ValueError(f"Unknown model type: {model_type}")


@app.post("/models/{model_name}/unload")
async def unload_model(model_name: str):
    import torch
    if model_name not in loaded_models:
        raise HTTPException(status_code=400, detail="Model not loaded")
    del loaded_models[model_name]
    torch.cuda.empty_cache()
    return {"status": "unloaded", "model": model_name}


# ── Inference: text ─────────────────────────────────────────────────────────

@app.post("/v1/chat/completions")
async def chat_completions(request: TextRequest):
    if request.model not in loaded_models:
        raise HTTPException(status_code=400, detail=f"Model '{request.model}' not loaded.")

    info = MODELS.get(request.model)
    if not info or info["type"] not in ("llm", "vlm"):
        raise HTTPException(status_code=400, detail="Use text/VLM model for this endpoint.")

    try:
        return await asyncio.to_thread(_run_text_inference, request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _run_text_inference(request: TextRequest):
    import torch
    ctx = loaded_models[request.model]
    model = ctx["model"]
    tokenizer = ctx.get("tokenizer") or ctx.get("processor")

    messages = [{"role": "user", "content": request.prompt}]
    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(text, return_tensors="pt").to(model.device)

    with torch.no_grad():
        outputs = model.generate(
            **inputs, max_new_tokens=request.max_tokens,
            temperature=request.temperature, do_sample=request.temperature > 0,
        )
    response = tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
    return {
        "model": request.model,
        "choices": [{"message": {"role": "assistant", "content": response}, "finish_reason": "stop"}],
    }


# ── Inference: image generation ─────────────────────────────────────────────

@app.post("/v1/images/generate")
async def generate_image(request: ImageRequest):
    import base64
    from io import BytesIO

    if request.model not in loaded_models:
        raise HTTPException(status_code=400, detail=f"Model '{request.model}' not loaded.")

    info = MODELS.get(request.model)
    if not info or info["type"] != "diffusion":
        raise HTTPException(status_code=400, detail="Use diffusion model for this endpoint.")

    try:
        image = await asyncio.to_thread(_run_image_inference, request)
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return {"model": request.model, "image": base64.b64encode(buffer.getvalue()).decode()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _run_image_inference(request: ImageRequest):
    import torch
    pipe = loaded_models[request.model]["pipeline"]
    with torch.no_grad():
        result = pipe(
            prompt=request.prompt, width=request.width, height=request.height,
            num_inference_steps=request.steps, guidance_scale=request.guidance_scale,
        )
    return result.images[0]


# ── Inference: background removal ───────────────────────────────────────────

@app.post("/v1/background/remove")
async def remove_background(image: UploadFile = File(...)):
    import torch
    from PIL import Image
    from io import BytesIO
    import base64
    from torchvision import transforms

    if "birefnet" not in loaded_models:
        raise HTTPException(status_code=400, detail="BiRefNet not loaded.")

    try:
        contents = await image.read()
        img = Image.open(BytesIO(contents)).convert("RGB")

        transform = transforms.Compose([
            transforms.Resize((1024, 1024)),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ])

        input_tensor = transform(img).unsqueeze(0).to("cuda")
        model = loaded_models["birefnet"]["model"]

        with torch.no_grad():
            pred = model(input_tensor)[-1].sigmoid().cpu()

        mask = pred[0].squeeze()
        mask_pil = transforms.ToPILImage()(mask).resize(img.size)
        img_rgba = img.copy()
        img_rgba.putalpha(mask_pil)

        buffer = BytesIO()
        img_rgba.save(buffer, format="PNG")
        return {"image": base64.b64encode(buffer.getvalue()).decode()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
