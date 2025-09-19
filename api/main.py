from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Any, Dict, List
import json

# ---------- Load demo data ----------
with open("seed_codes.json", "r", encoding="utf-8") as f:
    SEED_CODES: List[Dict[str, Any]] = json.load(f)["codes"]

with open("valueset_demo.json", "r", encoding="utf-8") as f:
    VALUESET: Dict[str, Any] = json.load(f)

with open("conceptmap_demo.json", "r", encoding="utf-8") as f:
    CONCEPTMAP: Dict[str, Any] = json.load(f)

# ---------- App & CORS ----------
app = FastAPI(title="SAARTHI Coding & FHIR API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # or restrict to your UI origin
    allow_credentials=False,
    allow_methods=["*"],        # GET, POST, OPTIONS, etc.
    allow_headers=["*"],        # Content-Type, Authorization, etc.
)

# ---------- Health ----------
@app.get("/health")
def health():
    return {"ok": True}

# ---------- ValueSet & ConceptMap ----------
@app.get("/valueset")
def get_valueset() -> Dict[str, Any]:
    return VALUESET

@app.get("/conceptmap")
def get_conceptmap() -> Dict[str, Any]:
    return CONCEPTMAP

# ---------- Code Search ----------
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
