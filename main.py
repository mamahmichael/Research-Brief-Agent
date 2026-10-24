"""HTTP API for the Research Brief Agent.

Run:  uvicorn main:app --reload
Docs: http://127.0.0.1:8000/docs
"""
import logging

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

# research logic lives in agent.py
from agent import Brief, QuotaExceededError, run_agent

logger = logging.getLogger("research_brief_api")
logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Research Brief Agent",
    description="Searches the web and returns a structured research brief with sources.",
    version="0.5.0",
)


class BriefRequest(BaseModel):
    # strip spaces so "   " fails min_length
    model_config = ConfigDict(str_strip_whitespace=True)

    # bad input gets a 422 before any model call, so it costs no quota
    topic: str = Field(
        min_length=3,
        max_length=500,
        description="The topic or question to research.",
        examples=["What are the main benefits and risks of intermittent fasting?"],
    )


@app.get("/health")
def health() -> dict:
    """Health check. Makes no model calls."""
    return {"status": "ok"}


# plain def, not async: the agent makes blocking calls, and FastAPI runs
# plain functions in a worker thread
@app.post("/brief", response_model=Brief)
def create_brief(request: BriefRequest) -> Brief:
    logger.info("brief requested: %r", request.topic)
    try:
        return run_agent(request.topic)
    except QuotaExceededError as e:
        # quota or rate limit: message is safe to show the caller
        raise HTTPException(status_code=429, detail=str(e))
    except Exception:
        # anything else: log the details, return a generic 502
        logger.exception("agent failed for topic %r", request.topic)
        raise HTTPException(
            status_code=502,
            detail="The agent could not produce a brief. Please try again.",
        )