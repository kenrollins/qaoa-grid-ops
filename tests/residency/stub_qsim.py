"""Stub gridops-qsim — only /health, which is all the control plane reads."""
from fastapi import FastAPI
app = FastAPI()

@app.get("/health")
def health():
    return {"ok": True, "device": "stub", "max_qubits": 30,
            "free_memory_bytes": 121 * 2**30, "total_memory_bytes": 128 * 2**30}
