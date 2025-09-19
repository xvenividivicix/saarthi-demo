# SAARTHI — Terminology & FHIR Demo (Production Ready)

A lightweight, production-oriented demo showcasing terminology search/validation and FHIR bundle workflows.  
Built using **FastAPI** (backend) and **React + Tailwind (static UI)** — deployable on **Render**, or any Docker/static host.

Run API, open UI, and demo full flow: Auto-code → Validate → Export FHIR → Import FHIR.
See /api/README.md for API details.

---

## ✨ Features

- 🔍 **Search codes** (with category filter & synonym support)
- ✅ **Validation list**: existence, ValueSet membership, ConceptMap mappings
- 🧩 **FHIR Bundle editor**: import, insert, summarize, validate, download, export
- 📦 **Reference data**: 888+ demo codes, large ValueSet & ConceptMap
- ⏬ **Export** as JSON / NDJSON / CSV
- ⚡ Zero build-step UI (static `index.html` with React + Tailwind via CDN)
- 🌐 Deploys seamlessly on Render with Docker + static frontend