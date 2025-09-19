# api/main.py
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import json
from typing import Any, Dict, List

app = FastAPI(title="SAARTHI API", version="1.1.0")

# ---------------- CORS ----------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- Helpers ----------------
def _load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def _norm_codes(raw: Any) -> List[Dict[str, Any]]:
    """
    Accepts any of:
      - [{"code":"X","display":"Y", ...}, ...]
      - {"codes":[...]}
      - ["X","Y", ...]  (strings)
      - {"X": {...}, "Y": {...}} (object map)
    Returns list of dicts with keys: code, display, synonyms(list), system.
    """
    # unwrap common containers
    if isinstance(raw, dict):
        if "codes" in raw:
            items = raw["codes"]
        elif "data" in raw:
            items = raw["data"]
        elif "items" in raw:
            items = raw["items"]
        else:
            # Maybe a code map: { "A": {...}, "B": {...} }
            items = list(raw.values())
    else:
        items = raw

    if not isinstance(items, list):
        items = [items]

    out: List[Dict[str, Any]] = []
    for x in items:
        if isinstance(x, dict):
            code = x.get("code") or x.get("id") or x.get("Code") or x.get("ID") or ""
            display = (
                x.get("display")
                or x.get("term")
                or x.get("name")
                or x.get("description")
                or str(code)
            )
            syns = x.get("synonyms") or x.get("Synonyms") or []
            if isinstance(syns, str):
                syns = [syns]
            system = x.get("system") or x.get("System") or "urn:icd:icd11:tm"
            out.append(
                {
                    "code": str(code),
                    "display": str(display),
                    "synonyms": [str(s) for s in syns],
                    "system": str(system),
                }
            )
        elif isinstance(x, str):
            out.append(
                {
                    "code": x,
                    "display": x,
                    "synonyms": [],
                    "system": "urn:icd:icd11:tm",
                }
            )
    return out

def _norm_valueset(raw: Any) -> Dict[str, Any]:
    """
    Ensures .includes is a list of strings (codes).
    Accepts shapes like {includes:[...]}, {codes:[...]}, list[str], etc.
    """
    includes: List[str] = []
    if isinstance(raw, dict):
        if isinstance(raw.get("includes"), list):
            includes = raw["includes"]
        elif isinstance(raw.get("codes"), list):
            includes = raw["codes"]
        elif isinstance(raw.get("data"), list):
            includes = raw["data"]
        else:
            # try to find any list of strings inside
            for v in raw.values():
                if isinstance(v, list) and all(isinstance(i, str) for i in v):
                    includes = v
                    break
    elif isinstance(raw, list) and all(isinstance(i, str) for i in raw):
        includes = raw

    includes = [str(c) for c in includes]
    return {"resourceType": "ValueSet", **(raw if isinstance(raw, dict) else {}), "includes": includes}

def _norm_conceptmap(raw: Any) -> Dict[str, Any]:
    """
    Ensures .mappings is a list of {sourceCode, targetCode, relation}.
    Accepts {mappings:[...]}, list[...] etc.
    """
    mappings: List[Dict[str, Any]] = []
    if isinstance(raw, dict):
        m = raw.get("mappings")
        if isinstance(m, list):
            mappings = m
        else:
            # maybe raw itself is a list
            pass
    if not mappings and isinstance(raw, list):
        mappings = raw

    norm_maps: List[Dict[str, Any]] = []
    for m in mappings:
        if not isinstance(m, dict):
            continue
        norm_maps.append(
            {
                "sourceCode": str(m.get("sourceCode", "")),
                "targetCode": str(m.get("targetCode", "")),
                "relation": str(m.get("relation", "equivalent")),
            }
        )
    if isinstance(raw, dict):
        return {"resourceType": "ConceptMap", **raw, "mappings": norm_maps}
    else:
        return {"resourceType": "ConceptMap", "mappings": norm_maps}

# ---------------- Load data ----------------
RAW_CODES = _load_json("seed_codes.json")
RAW_VALUESET = _load_json("valueset_demo.json")
RAW_CONCEPTMAP = _load_json("conceptmap_demo.json")

CODES = _norm_codes(RAW_CODES)
VALUESET = _norm_valueset(RAW_VALUESET)
CONCEPTMAP = _norm_conceptmap(RAW_CONCEPTMAP)

_VALUESET_INCLUDES_LOWER = {c.lower() for c in VALUESET.get("includes", [])}

# index ConceptMap by target (lowercased)
_MAPS_BY_TARGET: Dict[str, List[Dict[str, Any]]] = {}
for m in CONCEPTMAP.get("mappings", []):
    tgt = str(m.get("targetCode", "")).lower()
    if not tgt:
        continue
    _MAPS_BY_TARGET.setdefault(tgt, []).append(m)

# ---------------- Health & root ----------------
@app.get("/")
def root():
    return {"ok": True, "message": "SAARTHI API is running", "version": app.version}

@app.get("/health")
def health():
    return {"ok": True, "version": app.version}

# ---------------- Codes ----------------
@app.get("/codes/search")
def search_codes(q: str):
    term = (q or "").strip().lower()
    if not term:
        return []
    out: List[Dict[str, Any]] = []
    for c in CODES:
        code = c["code"].lower()
        display = c["display"].lower()
        syns = [s.lower() for s in c.get("synonyms", [])]
        if term in code or term in display or any(term in s for s in syns):
            out.append(c)
    return out[:200]

@app.get("/codes/validate")
def validate_code(code: str):
    needle = (code or "").strip().lower()
    if not needle:
        raise HTTPException(status_code=400, detail="Missing code")

    found = next((c for c in CODES if c["code"].lower() == needle), None)
    exists = found is not None
    in_valueset = needle in _VALUESET_INCLUDES_LOWER
    mappings = _MAPS_BY_TARGET.get(needle, [])

    return {
        "code": code,
        "exists": exists,
        "inValueSet": in_valueset,
        "display": (found or {}).get("display"),
        "system": (found or {}).get("system"),
        "mappings": mappings,
    }

# ---------------- ValueSet / ConceptMap ----------------
@app.get("/valueset")
def get_valueset():
    return VALUESET

@app.get("/conceptmap")
def get_conceptmap():
    return CONCEPTMAP

# ---------------- FHIR Bundle Summary ----------------
@app.post("/bundle/summary")
async def bundle_summary(req: Request):
    try:
        bundle = await req.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    if bundle.get("resourceType") != "Bundle":
        raise HTTPException(status_code=400, detail="resourceType must be 'Bundle'")

    entries = bundle.get("entry", []) or []
    counts: Dict[str, int] = {}
    patient_ref = None
    encounter_ref = None
    conditions: List[Dict[str, Any]] = []
    procedures: List[Dict[str, Any]] = []
    observations: List[Dict[str, Any]] = []

    for e in entries:
        res = (e or {}).get("resource") or {}
        rtype = res.get("resourceType", "Unknown")
        counts[rtype] = counts.get(rtype, 0) + 1

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
        "counts": counts,
        "patientRef": patient_ref,
        "encounterRef": encounter_ref,
        "conditions": conditions[:50],
        "procedures": procedures[:50],
        "observations": observations[:50],
    }

# ---------------- Export (echo) ----------------
@app.post("/export/fhir/bundle")
async def export_fhir_bundle(req: Request):
    try:
        bundle = await req.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    return JSONResponse(content=bundle, media_type="application/fhir+json")

@app.post("/export/bundle")
async def export_bundle(req: Request):
    try:
        bundle = await req.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    return JSONResponse(content=bundle, media_type="application/json")
