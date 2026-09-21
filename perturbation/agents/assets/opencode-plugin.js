// Perturbation's opencode plugin. The installer writes this file with the interpreter and app paths
// filled in; reinstalling overwrites it, so edit the source in the repository instead.
//
// It forwards a handful of session events to `perturbation.pyz hook opencode`, one process per event
// with the event JSON on stdin. Events are handed on one at a time, in the order opencode published
// them: opencode ends a turn with two events at once, and two hooks racing would record them out of
// order. The event handler itself returns at once, and the plugin never reads the hook's output and
// never throws: a plugin exception must not disturb opencode.
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

const HOOK_TIMEOUT_MS = 5000; // a stuck hook is killed, so it can't hold up the events behind it

let queue = Promise.resolve();

function run(payload) {
  return new Promise((resolve) => {
    let child;
    let timer;
    const done = () => {
      clearTimeout(timer);
      resolve();
    };
    try {
      child = spawn(PYTHON, [APP, "hook", "opencode"], {
        stdio: ["pipe", "ignore", "ignore"],
        detached: true,
        windowsHide: true,
      });
    } catch (e) {
      return resolve();
    }
    timer = setTimeout(() => {
      try {
        child.kill();
      } catch (e) {}
      resolve();
    }, HOOK_TIMEOUT_MS);
    child.on("error", done);
    child.on("close", done);
    child.stdin.on("error", () => {});
    child.stdin.end(payload);
  });
}

function forward(event) {
  try {
    const payload = JSON.stringify(event);
    queue = queue.then(() => run(payload)).catch(() => {});
  } catch (e) {
    // nothing to report to, and nothing that may reach opencode
  }
  return queue;
}

function settle(ms) {
  return Promise.race([queue, new Promise((resolve) => setTimeout(resolve, ms))]);
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
        await settle(2000);
      } catch (e) {}
    },
  };
};
