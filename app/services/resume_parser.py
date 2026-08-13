"""Resume/JD parsing and matching analysis service.

Parses PDF resumes, extracts structured info from JD text,
and performs matching analysis using LLM.
"""

import json
import re
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import UploadFile

from app.services.llm_client import LLMClient
from app.utils.logger import get_logger

logger = get_logger(__name__)

# --- Prompt templates ---

RESUME_PARSE_PROMPT = """请从以下简历文本中提取结构化信息，以JSON格式输出（不要包含其他内容）：

{resume_text}

请按以下JSON格式输出：
{{
    "skills": ["Java", "Spring", ...],
    "projects": [
        {{
            "name": "项目名称",
            "description": "项目简介",
            "technologies": ["技术栈1", "技术栈2"]
        }}
    ],
    "experience": [
        {{
            "company": "公司名",
            "role": "职位",
            "duration": "时间范围",
            "description": "工作内容简述"
        }}
    ],
    "education": [
        {{
            "school": "学校名",
            "major": "专业",
            "degree": "学历",
            "year": "毕业年份"
        }}
    ],
    "summary": "候选人整体背景总结（30字以内）"
}}
"""

JD_PARSE_PROMPT = """请从以下招聘JD文本中提取结构化需求，以JSON格式输出（不要包含其他内容）：

{jd_text}

请按以下JSON格式输出：
{{
    "required_skills": ["Java", "Spring", ...],
    "preferred_skills": ["Redis", "Docker", ...],
    "responsibilities": ["负责XXX开发", ...],
    "experience_required": "3-5年",
    "education_required": "本科及以上",
    "key_requirements": ["核心要求1", "核心要求2"],
    "summary": "岗位整体要求总结（30字以内）"
}}
"""

MATCH_ANALYSIS_PROMPT = """请根据以下候选人的简历信息和招聘JD需求，进行详细的匹配分析，以JSON格式输出。

【简历信息】
{resume_json}

【JD需求】
{jd_json}

请按以下JSON格式输出：
{{
    "matched_skills": ["JD要求且候选人具备的技能1", "技能2"],
    "missing_skills": ["JD要求但候选人缺失的技能1", "技能2"],
    "partial_skills": ["JD要求但候选人仅部分具备的技能"],
    "project_match": "项目经验与岗位职责的匹配度评价（30字以内）",
    "experience_match": "工作年限/经验匹配度评价（20字以内）",
    "strong_areas": ["候选人具备的突出优势1", "优势2"],
    "risk_areas": ["高风险追问方向1", "方向2"],
    "overall_match": "high/medium/low",
    "interview_focus": "面试中应重点考察的方向（50字以内）"
}}
"""


def _parse_json(text: str) -> Optional[dict]:
    """Extract JSON from LLM response (handles markdown code blocks)."""
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"(\{.*\})", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    return None


class ResumeParser:
    """Resume/JD parsing and matching analysis service."""

    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def extract_pdf_text(self, file: UploadFile) -> str:
        """Extract text from a PDF file using pypdf."""
        try:
            from pypdf import PdfReader

            # Save uploaded file to temp location
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                content = await file.read()
                tmp.write(content)
                tmp_path = tmp.name

            try:
                reader = PdfReader(tmp_path)
                text_parts = []
                for page in reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
                return "\n".join(text_parts)
            finally:
                Path(tmp_path).unlink(missing_ok=True)
        except Exception as e:
            logger.error(f"PDF text extraction failed: {e}")
            return ""

    async def parse_resume(self, text: str) -> dict:
        """Parse resume text into structured info using LLM."""
        if not text.strip():
            return {}
        prompt = RESUME_PARSE_PROMPT.format(resume_text=text[:4000])
        result = await self.llm.chat(prompt)
        parsed = _parse_json(result)
        if not parsed:
            logger.warning(f"Failed to parse resume JSON, raw: {result[:200]}")
            return {"skills": [], "projects": [], "experience": [], "summary": text[:100]}
        return parsed

    async def parse_jd(self, text: str) -> dict:
        """Parse JD text into structured requirements using LLM."""
        if not text.strip():
            return {}
        prompt = JD_PARSE_PROMPT.format(jd_text=text[:3000])
        result = await self.llm.chat(prompt)
        parsed = _parse_json(result)
        if not parsed:
            logger.warning(f"Failed to parse JD JSON, raw: {result[:200]}")
            return {"required_skills": [], "key_requirements": [], "summary": text[:100]}
        return parsed

    async def analyze_match(self, resume: dict, jd: dict) -> dict:
        """Analyze match between resume and JD using LLM."""
        if not resume or not jd:
            return {}
        prompt = MATCH_ANALYSIS_PROMPT.format(
            resume_json=json.dumps(resume, ensure_ascii=False, indent=2),
            jd_json=json.dumps(jd, ensure_ascii=False, indent=2),
        )
        result = await self.llm.chat(prompt)
        parsed = _parse_json(result)
        if not parsed:
            logger.warning(f"Failed to parse match analysis JSON, raw: {result[:200]}")
            return {"matched_skills": [], "missing_skills": [], "overall_match": "unknown"}
        return parsed