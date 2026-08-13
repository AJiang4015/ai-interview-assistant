"""Interview API endpoints."""

from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form

from app.api.schemas import BaseModel, Field

# --- Interview Schemas ---


class StartInterviewRequest(BaseModel):
    position: str = Field(..., description="Job position, e.g. Java后端")


class AnswerRequest(BaseModel):
    question_id: str
    answer: str = Field(..., min_length=1, max_length=10000)


class EndInterviewRequest(BaseModel):
    session_id: str


router = APIRouter(prefix="/api/interview")


def _get_service():
    from app.main import interview_service
    if interview_service is None:
        raise HTTPException(status_code=503, detail="Interview service not initialized")
    return interview_service


@router.post("/start")
async def start_interview(
    position: str = Form(...),
    resume_file: Optional[UploadFile] = File(None),
    jd_text: Optional[str] = Form(None),
):
    """Start a new interview session, optionally with resume+JD analysis."""
    try:
        service = _get_service()
        # Validate file type
        if resume_file and not resume_file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="仅支持PDF格式的简历文件")
        result = await service.start(position, resume_file=resume_file, jd_text=jd_text)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/answer")
async def submit_answer(req: AnswerRequest):
    """Submit an answer to the current question."""
    try:
        result = await _get_service().answer(req.question_id, req.answer)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/end")
async def end_interview(req: EndInterviewRequest):
    """Force-end an interview and generate report."""
    try:
        result = await _get_service().end(req.session_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/report/{session_id}")
async def get_report(session_id: str):
    """Get interview report."""
    try:
        report = await _get_service().get_report(session_id)
        if report is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return {"session_id": session_id, "report": report}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def list_history():
    """List recent interview sessions."""
    try:
        sessions = _get_service().history()
        return {"total": len(sessions), "sessions": sessions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))