// Perturbation's opencode plugin. The installer writes this file with the interpreter and app paths
// filled in; reinstalling overwrites it, so edit the source in the repository instead.
//
// It forwards a handful of session events to `perturbation.pyz hook opencode`, each in a detached
// process with the event JSON on stdin. It never awaits the child, never reads its output, and never
// throws: a plugin exception must not disturb opencode.
import { spawn } from "node:child_process";

const PYTHON = __PYTHON__;
const APP = __APP__;

const EVENTS = new Set([
  "session.created",
  "session.status",
  "session.idle",
  "session.error",
  "session.deleted",
  "session.compacted",
  "permission.updated",
  "permission.asked",
  "permission.replied",
]);

function forward(event) {
  try {
    const child = spawn(PYTHON, [APP, "hook", "opencode"], {
      stdio: ["pipe", "ignore", "ignore"],
      detached: true,
      windowsHide: true,
    });
    child.on("error", () => {});
    child.stdin.on("error", () => {});
    child.stdin.end(JSON.stringify(event));
    child.unref();
  } catch (e) {
    // nothing to report to, and nothing that may reach opencode
  }
}

export const Perturbation = async () => {
  const children = new Set(); // subagent sessions: they belong to their parent's turn and are never counted
  const seen = new Set(); // sessions this process forwarded, cleared when opencode shuts down

  function track(sessionID, type) {
    if (type === "session.deleted") seen.delete(sessionID);
    else seen.add(sessionID);
  }

  return {
    event: async ({ event }) => {
      try {
        if (!event || !EVENTS.has(event.type)) return;
        const props = event.properties || {};
        const info = props.info || {};
        if (event.type === "session.created" && info.parentID) {
          children.add(info.id);
          return;
        }
        const sessionID = props.sessionID || info.id;
        if (!sessionID || children.has(sessionID)) return;
        track(sessionID, event.type);
        forward(event);
      } catch (e) {}
    },
    "tool.execute.before": async (input) => {
      try {
        if (input && input.sessionID && !children.has(input.sessionID)) {
          track(input.sessionID, "tool");
          forward({ type: "tool.execute.before", properties: { sessionID: input.sessionID } });
        }
      } catch (e) {}
    },
    "tool.execute.after": async (input) => {
      try {
        if (input && input.sessionID && !children.has(input.sessionID)) {
          forward({ type: "tool.execute.after", properties: { sessionID: input.sessionID } });
        }
      } catch (e) {}
    },
    dispose: async () => {
      // opencode is shutting down and keeps its sessions on disk; ours would linger for a day otherwise.
      try {
        for (const sessionID of seen) forward({ type: "perturbation.shutdown", properties: { sessionID } });
      } catch (e) {}
    },
  };
};
