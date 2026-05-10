# H-SEMAS Backend (Phase 1 MVP)

## Run (local)

```bash
py -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Then open `http://localhost:8000/api/health`.

## Notes

- Phase 1 uses a **simulated decision engine** so you can validate UI + streaming + heatmap schema before wiring real LLM APIs.
