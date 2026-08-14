from fastapi import APIRouter, HTTPException

from app.api.schemas import BaseModel


class GenTestsetRequest(BaseModel):
    limit: int | None = None


class RunEvalRequest(BaseModel):
    configs: list[dict] | None = None


router = APIRouter(prefix="/api/eval")


def _get_eval_service():
    from app.main import evaluation_service
    if evaluation_service is None:
        raise HTTPException(status_code=503, detail="Evaluation service not initialized")
    return evaluation_service


@router.post("/generate-testset")
async def generate_testset(req: GenTestsetRequest):
    try:
        from app.main import testset_generator
        if testset_generator is None:
            raise HTTPException(status_code=503, detail="Testset generator not initialized")
        return await testset_generator.generate(limit=req.limit)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run")
async def run_eval(req: RunEvalRequest):
    try:
        return await _get_eval_service().run(req.configs)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reports")
async def list_reports():
    return {"reports": _get_eval_service().list_reports()}


@router.get("/reports/{name}")
async def get_report(name: str):
    report = _get_eval_service().get_report(name)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return report