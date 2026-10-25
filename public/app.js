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

if (mockMode) {
  document.querySelector("#source-label").textContent = "MODO SIMULAÇÃO";
  document.querySelector("#simulation-notice").classList.remove("hidden");
  document.querySelector("#simulation-link").textContent = "Voltar à apuração real";
  document.querySelector("#simulation-link").href = "/";
  refreshButton.lastChild.textContent = " Executar simulação";
}

const number = new Intl.NumberFormat("pt-BR");
const percent = (value) => `${Number(value || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`;

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
  } catch (error) {
    refreshButton.disabled = false;
    errorMessage(error.message);
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
