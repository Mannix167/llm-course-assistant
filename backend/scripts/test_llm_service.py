from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.services.llm_service import LLMService


def main() -> None:
    parser = argparse.ArgumentParser(description="Test LLMService text/json/vision calls.")
    parser.add_argument("--provider", default="kimi", help="Provider name, e.g. kimi or glm")
    parser.add_argument("--model", default="Kimi-K2.5", help="Model name")
    parser.add_argument(
        "--image",
        default=r"D:\course learn agent\backend\storage\course_001\images\page_010.png",
        help="Local image path for vision testing",
    )
    parser.add_argument("--skip-network", action="store_true", help="Only print readiness and skip live LLM calls")
    args = parser.parse_args()

    llm = LLMService()
    readiness = llm.check_provider_ready(provider=args.provider, model=args.model)
    result: dict[str, object] = {"readiness": readiness}

    if not args.skip_network:
        text_messages = [
            {"role": "system", "content": "你是一个简洁的中文助手，只输出最终答案，不要展示思考过程。"},
            {"role": "user", "content": "请用一句中文说明什么是回归分析。"},
        ]
        json_messages = [
            {"role": "system", "content": "你是一个简洁的中文助手，只输出最终答案，不要展示思考过程。"},
            {"role": "user", "content": "请返回 JSON，字段为 topic 和 difficulty，主题是回归分析，难度是入门。"},
        ]
        vision_messages = [
            {"role": "system", "content": "你是一个简洁的中文助手，只输出最终答案，不要展示思考过程。"},
            {"role": "user", "content": "请用一句中文描述这张课件页主要展示了什么。"},
        ]

        result["text_response"] = llm.chat(
            messages=text_messages,
            provider=args.provider,
            model=args.model,
            temperature=0.1,
            max_tokens=800,
        )
        result["json_response"] = llm.chat_json(
            messages=json_messages,
            provider=args.provider,
            model=args.model,
            temperature=0.1,
            max_tokens=400,
        )
        result["vision_response"] = llm.vision_chat(
            messages=vision_messages,
            images=[args.image],
            provider=args.provider,
            model=args.model,
            temperature=0.1,
            max_tokens=800,
        )

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
