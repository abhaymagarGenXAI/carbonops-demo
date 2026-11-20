# CarbonOps API (FastAPI + PyMongo)

See the repository root README for the full run guide. Quick reference:

    python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
    pip install -r requirements.txt
    cp .env.example .env            # or copy your existing .env.local here; then set JWT_SECRET_KEY
    python -m app.seed.seed         # idempotent; never overwrites existing documents
    uvicorn app.main:app --reload --port 8000

    pytest                          # uses mongomock, no database needed

Interactive docs: http://localhost:8000/docs  (click *Authorize*, paste the `accessToken` from `POST /api/v1/auth/login`).
