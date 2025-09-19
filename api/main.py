# main.py
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import json
from typing import List, Dict, Any

app = FastAPI(title="SAARTHI API", version="1.0.0")

# CORS (relax in prod to your UI origin)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Load data at startup ----------
def _load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

CODES: List[Dict[str, Any]] = _load_json("seed_codes.json")
VALUESET: Dict[str, Any] = _load_json("valueset_demo.json")
CONCEPTMAP: Dict[str, Any] = _load_json("conceptmap_demo.json")

# For fast case-insensitive lookups
_VALUESET_INCLUDES_LOWER = {str(c).lower() for c in VALUESET.get("includes", [])}

# targetCode -> list of mappings
_MAPS_BY_TARGET: Dict[str, List[Dict[str, Any]]] = {}
for m in CONCEPTMAP.get("mappings", []):
    tgt = str(m.get("targetCode", "")).lower()
    if not tgt:
        continue
    _MAPS_BY_TARGET.setdefault(tgt, []).append(m)


# ---------- Health & Root ----------
@app.get("/")
def root():
    return {"ok": True, "message": "SAARTHI API is running", "version": app.version}

@app.get("/health")
def health():
    # Keep this simple since Render is probing /health
    return {"ok": True, "version": app.version}


# ---------- Codes Search (case-insensitive over code/display/synonyms) ----------
@app.get("/codes/search")
def search_codes(q: str):
    term = (q or "").strip().lower()
    if not term:
        return []

    out: List[Dict[str, Any]] = []
    for c in CODES:
        code = str(c.get("code", "")).lower()
        display = str(c.get("display", "")).lower()
        syns = [str(s).lower() for s in c.get("synonyms", [])]

        if term in code or term in display or any(term in s for s in syns):
            out.append(c)

    # cap to a reasonable number
    return out[:200]


# ---------- Single Code Validate ----------
@app.get("/codes/validate")
def validate_code(code: str):
    needle = (code or "").strip().lower()
    if not needle:
        raise HTTPException(status_code=400, detail="Missing code")

    # Exists in seed set?
    found = None
    for c in CODES:
        if str(c.get("code", "")).lower() == needle:
            found = c
            break

    exists = found is not None
    in_valueset = needle in _VALUESET_INCLUDES_LOWER

    # Get ConceptMap mappings for this target (by our convention, targetCode == the terminology code)
    mappings = _MAPS_BY_TARGET.get(needle, [])

    return {
        "code": code,
        "exists": exists,
        "inValueSet": in_valueset,
        "display": (found or {}).get("display"),
        "system": (found or {}).get("system"),
        "mappings": mappings,
    }


# ---------- ValueSet / ConceptMap ----------
@app.get("/valueset")
def get_valueset():
    return VALUESET

@app.get("/conceptmap")
def get_conceptmap():
    return CONCEPTMAP


# ---------- FHIR Bundle Summary ----------
@app.post("/bundle/summary")
async def bundle_summary(req: Request):
    try:
        bundle = await req.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    if bundle.get("resourceType") != "Bundle":
        raise HTTPException(status_code=400, detail="resourceType must be 'Bundle'")

    entries = bundle.get("entry", []) or []
    types = {}
    patient_ref = None
    encounter_ref = None
    conditions: List[Dict[str, Any]] = []
    procedures: List[Dict[str, Any]] = []
    observations: List[Dict[str, Any]] = []

    for e in entries:
        res = (e or {}).get("resource") or {}
        rtype = res.get("resourceType", "Unknown")
        types[rtype] = types.get(rtype, 0) + 1

        rid = res.get("id")
        if rtype == "Patient" and rid:
            patient_ref = f"Patient/{rid}"
        if rtype == "Encounter" and rid:
            encounter_ref = f"Encounter/{rid}"
        if rtype == "Condition":
            conditions.append(res)
        if rtype == "Procedure":
            procedures.append(res)
        if rtype == "Observation":
            observations.append(res)

    return {
        "counts": types,
        "patientRef": patient_ref,
        "encounterRef": encounter_ref,
        "conditions": conditions[:50],
        "procedures": procedures[:50],
        "observations": observations[:50],
    }


# ---------- Export FHIR ----------
@app.post("/export/fhir/bundle")
async def export_fhir_bundle(req: Request):
    try:
        bundle = await req.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    # Echo back as FHIR JSON
    return JSONResponse(content=bundle, media_type="application/fhir+json")

# Alias used by UI as fallback
@app.post("/export/bundle")
async def export_bundle(req: Request):
    try:
        bundle = await req.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    return JSONResponse(content=bundle, media_type="application/json")
