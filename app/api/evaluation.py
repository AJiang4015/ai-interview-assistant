from fastapi import APIRouter, HTTPException, Depends

from app.api.auth import get_current_user
from app.api.schemas import BaseModel


class GenTestsetRequest(BaseModel):
    limit: int | None = None


class RunEvalRequest(BaseModel):
    configs: list[dict] | None = None


router = APIRouter(prefix="/api/eval", dependencies=[Depends(get_current_user)])


def _get_eval_service():
    from app.main import evaluation_service
    if evaluation_service is None:
        raise HTTPException(status_code=503, detail="Evaluation service not initialized")
    return evaluation_service


@router.post("/generate-testset")
async def generate_testset(req: GenTestsetRequest):
    try:
        from app.main import testset_generator, doc_store
        if testset_generator is None:
            raise HTTPException(status_code=503, detail="Testset generator not initialized")
        data = doc_store.load()
        testset_generator.chunks = (
            [{"content": c["content"], "source": c["source_file"]} for c in data["chunks"]]
            if data and data.get("chunks") else []
        )
        return await testset_generator.generate(limit=req.limit)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run")
async def run_eval(req: RunEvalRequest):
    try:
        import asyncio
        svc = _get_eval_service()
        job_id = svc.create_job(req.configs)
        asyncio.create_task(svc.run_async(job_id, req.configs))
        return {"job_id": job_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    job = _get_eval_service().get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/reports")
async def list_reports():
    return {"reports": _get_eval_service().list_reports()}


@router.get("/reports/{name}")
async def get_report(name: str):
    report = _get_eval_service().get_report(name)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return report