def join_markdown_sections(sections: list[str]) -> str:
    return "\n\n---\n\n".join(section.strip() for section in sections if section.strip())

