#!/usr/bin/env python3
"""
Patch OpenClaw extensions/slack/src/monitor/message-handler/dispatch.ts for
Directive 4.6.3.4.C.1 — explicit Anna requests run ~/blackbox before the embedded model.

Idempotent: skips if BLACKBOX_ANNA_INGRESS marker already present.

Usage (on clawbot, after git pull in ~/blackbox):
  python3 ~/blackbox/scripts/openclaw/apply_openclaw_dispatch_anna_ingress.py

Then rebuild OpenClaw and restart gateway, e.g.:
  cd ~/openclaw && pnpm build
  systemctl --user restart openclaw-gateway.service
"""
from __future__ import annotations

import pathlib
import sys

MARKER = "// BLACKBOX_ANNA_INGRESS_BEGIN"
OPENCLAW = pathlib.Path.home() / "openclaw"
DISPATCH = OPENCLAW / "extensions" / "slack" / "src" / "monitor" / "message-handler" / "dispatch.ts"

IMPORTS = '''import { spawnSync } from "node:child_process";
import { join } from "node:path";
import { stripSlackMentionsForCommandDetection } from "../commands.js";
'''

BLOCK = """
  // BLACKBOX_ANNA_INGRESS_BEGIN — Directive 4.6.3.4.C.1 (blackbox Anna before embedded model)
  const ingressTextForAnna = stripSlackMentionsForCommandDetection(message.text ?? "").trim();
  if (ingressTextForAnna.length > 0) {
    const blackboxRoot = join(process.env.HOME ?? "", "blackbox");
    const bridgeScript = join(blackboxRoot, "scripts", "openclaw", "slack_anna_ingress.py");
    const py = process.env.BLACKBOX_PYTHON ?? "python3";
    const annaBridge = spawnSync(py, [bridgeScript, ingressTextForAnna], {
      encoding: "utf-8",
      maxBuffer: 10_000_000,
      cwd: blackboxRoot,
      env: { ...process.env, PYTHONPATH: blackboxRoot },
    });
    if (annaBridge.status === 0 && (annaBridge.stdout ?? "").trim().length > 0) {
      const finalAnnaText = (annaBridge.stdout ?? "").trim();
      const useAnnaPersonaRoute = !finalAnnaText.startsWith("[BlackBox — System Agent]");
      if (useAnnaPersonaRoute) {
        process.env.SLACK_PERSONA_ROUTE = "anna";
      }
      try {
        await deliverNormally({ text: finalAnnaText });
      } finally {
        delete process.env.SLACK_PERSONA_ROUTE;
      }
      await draftStream.flush();
      draftStream.stop();
      markDispatchIdle();
      const finalStreamEarly = streamSession as SlackStreamSession | null;
      if (finalStreamEarly && !finalStreamEarly.stopped) {
        try {
          await stopSlackStream({ session: finalStreamEarly });
        } catch (err) {
          runtime.error?.(danger(`slack-stream: failed to stop stream: ${String(err)}`));
        }
      }
      const participationThreadTsEarly = usedReplyThreadTs ?? statusThreadTs;
      if (participationThreadTsEarly) {
        recordSlackThreadParticipation(account.accountId, message.channel, participationThreadTsEarly);
      }
      if (shouldLogVerbose()) {
        logVerbose(`slack: blackbox Anna ingress short-circuit to ${prepared.replyTarget}`);
      }
      removeAckReactionAfterReply({
        removeAfterReply: ctx.removeAckAfterReply,
        ackReactionPromise: prepared.ackReactionPromise,
        ackReactionValue: prepared.ackReactionValue,
        remove: () =>
          removeSlackReaction(
            message.channel,
            prepared.ackReactionMessageTs ?? "",
            prepared.ackReactionValue,
            {
              token: ctx.botToken,
              client: ctx.app.client,
            },
          ),
        onError: (err) => {
          logAckFailure({
            log: logVerbose,
            channel: "slack",
            target: `${message.channel}/${message.ts}`,
            error: err,
          });
        },
      });
      if (prepared.isRoomish) {
        clearHistoryEntriesIfEnabled({
          historyMap: ctx.channelHistories,
          historyKey: prepared.historyKey,
          limit: ctx.historyLimit,
        });
      }
      return;
    }
    if (annaBridge.status !== 2 && annaBridge.status !== 0) {
      runtime.error?.(
        danger(
          `slack: blackbox Anna bridge failed (status ${String(annaBridge.status)}): ${String(annaBridge.stderr ?? "")}`,
        ),
      );
    }
  }
"""


def main() -> int:
    if not DISPATCH.is_file():
        print("missing", DISPATCH, file=sys.stderr)
        return 1
    orig = DISPATCH.read_text(encoding="utf-8")
    text = orig
    if MARKER in text:
        print("already_patched", DISPATCH)
        return 0
    anchor = 'import type { PreparedSlackMessage } from "./types.js";\n'
    if anchor not in text:
        print("import anchor not found", file=sys.stderr)
        return 1
    text = text.replace(anchor, anchor + "\n" + IMPORTS + "\n", 1)
    anchor2 = "  const { queuedFinal, counts } = await dispatchInboundMessage({\n"
    if anchor2 not in text:
        print("dispatchInboundMessage anchor not found", file=sys.stderr)
        return 1
    text = text.replace(anchor2, BLOCK + "\n" + anchor2, 1)
    bak = DISPATCH.with_suffix(".ts.bak.4_6_3_4C1")
    bak.write_text(orig, encoding="utf-8")
    DISPATCH.write_text(text, encoding="utf-8")
    print("patched_ok", DISPATCH, "backup", bak)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
