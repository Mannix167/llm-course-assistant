from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.database.db import SessionLocal, init_db
from app.database.models import Course
from app.services.course_service import CourseService
from app.services.report_service import ReportService


class FakeStandardLLM:
    def parse_json_text(self, content: str) -> dict[str, Any]:
        return json.loads(content)

    def chat_json_for_purpose(
        self,
        purpose: str,
        messages: list[dict[str, Any]],
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        return {
            "outline_markdown": (
                "## 课程目录\n\n"
                "| 章节 | 页码范围 | 内容总结 |\n"
                "|---|---|---|\n"
                "| 第一章 导论与模型背景 | 1-8 | 介绍经典单方程模型的学习目标、基本概念和建模背景。 |\n"
                "| 第二章 模型设定与估计思路 | 9-16 | 解释模型形式、变量关系和估计的核心步骤。 |"
            ),
            "chapters": [
                {
                    "title": "第一章 导论与模型背景",
                    "start_page": 1,
                    "end_page": 8,
                    "content_summary": "介绍经典单方程模型的学习目标、基本概念和建模背景。",
                    "key_points": ["单方程模型", "变量关系", "学习目标"],
                },
                {
                    "title": "第二章 模型设定与估计思路",
                    "start_page": 9,
                    "end_page": 16,
                    "content_summary": "解释模型形式、变量关系和估计的核心步骤。",
                    "key_points": ["模型设定", "参数估计", "结果解释"],
                },
            ],
        }

    def chat_for_purpose(
        self,
        purpose: str,
        messages: list[dict[str, Any]],
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ) -> str:
        prompt = messages[-1]["content"]
        if "overall_summary_markdown" in str(prompt):
            return json.dumps(self.chat_json_for_purpose(purpose, messages, temperature, max_tokens), ensure_ascii=False)
        title = "章节讲解"
        for line in str(prompt).splitlines():
            if line.startswith("章节标题："):
                title = line.replace("章节标题：", "").strip()
                break
        return (
            f"### {title}\n\n"
            "本章讲解由标准模式链路生成。它会读取该章节对应页码范围内的净化文本，"
            "按课件顺序解释核心概念、变量关系和学习重点。\n\n"
            "#### 1. 本章在讲什么\n\n"
            "本章围绕课件中的主要概念展开，先建立问题背景，再说明模型或方法的基本结构。\n\n"
            "#### 2. 学习重点\n\n"
            "- 理解课件术语的含义\n"
            "- 把握页面之间的逻辑顺序\n"
            "- 形成可复习的知识框架"
        )

    def vision_chat_for_purpose(
        self,
        purpose: str,
        messages: list[dict[str, Any]],
        images: list[str],
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> str:
        return json.dumps({"insertions": []}, ensure_ascii=False)


def ensure_sample_course() -> int:
    init_db()
    pdf_path = Path(r"D:\course learn agent\samples\3 经典单方程模型 1.pdf")
    with SessionLocal() as db:
        existing = db.query(Course).filter(Course.file_name == pdf_path.name, Course.status == "parsed").first()
        if existing is not None:
            return existing.id

        course = CourseService().create_uploaded_course(db, pdf_path, original_file_name=pdf_path.name)
        course = CourseService().parse_existing_course(db, course.id)
        return course.id


def main() -> None:
    course_id = ensure_sample_course()
    with SessionLocal() as db:
        report = ReportService(llm_service=FakeStandardLLM()).create_report(
            db=db,
            course_id=course_id,
            mode="standard",
        )
        detail = ReportService().get_report_detail(db, report.id)
        steps = ReportService().list_report_steps(db, report.id)

    print(
        json.dumps(
            {
                "course_id": course_id,
                "report_id": report.id,
                "status": report.status,
                "step_names": [step["step_name"] for step in steps],
                "report_path": report.report_path,
                "final_markdown_preview": (detail["final_markdown"] or "")[:1200],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
