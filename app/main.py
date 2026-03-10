import os
import json
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MODEL_DIR = os.environ.get("MODEL_DIR", "/workspace/models")

# Track loaded models and download status
loaded_models = {}
download_status = {}


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting API server. Models will be loaded on first request.")
    logger.info(f"Model directory: {MODEL_DIR}")
    yield
    logger.info("Shutting down API server.")


app = FastAPI(title="OVH AI Deploy - Multi-Model Server", lifespan=lifespan)


# ── Model registry ──────────────────────────────────────────────────────────

MODELS = {
    # Vision-Language
    "llava-13b": {
        "repo": "llava-hf/llava-1.5-13b-hf",
        "type": "vlm",
        "description": "LLaVA 1.5 13B - Vision Language Model",
    },
    # Image generation - FLUX
    "flux-schnell": {
        "repo": "black-forest-labs/FLUX.1-schnell",
        "type": "diffusion",
        "description": "FLUX.1 Schnell - Fast text-to-image",
    },
    "flux-klein-4b": {
        "repo": "freepik/flux.1-lite-8B-alpha",
        "type": "diffusion",
        "description": "FLUX lite/klein variant",
    },
    "flux-vae": {
        "repo": "black-forest-labs/FLUX.1-schnell",
        "type": "vae",
        "subfolder": "vae",
        "description": "FLUX VAE encoder/decoder",
    },
    # Image generation - Stable Diffusion
    "sdxl-base": {
        "repo": "stabilityai/stable-diffusion-xl-base-1.0",
        "type": "diffusion",
        "description": "SDXL Base 1.0",
    },
    "sd-1.5": {
        "repo": "stable-diffusion-v1-5/stable-diffusion-v1-5",
        "type": "diffusion",
        "description": "Stable Diffusion 1.5",
    },
    # Background removal
    "birefnet": {
        "repo": "ZhengPeng7/BiRefNet",
        "type": "segmentation",
        "description": "BiRefNet - Background removal",
    },
    # LLMs - Qwen
    "qwen-2.5-14b": {
        "repo": "Qwen/Qwen2.5-14B-Instruct",
        "type": "llm",
        "description": "Qwen 2.5 14B Instruct",
    },
    "qwen-2.5-32b": {
        "repo": "Qwen/Qwen2.5-32B-Instruct",
        "type": "llm",
        "description": "Qwen 2.5 32B Instruct",
    },
    "qwen-2.5-72b": {
        "repo": "Qwen/Qwen2.5-72B-Instruct",
        "type": "llm",
        "description": "Qwen 2.5 72B Instruct",
    },
}


# ── Health & status ─────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "loaded_models": list(loaded_models.keys())}


@app.get("/models")
async def list_models():
    result = {}
    for name, info in MODELS.items():
        result[name] = {
            "description": info["description"],
            "type": info["type"],
            "repo": info["repo"],
            "loaded": name in loaded_models,
            "downloading": download_status.get(name, {}).get("status") == "downloading",
        }
    return result


@app.get("/models/{model_name}/status")
async def model_status(model_name: str):
    if model_name not in MODELS:
        raise HTTPException(status_code=404, detail=f"Unknown model: {model_name}")
    return {
        "model": model_name,
        "loaded": model_name in loaded_models,
        "download_status": download_status.get(model_name, {"status": "not_started"}),
    }


# ── Download endpoint ───────────────────────────────────────────────────────

@app.post("/models/{model_name}/download")
async def download_model(model_name: str):
    if model_name == "all":
        for name in MODELS:
            if name not in download_status or download_status[name].get("status") != "downloading":
                asyncio.create_task(_download_model(name))
        return {"status": "downloading_all", "models": list(MODELS.keys())}

    if model_name not in MODELS:
        raise HTTPException(status_code=404, detail=f"Unknown model: {model_name}")

    if download_status.get(model_name, {}).get("status") == "downloading":
        return {"status": "already_downloading"}

    asyncio.create_task(_download_model(model_name))
    return {"status": "download_started", "model": model_name}


async def _download_model(model_name: str):
    from huggingface_hub import snapshot_download

    info = MODELS[model_name]
    download_status[model_name] = {"status": "downloading"}
    logger.info(f"Downloading {model_name} from {info['repo']}...")

    try:
        local_dir = os.path.join(MODEL_DIR, model_name)
        await asyncio.to_thread(
            snapshot_download,
            repo_id=info["repo"],
            local_dir=local_dir,
            ignore_patterns=["*.md", "*.txt", ".gitattributes"],
        )
        download_status[model_name] = {"status": "completed"}
        logger.info(f"Download complete: {model_name}")
    except Exception as e:
        download_status[model_name] = {"status": "error", "error": str(e)}
        logger.error(f"Download failed for {model_name}: {e}")


# ── Load model into GPU ────────────────────────────────────────────────────

@app.post("/models/{model_name}/load")
async def load_model(model_name: str):
    if model_name not in MODELS:
        raise HTTPException(status_code=404, detail=f"Unknown model: {model_name}")

    if model_name in loaded_models:
        return {"status": "already_loaded"}

    info = MODELS[model_name]
    local_dir = os.path.join(MODEL_DIR, model_name)

    if not os.path.exists(local_dir):
        raise HTTPException(status_code=400, detail="Model not downloaded yet. POST /models/{name}/download first.")

    try:
        model = await asyncio.to_thread(_load_model_sync, model_name, info, local_dir)
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
            local_dir,
            torch_dtype=torch.float16,
            device_map="auto",
            trust_remote_code=True,
        )
        return {"model": model, "tokenizer": tokenizer}

    elif model_type == "vlm":
        from transformers import AutoProcessor, LlavaForConditionalGeneration

        processor = AutoProcessor.from_pretrained(local_dir)
        model = LlavaForConditionalGeneration.from_pretrained(
            local_dir,
            torch_dtype=torch.float16,
            device_map="auto",
        )
        return {"model": model, "processor": processor}

    elif model_type == "diffusion":
        from diffusers import DiffusionPipeline

        pipe = DiffusionPipeline.from_pretrained(
            local_dir,
            torch_dtype=torch.float16,
        )
        pipe.to("cuda")
        return {"pipeline": pipe}

    elif model_type == "segmentation":
        from transformers import AutoModelForImageSegmentation

        model = AutoModelForImageSegmentation.from_pretrained(
            local_dir, trust_remote_code=True
        )
        model.to("cuda")
        return {"model": model}

    elif model_type == "vae":
        from diffusers import AutoencoderKL

        vae = AutoencoderKL.from_pretrained(local_dir, torch_dtype=torch.float16)
        vae.to("cuda")
        return {"vae": vae}

    else:
        raise ValueError(f"Unknown model type: {model_type}")


@app.post("/models/{model_name}/unload")
async def unload_model(model_name: str):
    import torch

    if model_name not in loaded_models:
        raise HTTPException(status_code=400, detail="Model not loaded")

    del loaded_models[model_name]
    torch.cuda.empty_cache()
    return {"status": "unloaded", "model": model_name}


# ── Inference endpoints ─────────────────────────────────────────────────────

@app.post("/v1/chat/completions")
async def chat_completions(request: TextRequest):
    model_name = request.model
    if model_name not in loaded_models:
        raise HTTPException(status_code=400, detail=f"Model '{model_name}' not loaded. POST /models/{model_name}/load first.")

    info = MODELS.get(model_name)
    if not info or info["type"] not in ("llm", "vlm"):
        raise HTTPException(status_code=400, detail="This endpoint is for text/VLM models only.")

    try:
        result = await asyncio.to_thread(
            _run_text_inference, model_name, request
        )
        return result
    except Exception as e:
        logger.error(f"Inference error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _run_text_inference(model_name: str, request: TextRequest):
    import torch

    ctx = loaded_models[model_name]
    model = ctx["model"]
    tokenizer = ctx.get("tokenizer") or ctx.get("processor")

    messages = [{"role": "user", "content": request.prompt}]
    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(text, return_tensors="pt").to(model.device)

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=request.max_tokens,
            temperature=request.temperature,
            do_sample=request.temperature > 0,
        )

    response_text = tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)

    return {
        "model": model_name,
        "choices": [
            {
                "message": {"role": "assistant", "content": response_text},
                "finish_reason": "stop",
            }
        ],
    }


@app.post("/v1/images/generate")
async def generate_image(request: ImageRequest):
    import base64
    from io import BytesIO

    model_name = request.model
    if model_name not in loaded_models:
        raise HTTPException(status_code=400, detail=f"Model '{model_name}' not loaded.")

    info = MODELS.get(model_name)
    if not info or info["type"] != "diffusion":
        raise HTTPException(status_code=400, detail="This endpoint is for diffusion models only.")

    try:
        image = await asyncio.to_thread(
            _run_image_inference, model_name, request
        )
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        img_base64 = base64.b64encode(buffer.getvalue()).decode()

        return {"model": model_name, "image": img_base64}
    except Exception as e:
        logger.error(f"Image generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _run_image_inference(model_name: str, request: ImageRequest):
    import torch

    ctx = loaded_models[model_name]
    pipe = ctx["pipeline"]

    with torch.no_grad():
        result = pipe(
            prompt=request.prompt,
            width=request.width,
            height=request.height,
            num_inference_steps=request.steps,
            guidance_scale=request.guidance_scale,
        )

    return result.images[0]


@app.post("/v1/background/remove")
async def remove_background(image: UploadFile = File(...)):
    import torch
    from PIL import Image
    from io import BytesIO
    import base64
    from torchvision import transforms

    if "birefnet" not in loaded_models:
        raise HTTPException(status_code=400, detail="BiRefNet not loaded. POST /models/birefnet/load first.")

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
        img_base64 = base64.b64encode(buffer.getvalue()).decode()

        return {"image": img_base64}
    except Exception as e:
        logger.error(f"Background removal error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
