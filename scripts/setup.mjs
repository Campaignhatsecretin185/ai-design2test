import { execFileSync, spawnSync } from "node:child_process";
import { platform } from "node:os";

function commandExists(command) {
  const result = spawnSync(command, ["--version"], { encoding: "utf8" });
  return !result.error && result.status === 0;
}

function readVersion(command, args = ["--version"]) {
  const result = spawnSync(command, args, { encoding: "utf8" });
  if (result.error || result.status !== 0) return "";
  return `${result.stdout}${result.stderr}`.trim().split("\n")[0];
}

function javaMajorVersion() {
  const result = spawnSync("java", ["-version"], { encoding: "utf8" });
  if (result.error || result.status !== 0) return 0;
  const text = `${result.stdout}${result.stderr}`;
  const match = text.match(/version "(\d+)(?:\.(\d+))?/);
  if (!match) return 0;
  const major = Number(match[1]);
  return major === 1 ? Number(match[2] || 0) : major;
}

function logStatus(name, ok, detail = "") {
  const mark = ok ? "OK" : "MISSING";
  console.log(`[${mark}] ${name}${detail ? ` - ${detail}` : ""}`);
}

console.log("AI App Test Platform setup check\n");

const pythonOk = commandExists("python3");
logStatus("python3", pythonOk, pythonOk ? readVersion("python3", ["--version"]) : "required");

const nodeOk = commandExists("node");
logStatus("node", nodeOk, nodeOk ? readVersion("node", ["--version"]) : "required for npm scripts");

const npmOk = commandExists("npm");
logStatus("npm", npmOk, npmOk ? readVersion("npm", ["--version"]) : "required for npm run dev");

const javaVersion = javaMajorVersion();
logStatus("Java 17+", javaVersion >= 17, javaVersion ? `major ${javaVersion}` : "required only for real Maestro execution");

const maestroOk = commandExists("maestro");
logStatus("Maestro CLI", maestroOk, maestroOk ? readVersion("maestro", ["--version"]) : "optional; dry-run works without it");

const aiProvider = process.env.AI_PROVIDER || (process.env.OPENAI_API_KEY || process.env.AI_API_KEY ? "openai" : "");
const aiConfigured = Boolean(
  aiProvider ||
    process.env.OPENAI_API_KEY ||
    process.env.AI_API_KEY ||
    process.env.AI_BASE_URL ||
    process.env.OLLAMA_MODEL
);
logStatus("AI provider", aiConfigured, aiConfigured ? `provider ${aiProvider || "custom"}` : "optional; rule-based fallback works without it");

console.log("\nLocal app dependencies");
console.log("- This MVP uses Python standard library only, so there is no pip install step.");
console.log("- AI provider calls use Python standard library HTTP, so there is no SDK install step.");
console.log("- The RAG implementation is built in. LlamaIndex is planned for the production upgrade, not required here.");
console.log("- Maestro CLI is optional unless you run npm run dev:maestro or set MAESTRO_ENABLED=true.");

if (!maestroOk) {
  console.log("\nInstall Maestro CLI when you want real device execution:");
  if (platform() === "darwin") {
    console.log('  curl -fsSL "https://get.maestro.mobile.dev" | bash');
    console.log("  # or");
    console.log("  brew tap mobile-dev-inc/tap && brew install mobile-dev-inc/tap/maestro");
  } else {
    console.log('  curl -fsSL "https://get.maestro.mobile.dev" | bash');
  }
}

console.log("\nUseful commands");
console.log("  npm run dev          # start web app and API at http://127.0.0.1:8080");
console.log("  npm run dev:maestro  # call local Maestro CLI instead of dry-run");
console.log("  npm test             # run unit tests");
console.log("  npm run check        # syntax check Python files");
console.log("\nAI configuration");
console.log("  export AI_PROVIDER=openai              # openai, compatible, ollama, disabled");
console.log("  export AI_MODEL=gpt-4.1-mini           # or your selected provider model");
console.log("  export AI_API_KEY=...                  # commercial or compatible provider key");
console.log("  export AI_BASE_URL=http://localhost... # compatible provider or local endpoint");
console.log("  export AI_RESPONSE_FORMAT=json_object  # set none for gateways that reject response_format");

if (!pythonOk || !nodeOk || !npmOk) {
  process.exitCode = 1;
}
