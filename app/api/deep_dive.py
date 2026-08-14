from typing import Literal

from fastapi import APIRouter, HTTPException, UploadFile, File

from app.api.schemas import BaseModel, Field


class DeepDiveStartRequest(BaseModel):
    project_name: str
    tech_point: str
    description: str = ""


class DeepDiveAnswerRequest(BaseModel):
    question_id: str
    answer: str = Field(..., min_length=1, max_length=10000)
    action: Literal["continue", "end"] = "continue"  # continue | end


class DeepDiveEndRequest(BaseModel):
    session_id: str


router = APIRouter(prefix="/api/deepdive")


def _get_service():
    from app.main import deep_dive_service
    if deep_dive_service is None:
        raise HTTPException(status_code=503, detail="Deep dive service not initialized")
    return deep_dive_service


@router.post("/analyze")
async def analyze_resume(resume_file: UploadFile = File(...)):
    """解析简历，返回项目与技术点列表。"""
    try:
        from app.main import resume_parser
        text = await resume_parser.extract_pdf_text(resume_file)
        analysis = await resume_parser.parse_resume(text)
        service = _get_service()
        projects = service.extract_projects(analysis)
        return {"projects": projects}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/start")
async def start_dive(req: DeepDiveStartRequest):
    try:
        return await _get_service().start(req.project_name, req.tech_point, req.description)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/answer")
async def answer_dive(req: DeepDiveAnswerRequest):
    try:
        return await _get_service().answer(req.question_id, req.answer, req.action)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/end")
async def end_dive(req: DeepDiveEndRequest):
    try:
        return await _get_service().end(req.session_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))