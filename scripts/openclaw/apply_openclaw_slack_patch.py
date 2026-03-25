#!/usr/bin/env python3
"""Run on clawbot once: patch OpenClaw extensions/slack/src/send.ts for 4.6.3.4.B.3."""
from __future__ import annotations

import pathlib
import sys

SEND = pathlib.Path.home() / "openclaw" / "extensions" / "slack" / "src" / "send.ts"


def main() -> int:
    if not SEND.is_file():
        print("missing", SEND, file=sys.stderr)
        return 1
    orig = SEND.read_text(encoding="utf-8")
    if "enforceSlackOutboundBlackbox" in orig:
        print("already_patched")
        return 0

    t = orig
    bak = SEND.with_suffix(".ts.bak.4_6_3_4B3")
    bak.write_text(orig, encoding="utf-8")

    old_imp = 'import { resolveSlackBotToken } from "./token.js";\n'
    new_imp = (
        old_imp
        + 'import { spawnSync } from "node:child_process";\n'
        + 'import { join } from "node:path";\n\n'
    )
    if old_imp not in t:
        print("import anchor not found", file=sys.stderr)
        return 1
    t = t.replace(old_imp, new_imp, 1)

    hook = '''/** Blackbox directive 4.6.3.4.B.3 — outbound persona enforcement. */
function enforceSlackOutboundBlackbox(raw: string): string {
  const script = join(process.env.HOME ?? "", "blackbox", "scripts", "openclaw", "run_slack_persona_enforce.py");
  const r = spawnSync("python3", [script], { input: raw, encoding: "utf-8", maxBuffer: 10_000_000 });
  if (r.error || r.status !== 0) {
    logVerbose(`slack persona enforce skipped (${r.status ?? "?"}): ${String(r.stderr ?? r.error)}`);
    return raw;
  }
  return r.stdout ?? raw;
}

'''
    anchor = "type SlackRecipient =\n"
    if anchor not in t:
        print("type SlackRecipient anchor not found", file=sys.stderr)
        return 1
    t = t.replace(anchor, hook + anchor, 1)

    guard = '''  if (!trimmedMessage && !opts.mediaUrl && !blocks) {
    throw new Error("Slack send requires text, blocks, or media");
  }
  const cfg = opts.cfg ?? loadConfig();'''
    repl = '''  if (!trimmedMessage && !opts.mediaUrl && !blocks) {
    throw new Error("Slack send requires text, blocks, or media");
  }
  const outboundText =
    trimmedMessage.length > 0 ? enforceSlackOutboundBlackbox(trimmedMessage) : trimmedMessage;
  const cfg = opts.cfg ?? loadConfig();'''
    if guard not in t:
        print("guard anchor not found", file=sys.stderr)
        return 1
    t = t.replace(guard, repl, 1)

    fb = """    const fallbackText = trimmedMessage || buildSlackBlocksFallbackText(blocks);
    const response = await postSlackMessageBestEffort({
      client,
      channelId,
      text: fallbackText,"""
    fb2 = """    const fallbackText = trimmedMessage || buildSlackBlocksFallbackText(blocks);
    const response = await postSlackMessageBestEffort({
      client,
      channelId,
      text: enforceSlackOutboundBlackbox(fallbackText),"""
    if fb not in t:
        print("fallback block not found", file=sys.stderr)
        return 1
    t = t.replace(fb, fb2, 1)

    ch = """  const markdownChunks =
    chunkMode === "newline"
      ? chunkMarkdownTextWithMode(trimmedMessage, chunkLimit, chunkMode)
      : [trimmedMessage];
  const chunks = markdownChunks.flatMap((markdown) =>
    markdownToSlackMrkdwnChunks(markdown, chunkLimit, { tableMode }),
  );
  const resolvedChunks = resolveTextChunksWithFallback(trimmedMessage, chunks);"""
    ch2 = """  const markdownChunks =
    chunkMode === "newline"
      ? chunkMarkdownTextWithMode(outboundText, chunkLimit, chunkMode)
      : [outboundText];
  const chunks = markdownChunks.flatMap((markdown) =>
    markdownToSlackMrkdwnChunks(markdown, chunkLimit, { tableMode }),
  );
  const resolvedChunks = resolveTextChunksWithFallback(outboundText, chunks);"""
    if ch not in t:
        print("chunk block not found", file=sys.stderr)
        return 1
    t = t.replace(ch, ch2, 1)

    SEND.write_text(t, encoding="utf-8")
    print("patched_ok", SEND)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
