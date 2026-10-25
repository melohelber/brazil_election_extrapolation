const state = { collection: null, result: null };
const params = new URLSearchParams(window.location.search);
const mockMode = params.get("mock") === "1";

const refreshButton = document.querySelector("#refresh-button");
const statusPanel = document.querySelector("#status-panel");
const statusTitle = document.querySelector("#status-title");
const statusDetail = document.querySelector("#status-detail");
const dialog = document.querySelector("#confirm-dialog");
const confirmButton = document.querySelector("#confirm-button");
const dashboard = document.querySelector("#dashboard");
const nationalCard = document.querySelector("#national-card");
const stateGrid = document.querySelector("#state-grid");
const stateSearch = document.querySelector("#state-search");
const historyDate = document.querySelector("#history-date");
const historyLoading = document.querySelector("#history-loading");
const historyContent = document.querySelector("#history-content");
const historyChart = document.querySelector("#history-chart");
const chartTooltip = document.querySelector("#chart-tooltip");
const historyList = document.querySelector("#history-list");
const historyScheduleStatus = document.querySelector("#history-schedule-status");

if (mockMode) {
  document.querySelector("#source-label").textContent = "MODO SIMULAÇÃO";
  document.querySelector("#simulation-notice").classList.remove("hidden");
  document.querySelector("#simulation-link").textContent = "Voltar à apuração real";
  document.querySelector("#simulation-link").href = "/";
  refreshButton.lastChild.textContent = " Executar simulação";
}

const number = new Intl.NumberFormat("pt-BR");
const percent = (value) => `${Number(value || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`;
const localDate = () => {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
};
historyDate.value = localDate();

function setLoading(active, title = "Coletando dados", detail = "Consultando as 27 UFs e o exterior…") {
  refreshButton.disabled = active;
  statusPanel.classList.toggle("hidden", !active);
  statusTitle.textContent = title;
  statusDetail.textContent = detail;
}

function errorMessage(message) {
  statusPanel.classList.remove("hidden");
  statusPanel.querySelector(".spinner").style.display = "none";
  statusTitle.textContent = "Não foi possível concluir";
  statusDetail.textContent = message;
}

async function readJson(response) {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload.erro
      || (payload.coleta?.erros ? "Uma ou mais localidades falharam na coleta." : null)
      || `Erro HTTP ${response.status}`;
    throw new Error(detail);
  }
  return payload;
}

function showConfirmation(collection) {
  const rows = collection.resumo_coleta || [];
  const ok = rows.filter((item) => item.status === "ok").length;
  const ready = collection.pronto_para_projetar === true;
  const withoutVotes = rows.filter((item) => item.status === "sem_votos").length;
  const errors = rows.filter((item) => item.status === "erro").length;
  document.querySelector("#dialog-summary").textContent = !ready
    ? `${errors} localidades com erro de coleta. A análise nacional exige uma coleta válida de todas as localidades.`
    : withoutVotes > 0
      ? `${ok} localidades usarão a apuração atual; ${withoutVotes} ainda sem votos usarão a base redistribuída do primeiro turno.`
      : `${ok} de ${rows.length} localidades com votos disponíveis. Confirme para calcular e abrir a análise.`;
  document.querySelector("#collection-grid").innerHTML = rows.map((item) => `
    <div class="collection-item ${item.status}">
      <span>${item.local}</span><span>${collectionStatus(item)}</span>
    </div>`).join("");
  confirmButton.disabled = !ready;
  dialog.showModal();
}

function collectionStatus(item) {
  if (item.status === "sem_votos") return "BASE 1º TURNO";
  if (item.status === "erro") return "ERRO";
  const sections = item.percentual_secoes_totalizadas;
  return sections === null || sections === undefined
    ? "OK"
    : `OK · ${percent(sections)}`;
}

async function collect() {
  setLoading(true);
  statusPanel.querySelector(".spinner").style.display = "block";
  try {
    const query = mockMode ? "?mock=1" : "";
    const response = await fetch(`/api/snapshot${query}`, { cache: "no-store" });
    const payload = await response.json();
    if (!payload.coleta) throw new Error(payload.erro || `Erro HTTP ${response.status}`);
    state.collection = payload.coleta;
    setLoading(false);
    showConfirmation(state.collection);
  } catch (error) {
    refreshButton.disabled = false;
    errorMessage(error.message);
  }
}

async function project() {
  setLoading(true, "Calculando projeção", "Aplicando a referência de comparecimento do primeiro turno…");
  try {
    const payload = await readJson(await fetch("/api/snapshot", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ coleta: state.collection }),
    }));
    state.result = payload.resultado;
    renderDashboard();
    setLoading(false);
    await loadHistory();
  } catch (error) {
    refreshButton.disabled = false;
    errorMessage(error.message);
  }
}

function linePath(points, key, xScale, yScale) {
  return points.map((point, index) => `${index ? "L" : "M"}${xScale(index).toFixed(1)},${yScale(point[key]).toFixed(1)}`).join(" ");
}

function chartTime(value) {
  return new Date(value).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

function renderHistoryChart(points) {
  if (!points.length) {
    historyChart.innerHTML = `<text x="50%" y="50%" text-anchor="middle" class="chart-axis-label">Nenhuma projeção salva neste dia.</text>`;
    return;
  }
  const width = 820;
  const height = 250;
  const margin = { top: 16, right: 16, bottom: 28, left: 43 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const values = points.flatMap((point) => [point.flavio_bolsonaro_percentual, point.lula_percentual]);
  const rawMin = Math.min(...values);
  const rawMax = Math.max(...values);
  const padding = Math.max(0.75, (rawMax - rawMin) * 0.25);
  const yMin = Math.max(0, Math.floor((rawMin - padding) * 2) / 2);
  const yMax = Math.min(100, Math.ceil((rawMax + padding) * 2) / 2);
  const range = Math.max(yMax - yMin, 1);
  const xScale = (index) => margin.left + (points.length === 1 ? plotWidth / 2 : index * plotWidth / (points.length - 1));
  const yScale = (value) => margin.top + (yMax - value) * plotHeight / range;
  const ticks = Array.from({ length: 5 }, (_, index) => yMin + range * index / 4).reverse();
  const grid = ticks.map((tick) => {
    const y = yScale(tick);
    return `<line class="chart-grid" x1="${margin.left}" y1="${y}" x2="${width - margin.right}" y2="${y}"></line><text class="chart-axis-label" x="${margin.left - 7}" y="${y + 3}" text-anchor="end">${tick.toFixed(1)}%</text>`;
  }).join("");
  const pointMarkup = points.map((point, index) => `
    <circle class="chart-point flavio" cx="${xScale(index)}" cy="${yScale(point.flavio_bolsonaro_percentual)}" r="3.5"></circle>
    <circle class="chart-point lula" cx="${xScale(index)}" cy="${yScale(point.lula_percentual)}" r="3.5"></circle>`).join("");
  historyChart.setAttribute("viewBox", `0 0 ${width} ${height}`);
  historyChart.innerHTML = `${grid}
    <path class="chart-line flavio" d="${linePath(points, "flavio_bolsonaro_percentual", xScale, yScale)}"></path>
    <path class="chart-line lula" d="${linePath(points, "lula_percentual", xScale, yScale)}"></path>
    ${pointMarkup}
    <line id="chart-cursor" class="chart-cursor hidden" y1="${margin.top}" y2="${height - margin.bottom}"></line>
    <text class="chart-axis-label" x="${margin.left}" y="${height - 6}">${chartTime(points[0].capturado_em)}</text>
    <text class="chart-axis-label" x="${width - margin.right}" y="${height - 6}" text-anchor="end">${chartTime(points.at(-1).capturado_em)}</text>
    <rect id="chart-hit" x="${margin.left}" y="${margin.top}" width="${plotWidth}" height="${plotHeight}" fill="transparent"></rect>`;

  const hit = historyChart.querySelector("#chart-hit");
  const cursor = historyChart.querySelector("#chart-cursor");
  const showPoint = (event) => {
    const bounds = historyChart.getBoundingClientRect();
    const clientX = event.clientX ?? event.touches?.[0]?.clientX;
    if (clientX === undefined) return;
    const svgX = (clientX - bounds.left) * width / bounds.width;
    const ratio = Math.min(1, Math.max(0, (svgX - margin.left) / plotWidth));
    const index = Math.round(ratio * Math.max(points.length - 1, 0));
    const point = points[index];
    const x = xScale(index);
    cursor.setAttribute("x1", x);
    cursor.setAttribute("x2", x);
    cursor.classList.remove("hidden");
    chartTooltip.innerHTML = `<strong>${new Date(point.capturado_em).toLocaleString("pt-BR", { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit" })}</strong>
      <span>Flávio Bolsonaro <b class="flavio-copy">${percent(point.flavio_bolsonaro_percentual)}</b></span>
      <span>Lula <b class="lula-copy">${percent(point.lula_percentual)}</b></span>
      <span>Apuração atual <b>${point.localidades_apuracao_atual}/28 locais</b></span>`;
    chartTooltip.style.left = `${x / width * 100}%`;
    chartTooltip.style.top = `${Math.min(yScale(point.flavio_bolsonaro_percentual), yScale(point.lula_percentual)) / height * 100}%`;
    chartTooltip.classList.remove("hidden");
  };
  hit.addEventListener("pointermove", showPoint);
  hit.addEventListener("pointerdown", showPoint);
  hit.addEventListener("pointerleave", (event) => {
    if (event.pointerType === "mouse") {
      cursor.classList.add("hidden");
      chartTooltip.classList.add("hidden");
    }
  });
}

function renderSchedule(schedule) {
  const active = schedule?.ativo === true;
  historyScheduleStatus.classList.toggle("paused", !active);
  historyScheduleStatus.lastChild.textContent = active
    ? " AUTOMÁTICO · 1 MIN"
    : " CRON AGUARDANDO PRO";
}

function renderHistory(history, schedule) {
  renderSchedule(schedule);
  const rounds = history.rodadas || [];
  const points = rounds.filter((round) => round.status === "ok" && round.flavio_bolsonaro_percentual !== null);
  if (!rounds.length) {
    historyContent.classList.add("hidden");
    historyLoading.classList.remove("hidden");
    historyLoading.textContent = schedule?.ativo
      ? "Ainda não há rodadas salvas neste dia. O diário aparecerá aqui assim que a primeira coleta automática terminar."
      : "O diário está pronto, mas o agendamento por minuto aguarda a ativação do Vercel Pro. Atualizações confirmadas manualmente já ficam salvas aqui.";
    return;
  }
  const latest = rounds.at(-1);
  const latestProjection = [...points].reverse().find((point) => point.id <= latest.id);
  historyLoading.classList.add("hidden");
  historyContent.classList.remove("hidden");
  document.querySelector("#history-last-time").textContent = new Date(latest.capturado_em).toLocaleString("pt-BR", { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit" });
  document.querySelector("#history-flavio").textContent = latestProjection ? percent(latestProjection.flavio_bolsonaro_percentual) : "—";
  document.querySelector("#history-lula").textContent = latestProjection ? percent(latestProjection.lula_percentual) : "—";
  document.querySelector("#last-updated").textContent = `Última atualização automática: ${new Date(latest.capturado_em).toLocaleString("pt-BR")}`;
  renderHistoryChart(points);
  historyList.innerHTML = rounds.slice(-8).reverse().map((round) => round.status === "ok" ? `
    <div class="history-row">
      <time>${chartTime(round.capturado_em)}</time>
      <span class="history-value">Flávio <strong class="flavio-copy">${percent(round.flavio_bolsonaro_percentual)}</strong></span>
      <span class="history-value">Lula <strong class="lula-copy">${percent(round.lula_percentual)}</strong></span>
      <span class="history-downloads"><a href="${round.coleta_url}" download>Coleta</a> · <a href="${round.resultado_url}" download>Resultado</a></span>
    </div>` : `
    <div class="history-row">
      <time>${chartTime(round.capturado_em)}</time>
      <span class="history-row-error">Rodada com erro — coleta preservada</span>
      <span class="history-downloads"><a href="${round.coleta_url}" download>Coleta</a></span>
    </div>`).join("");
}

async function loadHistory() {
  const query = new URLSearchParams({ data: historyDate.value, limite: "720" });
  if (mockMode) query.set("mock", "1");
  try {
    const payload = await readJson(await fetch(`/api/history?${query}`, { cache: "no-store" }));
    renderHistory(payload.historico, payload.agendamento);
  } catch (error) {
    historyContent.classList.add("hidden");
    historyLoading.classList.remove("hidden");
    historyLoading.textContent = `Diário indisponível: ${error.message}`;
  }
}

function resultBlock(data, projected = true) {
  return projected ? data?.resultado_extrapolado : data?.resultado_atual;
}

function candidateRow(label, key, votes) {
  const value = votes[key];
  return `<div class="candidate-row">
    <div><div class="candidate-name">${label}</div><div class="candidate-votes">${number.format(value.votos_brutos)} votos projetados</div></div>
    <div class="candidate-percent">${percent(value.percentual_sobre_validos)}</div>
    <div class="bar ${key === "flavio_bolsonaro" ? "flavio" : "lula"}"><span style="width:${value.percentual_sobre_validos}%"></span></div>
  </div>`;
}

function renderNational(entry) {
  const projected = resultBlock(entry.projetado);
  if (!projected) return `<p>A projeção nacional ainda está indisponível.</p>`;
  return `<div class="result-meta"><span>PROJEÇÃO SOBRE VOTOS VÁLIDOS</span><span>${number.format(entry.projetado.total_votos)} votos totais</span></div>
    ${candidateRow("Flávio Bolsonaro", "flavio_bolsonaro", projected)}
    ${candidateRow("Lula", "lula", projected)}
    <div class="summary-foot"><span>Válidos: ${number.format(projected.votos_validos.votos_brutos)}</span><span>Brancos + nulos: ${number.format(projected.brancos_nulos.votos_brutos)}</span><span>Base 1º turno: ${number.format(entry.votos_totais_primeiro_turno)}</span></div>`;
}

function renderState(entry) {
  const votes = resultBlock(entry.projetado);
  const factor = entry.projetado.fator_extrapolacao;
  if (!votes) return `<article class="state-card" data-name="${entry.local}"><div class="state-top"><span class="state-code">${entry.local}</span><span class="factor">SEM PROJEÇÃO</span></div><small>Aguardando votos apurados.</small></article>`;
  const source = entry.projetado.origem_projecao === "primeiro_turno_redistribuido"
    ? "BASE 1º TURNO"
    : `FATOR ${Number(factor).toLocaleString("pt-BR", { maximumFractionDigits: 3 })}×`;
  return `<article class="state-card" data-name="${entry.local}">
    <div class="state-top"><span class="state-code">${entry.local}</span><span class="factor">${source}</span></div>
    <div class="mini-result"><span>Flávio Bolsonaro</span><strong>${percent(votes.flavio_bolsonaro.percentual_sobre_validos)}</strong><small>${number.format(votes.flavio_bolsonaro.votos_brutos)} votos projetados</small></div>
    <div class="mini-result"><span>Lula</span><strong>${percent(votes.lula.percentual_sobre_validos)}</strong><small>${number.format(votes.lula.votos_brutos)} votos projetados</small></div>
  </article>`;
}

function renderDashboard() {
  const entries = state.result.resultados;
  const brazil = entries.find((entry) => entry.local === "BRASIL");
  nationalCard.innerHTML = renderNational(brazil);
  stateGrid.innerHTML = entries.filter((entry) => entry.local !== "BRASIL").map(renderState).join("");
  dashboard.classList.remove("hidden");
  refreshButton.disabled = false;
  document.querySelector("#last-updated").textContent = `Coleta de ${new Date(state.result.capturado_em).toLocaleString("pt-BR")}`;
  dashboard.scrollIntoView({ behavior: "smooth", block: "start" });
}

function downloadJson(prefix, payload) {
  const stamp = (state.collection?.capturado_em || new Date().toISOString()).replace(/[-:]/g, "").replace(/\..+/, "").replace("T", "_");
  const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${prefix}_${stamp}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

refreshButton.addEventListener("click", collect);
confirmButton.addEventListener("click", (event) => {
  event.preventDefault();
  if (!state.collection?.pronto_para_projetar) return;
  dialog.close();
  project();
});
stateSearch.addEventListener("input", () => {
  const query = stateSearch.value.trim().toUpperCase();
  document.querySelectorAll(".state-card").forEach((card) => card.classList.toggle("hidden", !card.dataset.name.includes(query)));
});
document.querySelector("#download-collection").addEventListener("click", () => downloadJson("coleta", state.collection));
document.querySelector("#download-result").addEventListener("click", () => downloadJson("resultado", state.result));
historyDate.addEventListener("change", loadHistory);
loadHistory();
window.setInterval(loadHistory, 60_000);
