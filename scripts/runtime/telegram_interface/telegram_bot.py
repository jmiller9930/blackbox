#!/usr/bin/env python3
"""
Phase 4.6 — Telegram interaction layer (human interface only).

Requires: TELEGRAM_BOT_TOKEN
Optional: TELEGRAM_ALLOWED_CHAT_IDS=comma-separated integers

Does NOT run execution, approvals, or kill switch.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from functools import partial
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from telegram_interface.agent_dispatcher import dispatch
from telegram_interface.message_router import route_message
from telegram_interface.response_formatter import format_anna_system_message, format_response

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("telegram_interface")


def _allowed_chat(update: Update) -> bool:
    raw = os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS")
    if not raw or not str(raw).strip():
        return True
    try:
        allowed = {int(x.strip()) for x in str(raw).split(",") if x.strip()}
    except ValueError:
        logger.warning("Invalid TELEGRAM_ALLOWED_CHAT_IDS; denying all")
        return False
    cid = update.effective_chat.id if update.effective_chat else None
    return cid is not None and cid in allowed


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if not _allowed_chat(update):
        name = None
        if update.effective_user:
            name = (update.effective_user.first_name or "").strip() or None
        await update.message.reply_text(
            format_anna_system_message(
                "I can't open this chat for you — it isn't on the allowed list.\n\n"
                "If you should have access, ask the operator to add your Telegram chat id to TELEGRAM_ALLOWED_CHAT_IDS.",
                user_display_name=name,
            )
        )
        return
    name = None
    if update.effective_user:
        name = (update.effective_user.first_name or "").strip() or None
    welcome = (
        "Welcome to BLACK BOX — read-only chat.\n\n"
        "Telegram may show one bot name (e.g. BB Trader); every reply still tells you who is speaking: "
        "[Anna] for trading, [DATA] for system/SQLite on this host, [Cody] for engineering.\n\n"
        "I'm your default for market, trading, risk, and concept questions — just ask in plain language.\n"
        "Call someone by name: @anna · @data · @mia (placeholder until online) · @cody. "
        "@data does report / insights / status / infra (read-only DB snapshot); "
        "@cody (or a line starting with cody …) is for engineering.\n"
        "You can also say infra or ask about SQLite — that routes to DATA.\n"
        "We don't hand off to each other inside one message yet; that's later.\n\n"
        "Try: help · report · insights · status · infra\n\n"
        "No trades or execution from Telegram."
    )
    await update.message.reply_text(format_anna_system_message(welcome, user_display_name=name))


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if not _allowed_chat(update):
        name = None
        if update.effective_user:
            name = (update.effective_user.first_name or "").strip() or None
        await update.message.reply_text(
            format_anna_system_message(
                "I can't open this chat for you — it isn't on the allowed list.",
                user_display_name=name,
            )
        )
        return
    routed = route_message("help")
    name = None
    if update.effective_user:
        name = (update.effective_user.first_name or "").strip() or None
    try:
        payload = await asyncio.to_thread(partial(dispatch, routed, display_name=name))
        out = format_response(payload, user_display_name=name)
    except Exception as e:
        logger.exception("help dispatch failed")
        await update.message.reply_text(
            format_anna_system_message(
                f"I couldn't load help just now: {e!s}",
                user_display_name=name,
            )
        )
        return
    await update.message.reply_text(out)


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or update.message.text is None:
        return
    if not _allowed_chat(update):
        name = None
        if update.effective_user:
            name = (update.effective_user.first_name or "").strip() or None
        await update.message.reply_text(
            format_anna_system_message(
                "I can't open this chat for you — it isn't on the allowed list.",
                user_display_name=name,
            )
        )
        return
    name = None
    if update.effective_user:
        name = (update.effective_user.first_name or "").strip() or None
    text = update.message.text.strip()
    if not text:
        return
    routed = route_message(text)
    if routed.agent == "anna" and not routed.text.strip():
        await update.message.reply_text(
            format_anna_system_message(
                "Send me a question (I'm Anna for trading and concepts), or try `report` / `insights` / `status` for DATA.",
                user_display_name=name,
            )
        )
        return
    try:
        payload = await asyncio.to_thread(partial(dispatch, routed, display_name=name))
        out = format_response(payload, user_display_name=name)
    except Exception as e:
        logger.exception("dispatch failed")
        await update.message.reply_text(
            format_anna_system_message(
                f"I hit a snag processing that: {e!s}",
                user_display_name=name,
            )
        )
        return
    await update.message.reply_text(out)


def _log_anna_llm_runtime() -> None:
    """Proof in logs: same OLLAMA_* resolution as Anna (see tools/check_ollama_runtime.py)."""
    try:
        from _ollama import ollama_base_url

        resolved = ollama_base_url()
    except Exception as e:
        logger.warning("anna_llm_runtime could not resolve Ollama base: %s", e)
        return
    logger.info(
        "anna_llm_runtime ANNA_USE_LLM=%s OLLAMA_BASE_URL=%s resolved_base=%s OLLAMA_MODEL=%s",
        os.environ.get("ANNA_USE_LLM", "<unset>"),
        os.environ.get("OLLAMA_BASE_URL", "<unset>"),
        resolved,
        os.environ.get("OLLAMA_MODEL", "<unset>"),
    )


def main() -> int:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("Set environment variable TELEGRAM_BOT_TOKEN", file=sys.stderr)
        return 1
    _log_anna_llm_runtime()
    app = (
        Application.builder()
        .token(token)
        .build()
    )
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    logger.info(
        "Starting Telegram bot (polling). Persona tags [Anna]/[DATA]/[Cody]/[Mia] are in message text; "
        "Telegram’s sender label is the bot display name from BotFather (not the persona). "
        "OpenClaw / clawbot do not handle this process — only this script with TELEGRAM_BOT_TOKEN."
    )
    app.run_polling(allowed_updates=Update.ALL_TYPES)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
