from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts"
PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


class PromptLoaderError(ValueError):
    pass


@dataclass(slots=True)
class PromptTemplate:
    name: str
    content: str

    def placeholders(self) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()
        for match in PLACEHOLDER_RE.finditer(self.content):
            key = match.group(1)
            if key not in seen:
                seen.add(key)
                ordered.append(key)
        return ordered

    def render(self, **variables: object) -> str:
        required = self.placeholders()
        missing = [key for key in required if key not in variables]
        if missing:
            raise PromptLoaderError(
                f"Missing prompt variables for '{self.name}': {', '.join(missing)}"
            )

        def replace(match: re.Match[str]) -> str:
            key = match.group(1)
            value = variables.get(key, "")
            return str(value)

        return PLACEHOLDER_RE.sub(replace, self.content)


def get_prompt_path(name: str) -> Path:
    prompt_path = (PROMPT_DIR / name).resolve()
    if prompt_path.parent != PROMPT_DIR.resolve():
        raise PromptLoaderError(f"Prompt path escapes prompt directory: {name}")
    if not prompt_path.exists():
        raise PromptLoaderError(f"Prompt file not found: {name}")
    return prompt_path


def load_prompt_template(name: str) -> PromptTemplate:
    prompt_path = get_prompt_path(name)
    return PromptTemplate(name=name, content=prompt_path.read_text(encoding="utf-8"))


def load_prompt(name: str, **variables: object) -> str:
    template = load_prompt_template(name)
    if template.placeholders():
        return template.render(**variables)
    return template.content


def list_prompts() -> list[str]:
    return sorted(path.name for path in PROMPT_DIR.glob("*.md"))
