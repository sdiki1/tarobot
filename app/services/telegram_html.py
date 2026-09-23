"""Проверка и нормализация HTML-разметки Telegram для текстов из админки.

Telegram понимает только небольшой набор тегов и отклоняет сообщение целиком, если
разметка битая, — поэтому тексты проверяются при сохранении, а не при отправке.
Одиночные символы <, > и & в тексте экранируются автоматически.
"""
import html
import re
from html.parser import HTMLParser

# Теги Telegram -> разрешённые атрибуты
ALLOWED_TAGS = {
    "b": (), "strong": (), "i": (), "em": (), "u": (), "ins": (),
    "s": (), "strike": (), "del": (), "code": (), "pre": (), "tg-spoiler": (),
    "span": ("class",), "a": ("href",), "blockquote": ("expandable",),
}
LINK_SCHEMES = ("http://", "https://", "tg://", "mailto:")
MESSAGE_LIMIT = 4096


class _Parser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.out: list[str] = []
        self.stack: list[str] = []
        self.errors: list[str] = []

    def _error(self, text: str) -> None:
        if text not in self.errors:
            self.errors.append(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "br":
            self._error("Тег <br> не нужен: перенос строки — это просто новая строка.")
            return
        if tag not in ALLOWED_TAGS:
            self._error(f"Тег <{tag}> не поддерживается Telegram.")
        elif tag == "span" and attrs.get("class") != "tg-spoiler":
            self._error('Тег <span> поддерживается только как спойлер: <span class="tg-spoiler">.')
        elif tag == "a":
            href = (attrs.get("href") or "").strip()
            if href.lower().startswith(LINK_SCHEMES):
                self.out.append(f'<a href="{html.escape(href)}">')
            else:
                self._error(f"Адрес ссылки должен начинаться с https:// (сейчас: «{href}»).")
                self.out.append("<a>")
        elif tag == "span":
            self.out.append("<tg-spoiler>")
        elif tag == "blockquote" and "expandable" in attrs:
            self.out.append("<blockquote expandable>")
        else:
            self.out.append(f"<{tag}>")
        self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        if tag == "br":
            self.handle_starttag(tag, attrs)
        else:
            self._error(f"Тег <{tag}/> не поддерживается Telegram.")

    def handle_endtag(self, tag):
        if tag == "br":
            return
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()
            if tag in ALLOWED_TAGS:
                self.out.append("</tg-spoiler>" if tag == "span" else f"</{tag}>")
        elif tag in self.stack:
            self._error(f"Теги закрыты не по порядку: </{tag}> встретился раньше, "
                        f"чем </{self.stack[-1]}>.")
        else:
            self._error(f"Лишний закрывающий тег </{tag}>.")

    def handle_data(self, data):
        self.out.append(html.escape(data, quote=False))

    def handle_entityref(self, name):
        self.out.append(html.escape(html.unescape(f"&{name};"), quote=False))

    def handle_charref(self, name):
        self.out.append(html.escape(html.unescape(f"&#{name};"), quote=False))

    def handle_comment(self, data):
        self._error("HTML-комментарии <!-- --> не поддерживаются.")

    def unknown_decl(self, data):
        self._error("Служебные HTML-конструкции не поддерживаются.")


def clean_telegram_html(text: str) -> tuple[str, list[str]]:
    """Возвращает (нормализованный текст, ошибки). Пустой список ошибок — текст можно
    отправлять в Telegram с parse_mode=HTML."""
    parser = _Parser()
    parser.feed(text.replace("\r\n", "\n").replace("\r", "\n"))
    parser.close()
    for tag in reversed(parser.stack):
        parser._error(f"Не закрыт тег <{tag}>.")
    return "".join(parser.out), parser.errors


def visible_text(text: str) -> str:
    """Текст без разметки — так, как его увидит пользователь."""
    return html.unescape(re.sub(r"<[^>]+>", "", text or ""))
