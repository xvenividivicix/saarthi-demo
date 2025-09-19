from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import json, re

with open("seed_codes.json","r") as f:
    SEED = json.load(f)["codes"]
with open("valueset_demo.json","r") as f:
    VALUESET = json.load(f)

app = FastAPI(title="SAARTHI Coding & FHIR API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def score_match(text: str, item: Dict[str, Any]) -> float:
    text = text.lower()
    hay = [item["display"].lower()] + [s.lower() for s in item.get("synonyms",[])]
    score = 0.0
    for h in hay:
        if h in text:
            score = max(score, 1.0)
        else:
            tset = set(re.findall(r"[a-z]+", text))
            hset = set(re.findall(r"[a-z]+", h))
            if not hset: 
                continue
            overlap = len(tset & hset) / len(hset)
            score = max(score, overlap)
    return round(score, 2)

class EncounterContext(BaseModel):
    system: str = "urn:icd:icd11:tm"
    language: str = "en-IN"

class Observation(BaseModel):
    code: str
    value: str

class EncounterIn(BaseModel):
    patientRef: Optional[str] = "patient-123"
    encounterRef: Optional[str] = "enc-001"
    chiefComplaint: Optional[str] = ""
    diagnosisText: Optional[str] = ""
    therapyText: Optional[str] = ""
    observations: Optional[List[Observation]] = []
    context: Optional[EncounterContext] = EncounterContext()

class CodeCandidate(BaseModel):
    code: str
    display: str
    confidence: float
    why: str

class AutocodeResponse(BaseModel):
    conditions: List[CodeCandidate] = []
    procedures: List[CodeCandidate] = []
    notes: Optional[str] = None

class ValidateRequest(BaseModel):
    system: str
    codes: List[str]
    valueSet: Optional[str] = None

class ValidateResult(BaseModel):
    code: str
    valid: bool
    message: str

class ValidateResponse(BaseModel):
    valid: bool
    details: List[ValidateResult]
    systemVersion: str = "2025-05"

@app.get("/health")
def health():
    return {"status":"ok"}

@app.get("/codes/search")
def codes_search(text: str, system: str = "urn:icd:icd11:tm", limit: int = 10):
    items = [x for x in SEED if x["system"] == system]
    scored = []
    for it in items:
        sc = score_match(text, it)
        if sc > 0:
            scored.append({**it, "score": sc})
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit]

@app.post("/autocode")
def autocode(encounter: dict):
    text_blob = " ".join([encounter.get("encounter",{}).get(k,"") for k in ["chiefComplaint","diagnosisText","therapyText"]])
    conds, procs = [], []
    for it in SEED:
        sc = score_match(text_blob, it)
        if sc >= 0.25:
            cc = {"code":it["code"],"display":it["display"],"confidence":sc,"why":"text/synonym overlap"}
            if it["code"].startswith("TM2-PROC"):
                procs.append(cc)
            else:
                conds.append(cc)
    conds = sorted(conds, key=lambda x: x["confidence"], reverse=True)[:3]
    procs = sorted(procs, key=lambda x: x["confidence"], reverse=True)[:3]
    return {"conditions":conds,"procedures":procs,"notes":"Candidates ranked by simple lexical overlap."}

@app.post("/codes/validate")
def validate(req: ValidateRequest):
    allowed = set(VALUESET["includes"])
    details = []
    all_ok = True
    for c in req.codes:
        if c in allowed:
            details.append(ValidateResult(code=c, valid=True, message="OK").model_dump())
        else:
            details.append(ValidateResult(code=c, valid=False, message="Not in ValueSet").model_dump())
            all_ok = False
    return ValidateResponse(valid=all_ok, details=details).model_dump()

@app.post("/export/fhir/bundle")
def export_fhir(body: dict):
    def coding(item):
        return {"coding":[{"system": item.get("system","urn:icd:icd11:tm"), "code": item["code"], "display": item.get("display", "")}]}
    entry = [
        {"resource":{"resourceType":"Patient","id": body.get("patientRef","patient-123")}},
        {"resource":{"resourceType":"Encounter","id": body.get("encounterRef","enc-001")}},
    ]
    for c in body.get("conditions", []):
        entry.append({"resource":{"resourceType":"Condition","code": coding(c)}})
    for p in body.get("procedures", []):
        entry.append({"resource":{"resourceType":"Procedure","code": coding(p)}})
    for o in body.get("observations", []):
        entry.append({"resource":{"resourceType":"Observation","code":{"text":o.get("code")}, "valueString": o.get("value")}})
    return {"resourceType":"Bundle","type":"collection","entry":entry}

@app.post("/import/fhir/bundle")
def import_fhir(bundle: dict):
    patient = next((e["resource"]["id"] for e in bundle.get("entry",[]) if e["resource"]["resourceType"]=="Patient"), "patient-unknown")
    enc = next((e["resource"]["id"] for e in bundle.get("entry",[]) if e["resource"]["resourceType"]=="Encounter"), "enc-unknown")
    conditions, procedures, observations = [], [], []
    for e in bundle.get("entry", []):
        r = e.get("resource",{})
        if r.get("resourceType") == "Condition":
            cd = r.get("code",{}).get("coding",[{}])[0]
            conditions.append({"code": cd.get("code"), "display": cd.get("display"), "system": cd.get("system")})
        if r.get("resourceType") == "Procedure":
            cd = r.get("code",{}).get("coding",[{}])[0]
            procedures.append({"code": cd.get("code"), "display": cd.get("display"), "system": cd.get("system")})
        if r.get("resourceType") == "Observation":
            observations.append({"code": r.get("code",{}).get("text"), "value": r.get("valueString")})
    return {
        "patientRef": patient,
        "encounterRef": enc,
        "conditions": conditions,
        "procedures": procedures,
        "observations": observations
    }
