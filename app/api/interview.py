"""Interview API endpoints."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Form, Depends

from app.api.auth import get_current_user
from app.api.schemas import BaseModel, Field
from app.exceptions import AuthorizationError

# --- Interview Schemas ---


class StartInterviewRequest(BaseModel):
    position: str = Field(..., description="Job position, e.g. Java后端")


class AnswerRequest(BaseModel):
    question_id: str
    answer: str = Field(..., min_length=1, max_length=10000)
    generate_next: bool = True


class EndInterviewRequest(BaseModel):
    session_id: str


router = APIRouter(prefix="/api/interview", dependencies=[Depends(get_current_user)])


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
    current_user: dict = Depends(get_current_user),
):
    """Start a new interview session, optionally with resume+JD analysis."""
    try:
        service = _get_service()
        # Validate file type
        if resume_file and not resume_file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="仅支持PDF格式的简历文件")
        result = await service.start(position, username=current_user["username"],
                                     resume_file=resume_file, jd_text=jd_text)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/answer")
async def submit_answer(req: AnswerRequest, current_user: dict = Depends(get_current_user)):
    """Submit an answer to the current question."""
    try:
        result = await _get_service().answer(req.question_id, req.answer,
                                             generate_next=req.generate_next,
                                             username=current_user["username"])
        return result
    except AuthorizationError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/end")
async def end_interview(req: EndInterviewRequest, current_user: dict = Depends(get_current_user)):
    """Force-end an interview and generate report."""
    try:
        result = await _get_service().end(req.session_id, username=current_user["username"])
        return result
    except AuthorizationError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/report/{session_id}")
async def get_report(session_id: str, current_user: dict = Depends(get_current_user)):
    """Get interview report."""
    try:
        report = await _get_service().get_report(session_id, username=current_user["username"])
        if report is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return {"session_id": session_id, "report": report}
    except AuthorizationError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{session_id}/detail")
async def get_session_detail(session_id: str, current_user: dict = Depends(get_current_user)):
    """获取面试详情：会话元信息 + 逐题问答（纯读取，不生成报告、不改变状态）。"""
    try:
        detail = _get_service().get_detail(session_id, username=current_user["username"])
        if detail is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return detail
    except AuthorizationError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def list_history(limit: int = Query(default=20, ge=1, le=100),
                       current_user: dict = Depends(get_current_user)):
    """List recent interview sessions (scoped to current user)."""
    try:
        sessions = _get_service().history(username=current_user["username"], limit=limit)
        return {"total": len(sessions), "sessions": sessions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_stats(current_user: dict = Depends(get_current_user)):
    """跨场次知识点画像（当前用户的薄弱点聚合）。"""
    try:
        return _get_service().stats(username=current_user["username"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/today")
async def get_today(position: str | None = Query(default=None),
                    current_user: dict = Depends(get_current_user)):
    """今日一题：从当前用户历史薄弱分类生成一道复习题。

    岗位未传时优先取该用户最近一场面试岗位，兜底使用全局默认岗位。
    """
    try:
        return await _get_service().today(username=current_user["username"], position=position)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/coverage")
async def get_coverage(session_id: str = Query(...), position: str = Query(...),
                       current_user: dict = Depends(get_current_user)):
    """Get topic coverage statistics for an interview session."""
    try:
        service = _get_service()
        if not hasattr(service, 'topic_tracker') or not service.topic_tracker:
            return {"categories": {}, "weakest": None, "untouched": [], "total_covered": 0, "total_topics": 0}
        # 用户隔离：仅允许访问本人场次的主题覆盖
        if not service.store.owns_session(session_id, current_user["username"]):
            if service.store.get_session(session_id) is None:
                raise HTTPException(status_code=404, detail="Session not found")
            raise HTTPException(status_code=403, detail="无权访问该面试场次")
        coverage = service.topic_tracker.get_coverage(session_id, position)
        return coverage
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))