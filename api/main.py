from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from typing import Any, Dict, List, Optional
import json

# ---------- Load demo data ----------
with open("seed_codes.json", "r", encoding="utf-8") as f:
    SEED_CODES: List[Dict[str, Any]] = json.load(f)["codes"]

with open("valueset_demo.json", "r", encoding="utf-8") as f:
    VALUESET: Dict[str, Any] = json.load(f)

with open("conceptmap_demo.json", "r", encoding="utf-8") as f:
    CONCEPTMAP: Dict[str, Any] = json.load(f)

# For quick lookup
CODES_BY_CODE = {c.get("code"): c for c in SEED_CODES}
VALUESET_CODES = set(VALUESET.get("includes", []))
MAP_BY_TARGET = {}
for m in CONCEPTMAP.get("mappings", []):
    tgt = m.get("targetCode")
    if not tgt:
        continue
    MAP_BY_TARGET.setdefault(tgt, []).append(m)

# ---------- App & CORS ----------
app = FastAPI(title="SAARTHI Coding & FHIR API", version="1.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Health & metadata ----------
@app.get("/health")
def health():
    return {"ok": True, "version": "1.1.0"}

@app.get("/metadata")
def metadata():
    return {
        "seed_count": len(SEED_CODES),
        "valueset_count": len(VALUESET_CODES),
        "conceptmap_count": len(CONCEPTMAP.get("mappings", [])),
        "system": "urn:icd:icd11:tm",
    }

# ---------- ValueSet & ConceptMap ----------
@app.get("/valueset")
def get_valueset() -> Dict[str, Any]:
    return VALUESET

@app.get("/conceptmap")
def get_conceptmap() -> Dict[str, Any]:
    return CONCEPTMAP

# ---------- Code Search & Validate ----------
@app.get("/codes/search")
def search_codes(q: str = Query(..., min_length=1)) -> List[Dict[str, Any]]:
    needle = q.strip().lower()

    def match(c: Dict[str, Any]) -> bool:
        if needle in (c.get("code") or "").lower():
            return True
        if needle in (c.get("display") or "").lower():
            return True
        for s in c.get("synonyms") or []:
            if needle in (s or "").lower():
                return True
        return False

    return [c for c in SEED_CODES if match(c)]

@app.get("/codes/validate")
def validate_code(code: str = Query(..., min_length=1)) -> Dict[str, Any]:
    """
    Validate a code against seed, ValueSet, and ConceptMap.
    """
    info = CODES_BY_CODE.get(code)
    in_valueset = code in VALUESET_CODES
    mappings = MAP_BY_TARGET.get(code, [])
    return {
        "code": code,
        "exists": info is not None,
        "display": (info or {}).get("display"),
        "system": (info or {}).get("system"),
        "inValueSet": in_valueset,
        "mappings": mappings,
    }

# ---------- FHIR Bundle → Summary ----------
@app.post("/bundle/summary")
def bundle_summary(bundle: Dict[str, Any]) -> Dict[str, Any]:
    if bundle.get("resourceType") != "Bundle":
        raise HTTPException(status_code=400, detail="Expected a FHIR Bundle")

    patient_ref = None
    enc_ref = None
    conditions: List[Dict[str, Any]] = []
    procedures: List[Dict[str, Any]] = []
    observations: List[Dict[str, Any]] = []

    for e in bundle.get("entry", []):
        r = (e or {}).get("resource") or {}
        rt = r.get("resourceType")

        if rt == "Patient":
            patient_ref = r.get("id") or patient_ref

        elif rt == "Encounter":
            enc_ref = r.get("id") or enc_ref

        elif rt == "Condition":
            coding = (r.get("code") or {}).get("coding") or [{}]
            cd = coding[0] or {}
            conditions.append({
                "code": cd.get("code"),
                "display": cd.get("display"),
                "system": cd.get("system")
            })

        elif rt == "Procedure":
            coding = (r.get("code") or {}).get("coding") or [{}]
            cd = coding[0] or {}
            procedures.append({
                "code": cd.get("code"),
                "display": cd.get("display"),
                "system": cd.get("system")
            })

        elif rt == "Observation":
            observations.append({
                "code": (r.get("code") or {}).get("text"),
                "value": r.get("valueString")
            })

    return {
        "patientRef": patient_ref,
        "encounterRef": enc_ref,
        "conditions": conditions,
        "procedures": procedures,
        "observations": observations,
    }

# ---------- Export FHIR ----------
@app.post("/export/fhir/bundle")
def export_fhir_bundle(bundle: Dict[str, Any]):
    """
    Server-side echo/normalization of the input Bundle so clients can download
    with a correct content type. Adjust transformation here if needed.
    """
    if bundle.get("resourceType") != "Bundle":
        raise HTTPException(status_code=400, detail="Expected a FHIR Bundle")
    data = json.dumps(bundle, ensure_ascii=False, indent=2)
    return Response(content=data, media_type="application/fhir+json")

# Back-compat alias
@app.post("/export/bundle")
def export_bundle_alias(bundle: Dict[str, Any]):
    return export_fhir_bundle(bundle)
