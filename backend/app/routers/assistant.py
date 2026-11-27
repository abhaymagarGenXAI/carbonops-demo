from __future__ import annotations

from fastapi import APIRouter
from pydantic import Field

from app.core.deps import CurrentUser, Db
from app.schemas.common import CamelModel
from app.services import assistant as svc
from app.services import assistant_tools as tools

router = APIRouter(prefix="/assistant", tags=["assistant"])


class AskIn(CamelModel):
    question: str = Field(min_length=3, max_length=500)


@router.get("/status", summary="Is the local Ollama server and model ready?")
def get_status(_: CurrentUser):
    return svc.status()


@router.get("/tools", summary="The read-only tools the assistant may call")
def get_tools(_: CurrentUser):
    return [{"name": n, "description": d, "parameters": list(p)} for n, (d, p, _fn) in tools.TOOLS.items()]


@router.post("/ask", summary="Ask a question; answered by a local model using only the app's calculated data")
def ask(body: AskIn, db: Db, user: CurrentUser):
    return svc.ask(db, user, body.question.strip())
