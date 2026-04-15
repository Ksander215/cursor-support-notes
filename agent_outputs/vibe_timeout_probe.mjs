import dns from "node:dns/promises";
import https from "node:https";
import { spawn } from "node:child_process";

const ENDPOINT = "http://127.0.0.1:7723/ingest/26b629b8-d8f9-4557-86c3-afa30ed12904";
const SESSION_ID = "3585ee";
const runId = process.argv[2] || "run-1";

function log(hypothesisId, location, message, data = {}) {
  // #region agent log
  fetch(ENDPOINT, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Debug-Session-Id": SESSION_ID,
    },
    body: JSON.stringify({
      sessionId: SESSION_ID,
      runId,
      hypothesisId,
      location,
      message,
      data,
      timestamp: Date.now(),
    }),
  }).catch(() => {});
  // #endregion
}

function headRequest(url, timeoutMs = 15000) {
  return new Promise((resolve, reject) => {
    const req = https.request(url, { method: "HEAD" }, (res) => {
      resolve({
        statusCode: res.statusCode,
        headers: {
          "content-length": res.headers["content-length"] || null,
          server: res.headers.server || null,
        },
      });
      res.resume();
    });
    req.setTimeout(timeoutMs, () => req.destroy(new Error(`TIMEOUT_${timeoutMs}`)));
    req.on("error", reject);
    req.end();
  });
}

function runNpx() {
  return new Promise((resolve) => {
    const child = spawn("npx", ["-y", "vibe-kanban@0.1.36"], {
      stdio: ["ignore", "pipe", "pipe"],
      shell: false,
    });

    let stdout = "";
    let stderr = "";

    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
      if (stdout.length < 1500) {
        log("H4", "agent_outputs/vibe_timeout_probe.mjs:58", "npx stdout chunk", {
          snippet: chunk.toString().slice(0, 220),
        });
      }
    });

    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
      if (stderr.length < 1500) {
        log("H4", "agent_outputs/vibe_timeout_probe.mjs:67", "npx stderr chunk", {
          snippet: chunk.toString().slice(0, 220),
        });
      }
    });

    child.on("close", (code, signal) => {
      resolve({ code, signal, stdout: stdout.slice(0, 2000), stderr: stderr.slice(0, 2000) });
    });
  });
}

async function main() {
  log("H0", "agent_outputs/vibe_timeout_probe.mjs:80", "probe start", {
    node: process.version,
    platform: process.platform,
    arch: process.arch,
  });

  for (const host of ["registry.npmjs.org", "github.com", "release-assets.githubusercontent.com"]) {
    try {
      const addrs = await dns.lookup(host, { all: true });
      log("H1", "agent_outputs/vibe_timeout_probe.mjs:89", "dns resolved", { host, addrs });
    } catch (err) {
      log("H1", "agent_outputs/vibe_timeout_probe.mjs:91", "dns failed", {
        host,
        error: String(err),
      });
    }
  }

  for (const url of [
    "https://registry.npmjs.org/vibe-kanban",
    "https://github.com",
    "https://release-assets.githubusercontent.com",
  ]) {
    try {
      const result = await headRequest(url, 15000);
      log("H2", "agent_outputs/vibe_timeout_probe.mjs:106", "head ok", { url, ...result });
    } catch (err) {
      log("H2", "agent_outputs/vibe_timeout_probe.mjs:108", "head failed", {
        url,
        error: String(err),
      });
    }
  }

  let metadata;
  try {
    const res = await fetch("https://registry.npmjs.org/vibe-kanban");
    metadata = await res.json();
    const pkg = metadata?.versions?.["0.1.36"] || null;
    log("H3", "agent_outputs/vibe_timeout_probe.mjs:120", "registry metadata parsed", {
      has036: !!pkg,
      tarball: pkg?.dist?.tarball || null,
    });
  } catch (err) {
    log("H3", "agent_outputs/vibe_timeout_probe.mjs:125", "registry metadata failed", {
      error: String(err),
    });
  }

  const npxResult = await runNpx();
  log("H4", "agent_outputs/vibe_timeout_probe.mjs:132", "npx finished", npxResult);
}

main().catch((err) => {
  log("H0", "agent_outputs/vibe_timeout_probe.mjs:136", "probe crash", { error: String(err) });
});
