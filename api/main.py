# api/main.py
# FastAPI backend entry point
# Run with: uvicorn api.main:app --reload --port 8000

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import pipeline, leads, contacts, campaigns, analytics, places, interactions, discover, status
from .routes.queue import router as queue_router
from .routes import us_outreach

app = FastAPI(title="ClickCatalyst Ops API", version="1.0.0")

# Comma-separated browser origins allowed to call the API. Defaults to local dev.
# Set CORS_ALLOW_ORIGINS on Render to include the deployed dashboard origin, e.g.
#   http://localhost:3000,https://clickcatalyst-dashboard.onrender.com
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:3000").split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(pipeline.router,  prefix="/api/pipeline",  tags=["Pipeline"])
app.include_router(leads.router,     prefix="/api/leads",     tags=["Leads"])
app.include_router(contacts.router,  prefix="/api/contacts",  tags=["Contacts"])
app.include_router(campaigns.router, prefix="/api/campaigns", tags=["Campaigns"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["Analytics"])
app.include_router(places.router,       prefix="/api/places",       tags=["Places"])
app.include_router(interactions.router, prefix="/api/interactions", tags=["Interactions"])
app.include_router(discover.router,     prefix="/api/discover",     tags=["Discover"])
app.include_router(queue_router, prefix="/api/queue")
app.include_router(us_outreach.router, prefix="/api/us-outreach", tags=["US Outreach"])
app.include_router(status.router, prefix="/api/status", tags=["Status"])

@app.get("/api/health")
def health():
    return {"status": "ok"}