from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.utils.prompt_loader import PromptLoaderError, list_prompts, load_prompt, load_prompt_template


def main() -> None:
    template = load_prompt_template("test_template.md")
    rendered = load_prompt(
        "test_template.md",
        system_role="课程分析助手",
        course_title="经典单方程模型",
        summary="这是一个用于测试 PromptLoader 的摘要。",
    )

    missing_error = None
    try:
        load_prompt("test_template.md", system_role="only-one")
    except PromptLoaderError as exc:
        missing_error = str(exc)

    print(
        json.dumps(
            {
                "available_prompts": list_prompts(),
                "template_placeholders": template.placeholders(),
                "rendered_prompt": rendered,
                "missing_error": missing_error,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
