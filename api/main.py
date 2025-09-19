from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import json
import os

app = FastAPI()

# Allow all CORS origins (important for Render deployments)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load data once on startup
with open("seed_codes.json", encoding="utf-8") as f:
    SEED_CODES = json.load(f)

with open("valueset_demo.json", encoding="utf-8") as f:
    VALUESET = json.load(f)

with open("conceptmap_demo.json", encoding="utf-8") as f:
    CONCEPTMAP = json.load(f)

@app.get("/")
def root():
    return {"message": "SAARTHI API is running."}

@app.get("/codes/search")
def search_codes(q: str):
    q_lower = q.lower()
    results = [
        code for code in SEED_CODES
        if q_lower in code.get("id", "").lower()
        or q_lower in code.get("term", "").lower()
        or q_lower in code.get("description", "").lower()
    ]
    return results

@app.get("/valueset")
def get_valueset():
    return VALUESET

@app.get("/conceptmap")
def get_conceptmap():
    return CONCEPTMAP

@app.post("/validate")
async def validate_code(request: Request):
    body = await request.json()
    code = body.get("code", "").strip().lower()
    valueset_ids = {c.lower() for c in VALUESET.get("includes", [])}
    is_valid = code in valueset_ids
    return {"code": code, "valid": is_valid}

@app.post("/validate/all")
async def validate_all_codes(request: Request):
    body = await request.json()
    codes = body.get("codes", [])
    valueset_ids = {c.lower() for c in VALUESET.get("includes", [])}
    result = [
        {"code": code, "valid": code.lower() in valueset_ids}
        for code in codes
    ]
    return result

@app.post("/summarize")
async def summarize_bundle(request: Request):
    bundle = await request.json()
    if bundle.get("resourceType") != "Bundle":
        return JSONResponse(status_code=400, content={"error": "Invalid Bundle"})
    
    counts = {}
    entries = bundle.get("entry", [])
    for entry in entries:
        res = entry.get("resource", {})
        rtype = res.get("resourceType", "Unknown")
        counts[rtype] = counts.get(rtype, 0) + 1

    return {"total": len(entries), "types": counts}
