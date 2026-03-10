import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MODEL_DIR = os.environ.get("MODEL_DIR", "/workspace/models")

loaded_models = {}
download_status = {}


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


async def download_all_models():
    from huggingface_hub import snapshot_download

    # Download order: smallest to largest
    download_order = [
        "birefnet",        # ~1 GB
        "flux-vae",        # ~2 GB
        "sd-1.5",          # ~5 GB
        "sdxl-base",       # ~7 GB
        "flux-klein-4b",   # ~16 GB
        "llava-13b",       # ~26 GB
        "qwen-2.5-14b",   # ~28 GB
        "flux-schnell",    # ~34 GB (gated - needs HF_TOKEN)
        "qwen-2.5-32b",   # ~64 GB
        "qwen-2.5-72b",   # ~144 GB
    ]

    for name in download_order:
        info = MODELS[name]
        local_dir = os.path.join(MODEL_DIR, name)
        if os.path.exists(local_dir) and os.listdir(local_dir):
            logger.info(f"SKIP: {name} already downloaded")
            download_status[name] = {"status": "completed"}
            continue

        download_status[name] = {"status": "downloading"}
        logger.info(f"DOWNLOADING: {name} from {info['repo']}...")

        success = False
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                await asyncio.to_thread(
                    snapshot_download,
                    repo_id=info["repo"],
                    local_dir=local_dir,
                    ignore_patterns=["*.md", "*.txt", ".gitattributes"],
                    token=HF_TOKEN,
                    max_workers=2,
                    local_dir_use_symlinks=False,
                )
                download_status[name] = {"status": "completed"}
                logger.info(f"DONE: {name}")
                success = True
                break
            except Exception as e:
                err = str(e)
                if "401" in err or "403" in err:
                    download_status[name] = {"status": "error", "error": f"Auth required: {err}"}
                    logger.error(f"FAILED: {name}: needs HF_TOKEN with accepted license. Skipping.")
                    break
                wait = min(30 * attempt, 120)
                logger.warning(f"RETRY {attempt}/{MAX_RETRIES} for {name} in {wait}s: {err[:200]}")
                download_status[name] = {"status": "downloading", "retry": attempt}
                await asyncio.sleep(wait)

        if not success and download_status[name].get("status") != "error":
            download_status[name] = {"status": "error", "error": f"Failed after {MAX_RETRIES} retries"}
            logger.error(f"FAILED: {name} after {MAX_RETRIES} retries")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting model server. Downloading models in background...")
    task = asyncio.create_task(download_all_models())
    yield
    task.cancel()


app = FastAPI(title="OVH Model Server", lifespan=lifespan)


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
    return {
        "model": model_name,
        "loaded": model_name in loaded_models,
        "download": download_status.get(model_name, {"status": "pending"}),
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
                ignore_patterns=["*.md", "*.txt", ".gitattributes"],
                token=HF_TOKEN,
                max_workers=2,
                local_dir_use_symlinks=False,
            )
            download_status[model_name] = {"status": "completed"}
        except Exception as e:
            download_status[model_name] = {"status": "error", "error": str(e)}

    asyncio.create_task(_dl())
    return {"status": "download_started", "model": model_name}


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
        logger.error(f"Failed to load {model_name}: {e}")
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
        from diffusers import DiffusionPipeline
        pipe = DiffusionPipeline.from_pretrained(local_dir, torch_dtype=torch.float16)
        pipe.to("cuda")
        return {"pipeline": pipe}

    elif model_type == "segmentation":
        from transformers import AutoModelForImageSegmentation
        model = AutoModelForImageSegmentation.from_pretrained(local_dir, trust_remote_code=True)
        model.to("cuda")
        return {"model": model}

    elif model_type == "vae":
        from diffusers import AutoencoderKL
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
