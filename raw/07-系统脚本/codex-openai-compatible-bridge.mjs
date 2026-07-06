#!/usr/bin/env node
/**
 * OpenAI-compatible local bridge for Trading Review Wiki.
 *
 * The app speaks /v1/chat/completions. This bridge accepts that shape locally
 * and delegates analysis to `codex exec`, so usage follows the local Codex
 * ChatGPT sign-in instead of a paid API key.
 */

import { createServer } from "node:http";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { spawn } from "node:child_process";
import { tmpdir } from "node:os";
import { join } from "node:path";

const HOST = process.env.CODEX_BRIDGE_HOST || "127.0.0.1";
const PORT = Number(process.env.CODEX_BRIDGE_PORT || "17373");
const WORKDIR = process.env.CODEX_BRIDGE_WORKDIR || "/Users/qixinchaye/wiki/73神话";
const MODEL = process.env.CODEX_BRIDGE_MODEL || "";
const TIMEOUT_MS = Number(process.env.CODEX_BRIDGE_TIMEOUT_MS || String(15 * 60 * 1000));

let activeJobs = 0;

function sendJson(res, status, body) {
  res.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "access-control-allow-origin": "*",
    "access-control-allow-headers": "content-type, authorization",
  });
  res.end(JSON.stringify(body));
}

function sseWrite(res, object) {
  res.write(`data: ${JSON.stringify(object)}\n\n`);
}

async function readRequestBody(req) {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  return Buffer.concat(chunks).toString("utf8");
}

function messagesToPrompt(messages) {
  return messages
    .map((message) => {
      const role = message?.role || "user";
      const content = typeof message?.content === "string"
        ? message.content
        : JSON.stringify(message?.content ?? "");
      return `## ${role}\n${content}`;
    })
    .join("\n\n");
}

async function runCodex(prompt, requestModel) {
  const tempDir = await mkdtemp(join(tmpdir(), "trwiki-codex-bridge-"));
  const outputPath = join(tempDir, "last-message.md");
  const promptPath = join(tempDir, "prompt.md");
  await writeFile(promptPath, prompt, "utf8");

  const args = [
    "exec",
    "--ephemeral",
    "--skip-git-repo-check",
    "--cd",
    WORKDIR,
    "--sandbox",
    "workspace-write",
    "--output-last-message",
    outputPath,
    "-",
  ];

  const chosenModel = requestModel && requestModel !== "codex-pro-local"
    ? requestModel
    : MODEL;
  if (chosenModel) {
    args.splice(1, 0, "--model", chosenModel);
  }

  return await new Promise((resolve, reject) => {
    const child = spawn("codex", args, {
      cwd: WORKDIR,
      stdio: ["pipe", "pipe", "pipe"],
      env: {
        ...process.env,
        NO_COLOR: "1",
      },
    });

    let stdout = "";
    let stderr = "";
    const timer = setTimeout(() => {
      child.kill("SIGTERM");
      reject(new Error(`codex exec timeout after ${TIMEOUT_MS}ms`));
    }, TIMEOUT_MS);

    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });
    child.on("error", (err) => {
      clearTimeout(timer);
      reject(err);
    });
    child.on("close", async (code) => {
      clearTimeout(timer);
      try {
        const text = await readFile(outputPath, "utf8");
        await rm(tempDir, { recursive: true, force: true });
        if (code !== 0 && !text.trim()) {
          reject(new Error(`codex exec failed code=${code}\n${stderr || stdout}`));
          return;
        }
        resolve(text.trim());
      } catch (err) {
        await rm(tempDir, { recursive: true, force: true });
        reject(new Error(`codex exec failed code=${code}\n${stderr || stdout}\n${err.message}`));
      }
    });

    child.stdin.end(prompt);
  });
}

const server = createServer(async (req, res) => {
  if (req.method === "OPTIONS") {
    res.writeHead(204, {
      "access-control-allow-origin": "*",
      "access-control-allow-methods": "GET, POST, OPTIONS",
      "access-control-allow-headers": "content-type, authorization",
    });
    res.end();
    return;
  }

  if (req.method === "GET" && req.url === "/health") {
    sendJson(res, 200, {
      ok: true,
      service: "trading-review-wiki-codex-bridge",
      activeJobs,
      workdir: WORKDIR,
    });
    return;
  }

  if (req.method !== "POST" || !req.url?.startsWith("/v1/chat/completions")) {
    sendJson(res, 404, { error: { message: "not found" } });
    return;
  }

  let body;
  try {
    body = JSON.parse(await readRequestBody(req));
  } catch {
    sendJson(res, 400, { error: { message: "invalid json" } });
    return;
  }

  const prompt = messagesToPrompt(Array.isArray(body.messages) ? body.messages : []);
  if (!prompt.trim()) {
    sendJson(res, 400, { error: { message: "messages required" } });
    return;
  }

  activeJobs += 1;
  const startedAt = Date.now();
  try {
    const content = await runCodex(prompt, body.model);
    const id = `chatcmpl-codex-local-${startedAt}`;
    const model = body.model || MODEL || "codex-pro-local";

    if (body.stream !== false) {
      res.writeHead(200, {
        "content-type": "text/event-stream; charset=utf-8",
        "cache-control": "no-cache",
        "connection": "keep-alive",
        "access-control-allow-origin": "*",
      });
      sseWrite(res, {
        id,
        object: "chat.completion.chunk",
        created: Math.floor(startedAt / 1000),
        model,
        choices: [{ index: 0, delta: { content }, finish_reason: null }],
      });
      sseWrite(res, {
        id,
        object: "chat.completion.chunk",
        created: Math.floor(Date.now() / 1000),
        model,
        choices: [{ index: 0, delta: {}, finish_reason: "stop" }],
      });
      res.write("data: [DONE]\n\n");
      res.end();
    } else {
      sendJson(res, 200, {
        id,
        object: "chat.completion",
        created: Math.floor(startedAt / 1000),
        model,
        choices: [{ index: 0, message: { role: "assistant", content }, finish_reason: "stop" }],
      });
    }
  } catch (err) {
    sendJson(res, 500, { error: { message: err instanceof Error ? err.message : String(err) } });
  } finally {
    activeJobs -= 1;
  }
});

server.listen(PORT, HOST, () => {
  console.log(`codex bridge listening on http://${HOST}:${PORT}/v1`);
  console.log(`workdir=${WORKDIR}`);
});
