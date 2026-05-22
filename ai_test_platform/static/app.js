const $ = (id) => document.getElementById(id);

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || response.statusText);
  return data;
}

function splitCsv(value) {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

async function generateCases() {
  const data = await api("/api/generate-cases", {
    method: "POST",
    body: JSON.stringify({
      feature: $("genFeature").value,
      requirement: $("requirement").value,
      platforms: splitCsv($("genPlatforms").value),
      max_cases: 4,
    }),
  });
  $("generationResult").innerHTML = `
    <p>Generated ${data.cases.length} cases with mode: ${escapeHtml(data.generation_mode)}</p>
    ${data.generation_error ? `<pre>${escapeHtml(data.generation_error)}</pre>` : ""}
  `;
  await refresh();
}

async function uploadSourceFile() {
  const files = Array.from($("sourceFile").files || []);
  if (files.length === 0) {
    $("fileResult").innerHTML = "<p>Please choose one or more Figma image files first.</p>";
    return;
  }
  const uploaded = [];
  for (const [index, file] of files.entries()) {
    const form = new FormData();
    form.append("file", file);
    form.append("source_type", "figma_image");
    form.append("feature", $("fileFeature").value);
    form.append("screen", `${$("fileScreen").value} ${index + 1}`);
    const response = await fetch("/api/source-files", {
      method: "POST",
      body: form,
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || response.statusText);
    uploaded.push(data);
  }
  $("fileResult").innerHTML = `
    <p>Uploaded ${uploaded.length} Figma design image files.</p>
    <pre>${escapeHtml(JSON.stringify(uploaded.map((item) => ({
      id: item.id,
      document_id: item.document_id,
      source_model_id: item.source_model_id,
      filename: item.filename,
      status: item.extraction_status,
      notes: item.extraction_notes,
      ai_error: item.ai_extraction_error,
    })), null, 2))}</pre>
  `;
  await refresh();
}

async function ingestFigmaContext() {
  let context = $("figmaContext").value;
  try {
    context = JSON.parse(context);
  } catch {
    // Plain-text MCP exports are accepted by the backend.
  }
  const data = await api("/api/figma/mcp-context", {
    method: "POST",
    body: JSON.stringify({
      figma_url: $("figmaUrl").value,
      feature: $("figmaFeature").value,
      screen: $("figmaScreen").value,
      mcp_context: context,
    }),
  });
  $("figmaResult").innerHTML = `
    <p>Ingested Figma artifact #${data.id} and document #${data.document_id}</p>
    <pre>${escapeHtml(JSON.stringify(data.screen_model, null, 2))}</pre>
  `;
  await refresh();
}

async function approveCase(id) {
  await api(`/api/test-cases/${id}/approve`, { method: "POST" });
  await refresh();
}

async function generateMaestro(id) {
  const data = await api(`/api/test-cases/${id}/maestro`, { method: "POST" });
  alert(`Maestro Flow generated:\n${data.path}`);
  await refresh();
}

async function loadCases() {
  const data = await api("/api/test-cases");
  $("cases").innerHTML = data.cases.map((item) => `
    <article class="case-card">
      <header>
        <div>
          <strong>#${item.id} ${escapeHtml(item.title)}</strong>
          <p>${escapeHtml(item.feature)} · ${escapeHtml(item.priority)} · v${item.version}</p>
        </div>
        <span class="status ${escapeHtml(item.status)}">${escapeHtml(item.status)}</span>
      </header>
      <div class="tags">${item.tags.map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("")}</div>
      <div class="actions">
        <button onclick="approveCase(${item.id})">Approve</button>
        <button onclick="generateMaestro(${item.id})">Generate Maestro</button>
      </div>
      <pre>${escapeHtml(JSON.stringify({ steps: item.steps, assertions: item.assertions }, null, 2))}</pre>
    </article>
  `).join("") || "<p>No test cases yet. Upload context and generate cases first.</p>";
}

async function loadMemory() {
  const data = await api("/api/memory");
  const memory = data.memory;
  const counts = memory.counts;
  $("memory").innerHTML = `
    <div class="metrics">
      <div class="metric"><span>Features</span><strong>${counts.features}</strong></div>
      <div class="metric"><span>Screens</span><strong>${counts.screens}</strong></div>
      <div class="metric"><span>Case Links</span><strong>${counts.case_links}</strong></div>
      <div class="metric"><span>Failure Patterns</span><strong>${counts.failure_patterns}</strong></div>
      <div class="metric"><span>Run Stats</span><strong>${counts.case_run_stats}</strong></div>
      <div class="metric"><span>Figma Artifacts</span><strong>${counts.figma_artifacts}</strong></div>
      <div class="metric"><span>Source Files</span><strong>${counts.source_files}</strong></div>
      <div class="metric"><span>Source Models</span><strong>${counts.source_models}</strong></div>
      <div class="metric"><span>Case Versions</span><strong>${counts.test_case_versions}</strong></div>
      <div class="metric"><span>Change Sets</span><strong>${counts.change_sets}</strong></div>
      <div class="metric"><span>Suggestions</span><strong>${counts.case_suggestions}</strong></div>
    </div>
    <h3>Feature Memory</h3>
    <pre>${escapeHtml(JSON.stringify(memory.features.slice(0, 8), null, 2))}</pre>
    <h3>Execution Memory</h3>
    <pre>${escapeHtml(JSON.stringify(memory.case_run_stats.slice(0, 8), null, 2))}</pre>
    <h3>Failure Patterns</h3>
    <pre>${escapeHtml(JSON.stringify(memory.failure_patterns.slice(0, 8), null, 2))}</pre>
    <h3>Figma Artifacts</h3>
    <pre>${escapeHtml(JSON.stringify(memory.figma_artifacts.slice(0, 8), null, 2))}</pre>
    <h3>Source Files</h3>
    <pre>${escapeHtml(JSON.stringify(memory.source_files.slice(0, 8), null, 2))}</pre>
    <h3>Source Models</h3>
    <pre>${escapeHtml(JSON.stringify(memory.source_models.slice(0, 8), null, 2))}</pre>
    <h3>Change Sets</h3>
    <pre>${escapeHtml(JSON.stringify(memory.change_sets.slice(0, 8), null, 2))}</pre>
    <h3>Case Suggestions</h3>
    <pre>${escapeHtml(JSON.stringify(memory.case_suggestions.slice(0, 8), null, 2))}</pre>
  `;
}

async function loadAIStatus() {
  const data = await api("/api/ai/status");
  const ai = data.ai;
  $("aiStatus").textContent = `${ai.provider} · ${ai.model} · ${ai.enabled ? "enabled" : "fallback"} · last mode: ${ai.last_generation_mode}`;
  $("aiStatus").title = ai.reason + (ai.last_generation_error ? ` Error: ${ai.last_generation_error}` : "");
}

async function loadMemoryContext() {
  const params = new URLSearchParams({
    feature: $("memoryFeature").value,
    screen: $("memoryScreen").value,
  });
  const data = await api(`/api/memory/context?${params.toString()}`);
  $("memoryContext").innerHTML = `
    <h3>Generation Memory Context</h3>
    <pre>${escapeHtml(JSON.stringify(data.context, null, 2))}</pre>
  `;
}

function regressionPayload() {
  return {
    changed_features: splitCsv($("changedFeatures").value),
    change_summary: $("changeSummary").value,
    name: $("runName").value,
  };
}

async function selectRegression() {
  const data = await api("/api/regression/select", {
    method: "POST",
    body: JSON.stringify(regressionPayload()),
  });
  $("regressionResult").innerHTML = `
    <p>Selected ${data.count} regression cases</p>
    <pre>${escapeHtml(JSON.stringify(data.selected.map((item) => ({
      id: item.case.id,
      title: item.case.title,
      score: item.score,
      reason: item.reason,
    })), null, 2))}</pre>
  `;
  return data;
}

async function runRegression() {
  const data = await api("/api/runs", {
    method: "POST",
    body: JSON.stringify(regressionPayload()),
  });
  const run = data.run;
  $("runResult").innerHTML = `
    <p>Run #${run.id} · ${escapeHtml(run.status)} · pass rate ${escapeHtml(run.summary.pass_rate)}</p>
    <div class="actions"><a href="/api/reports/${run.id}.html" target="_blank"><button>Open Report</button></a></div>
    <pre>${escapeHtml(JSON.stringify(run.summary, null, 2))}</pre>
  `;
}

async function refresh() {
  await loadAIStatus();
  await loadCases();
  await loadMemory();
}

$("uploadFileBtn").addEventListener("click", uploadSourceFile);
$("generateBtn").addEventListener("click", generateCases);
$("ingestFigmaBtn").addEventListener("click", ingestFigmaContext);
$("selectRegressionBtn").addEventListener("click", selectRegression);
$("runRegressionBtn").addEventListener("click", runRegression);
$("refreshBtn").addEventListener("click", refresh);
$("loadMemoryContextBtn").addEventListener("click", loadMemoryContext);

refresh().catch((error) => {
  $("cases").innerHTML = `<p>${escapeHtml(error.message)}</p>`;
});
