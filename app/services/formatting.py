"""Безопасное форматирование текста ИИ для Telegram HTML."""
import html
import re


def markdown_to_telegram_html(text: str) -> str:
    """Преобразует используемый моделями базовый Markdown в Telegram HTML."""
    escaped = html.escape(text)

    # Модели нередко экранируют Markdown: \#, \*, \- и точку списка 1\.
    escaped = re.sub(r"\\([#*_\-.])", r"\1", escaped)

    lines: list[str] = []
    for line in escaped.splitlines():
        heading = re.match(r"^\s*#{1,6}\s+(.+?)\s*$", line)
        if heading:
            line = f"<b>{heading.group(1)}</b>"
        else:
            line = re.sub(r"^\s*[-*]\s+", "• ", line)
            line = re.sub(r"^\s*(\d+)\.\s+", r"\1. ", line)
        lines.append(line)

    result = "\n".join(lines)
    result = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", result)
    result = re.sub(r"(?<!\*)\*([^*\n]+?)\*(?!\*)", r"<i>\1</i>", result)
    return result
