"""Escape notification text for the parse mode of a Telegram bot.

A Telegram notify entity (HA 2025.11+) sends with the parse mode set in
the telegram_bot options, Markdown by default. Our messages contain
option and service names with underscores (``short_off_threshold_min``,
``recompute_kmeans``): Markdown reads them as an unclosed italic and
Telegram rejects the message ("Can't parse entities"). The text is
escaped for the bot's parse mode so it arrives exactly as written.
"""
from __future__ import annotations

# Telegram Bot API, "Formatting options"
_MD_CHARS = "_*`["
_MD2_CHARS = "_*[]()~`>#+-=|{}.!"


def escape_for_parse_mode(text: str, parse_mode: str | None) -> str:
    """Return ``text`` escaped for a telegram_bot parse mode.

    ``markdown`` (legacy, the default), ``markdownv2`` and ``html`` are
    escaped; ``plain_text`` and anything unknown are returned unchanged.
    """
    mode = (parse_mode or "markdown").lower()
    if mode == "markdown":
        return "".join("\\" + c if c in _MD_CHARS else c for c in text)
    if mode == "markdownv2":
        return "".join("\\" + c if c in _MD2_CHARS or c == "\\" else c for c in text)
    if mode == "html":
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return text
