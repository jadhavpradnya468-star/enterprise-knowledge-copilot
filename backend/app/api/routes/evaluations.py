import json
from pathlib import Path

from fastapi import APIRouter, Depends

from app.agents.deps import Deps
from app.api.dependencies import get_current_user, get_deps
from app.api.errors import AppError
from app.db import User
from app.evaluation.runner import run_evaluation

router = APIRouter(prefix="/evaluations", tags=["evaluations"])


@router.post("/run")
def run_eval(user: User = Depends(get_current_user), deps: Deps = Depends(get_deps)):
    if not deps.settings.eval_enabled:
        raise AppError(403, "evaluation_disabled", "Evaluation is disabled (EVAL_ENABLED=false).")
    return run_evaluation(deps)


@router.get("/latest")
def latest_report(user: User = Depends(get_current_user), deps: Deps = Depends(get_deps)):
    reports = sorted(Path(deps.settings.eval_report_dir).glob("eval_*.json"))
    if not reports:
        raise AppError(404, "no_reports", "No evaluation report exists yet.")
    return json.loads(reports[-1].read_text())
