"""ZeroRelay Cloud control plane API (scaffold — Sprint 2 C1)."""

from fastapi import FastAPI

app = FastAPI(title="ZeroRelay Cloud API", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "ok", "service": "zerorelay-cloud-api"}
