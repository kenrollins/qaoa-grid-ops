"""Stub GB10 vLLM orchestrator — same shapes as the real :9000."""
import os
import time
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()
ALL = ["nemotron-120b", "voicechat-11b", "gemma-26b-moe", "qwen35-a3b", "llama-70b"]
LOADED = set((os.getenv("STUB_LOADED") or "nemotron-120b,qwen35-a3b").split(","))
DELAY = float(os.getenv("STUB_DELAY", "0"))
FAIL_LOAD = {x for x in (os.getenv("STUB_FAIL_LOAD") or "").split(",") if x}

class Req(BaseModel):
    model_id: str

@app.get("/status")
def status():
    return {"models": [{"model_id": m, "name": m, "loaded": m in LOADED,
                        "port": 8000, "health": "healthy" if m in LOADED else "unknown"}
                       for m in ALL],
            "memory": {"used_gb": 117.7 if LOADED else 3.9}}

@app.post("/unload")
def unload(r: Req):
    time.sleep(DELAY)
    LOADED.discard(r.model_id)
    return {"status": "unloaded", "model_id": r.model_id}

@app.post("/load")
def load(r: Req):
    time.sleep(DELAY)
    if r.model_id in FAIL_LOAD:
        from fastapi import HTTPException
        raise HTTPException(500, f"Failed to load {r.model_id}")
    LOADED.add(r.model_id)
    return {"status": "loaded", "model_id": r.model_id}
