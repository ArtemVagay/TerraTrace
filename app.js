/* Связь интерфейса с Python. Найди id кнопки в index.html, затем её обработчик здесь. */
const $ = (id) => document.getElementById(id);
const HISTORY_KEY = "terratrace.reports.v1";
const MAX_BYTES = 5 * 1024 * 1024;
let mode = "file";
let selectedFile = null;
let currentReport = null;
let activeLevel = "all";
let busy = false;
let toastTimer;

// Создаём DOM-элементы. Текст из логов вставляется через textContent, а не innerHTML.
function element(tag, className = "", text = "") {
  const node = document.createElement(tag);
  node.className = className;
  node.textContent = text;
  return node;
}

function icon(name, small = false) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  node.setAttribute("class", small ? "icon small" : "icon");
  node.setAttribute("aria-hidden", "true");
  const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", `#i-${name}`);
  node.append(use);
  return node;
}

function number(value) { return new Intl.NumberFormat("ru-RU").format(value); }
function shortDate(value) {
  return new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}

function toast(message) {
  clearTimeout(toastTimer);
  $("toast").textContent = message;
  $("toast").hidden = false;
  toastTimer = setTimeout(() => { $("toast").hidden = true; }, 3800);
}

function showError(message) {
  $("formError").textContent = message;
  $("formError").hidden = false;
}

function refreshAnalyzeButton() {
  const ready = mode === "file" ? selectedFile !== null : $("logText").value.trim().length > 0;
  $("analyzeButton").disabled = busy || !ready;
}

function setBusy(value) {
  busy = value;
  $("logForm").classList.toggle("is-busy", value);
  $("demoButton").disabled = value;
  $("logFile").disabled = value;
  $("logText").disabled = value;
  $("fileTab").disabled = value;
  $("textTab").disabled = value;
  $("clearFile").disabled = value;
  $("analyzeLabel").textContent = value ? "Разбираем…" : "Разобрать лог";
  refreshAnalyzeButton();
}

function setMode(nextMode) {
  mode = nextMode;
  for (const name of ["file", "text"]) {
    const selected = mode === name;
    $(`${name}Tab`).classList.toggle("selected", selected);
    $(`${name}Tab`).setAttribute("aria-selected", String(selected));
    $(`${name}Panel`).hidden = !selected;
  }
  $("formError").hidden = true;
  refreshAnalyzeButton();
}

function clearSelectedFile() {
  selectedFile = null;
  $("logFile").value = "";
  $("fileLabel").textContent = "Перетащи сюда client.log";
  $("fileHint").textContent = "или нажми, чтобы выбрать файл";
  $("dropZone").classList.remove("has-file");
  $("clearFile").hidden = true;
  refreshAnalyzeButton();
}

function chooseFile(file) {
  if (busy) return;
  $("formError").hidden = true;
  if (!file) return;
  if (!/\.(log|txt)$/i.test(file.name)) { clearSelectedFile(); showError("Нужен текстовый файл .log или .txt."); return; }
  if (!file.size) { clearSelectedFile(); showError("Файл пустой. Выбери журнал после тестового запуска."); return; }
  if (file.size > MAX_BYTES) { clearSelectedFile(); showError("Файл больше 5 МиБ. Выбери более короткий журнал."); return; }
  selectedFile = file;
  $("fileLabel").textContent = file.name;
  $("fileHint").textContent = `${number(Math.max(1, Math.round(file.size / 1024)))} КБ · готов к разбору`;
  $("dropZone").classList.add("has-file");
  $("clearFile").hidden = false;
  refreshAnalyzeButton();
}

// fetch отправляет HTTP-запрос к FastAPI. Сервер возвращает JSON.
async function fetchJSON(url, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 25000);
  try {
    const response = await fetch(url, { ...options, signal: controller.signal });
    let data;
    try { data = await response.json(); }
    catch { throw new Error("Сервер вернул неожиданный ответ. Проверь терминал с Uvicorn."); }
    if (!response.ok) {
      const detail = Array.isArray(data.detail) ? data.detail.map((part) => part.msg).join("; ") : data.detail;
      throw new Error(detail || `Не удалось выполнить запрос (${response.status}).`);
    }
    return data;
  } catch (error) {
    if (error.name === "AbortError") throw new Error("Сервер отвечает слишком долго. Попробуй файл поменьше.");
    if (error instanceof TypeError) throw new Error("Не удалось связаться с сервером. Проверь, что Uvicorn запущен.");
    throw error;
  } finally { clearTimeout(timeout); }
}

async function runAnalysis(request) {
  if (busy) return;
  $("formError").hidden = true;
  setBusy(true);
  try { renderReport(await request()); }
  catch (error) { showError(error.message); }
  finally { setBusy(false); }
}

function renderGroup(group, first) {
  const card = element("details", "event-card");
  card.open = first;
  const summary = document.createElement("summary");
  summary.append(element("span", `level-badge${group.level === "WARN" ? " warn" : ""}`, group.level));
  const heading = element("div", "event-title-block");
  heading.append(element("strong", "event-title", group.finding.title));
  const meta = element("div", "event-subtitle");
  meta.append(element("span", "", group.related_mods.length ? group.related_mods.join(", ") : group.source));
  meta.append(element("span", "", "·"), element("span", "", group.finding.category));
  meta.append(element("span", "", "·"), element("span", "", `строки ${group.first_line}…${group.last_line}`));
  heading.append(meta);
  summary.append(heading, element("span", "event-count", `×${number(group.count)}`), icon("chevron"));
  const body = element("div", "event-details");
  body.append(element("p", "event-message", group.message));
  const columns = element("div", "detail-columns");
  const diagnosis = element("div");
  diagnosis.append(element("p", "detail-label", "ЧТО ПРОВЕРИТЬ"), element("p", "diagnosis-explanation", group.finding.explanation));
  const steps = element("ol", "check-steps");
  for (const step of group.finding.steps) steps.append(element("li", "", step));
  diagnosis.append(steps, element("p", "pattern-note", group.finding.known_pattern ? "Найден известный шаблон. Причину нужно подтвердить тестом." : "Правило пока не найдено. Можно добавить его после проверки случая."));
  const trace = element("div");
  trace.append(element("p", "detail-label", `ПЕРВЫЙ ФРАГМЕНТ · СО СТРОКИ ${group.first_line}`));
  trace.append(element("pre", "trace-code", group.excerpt));
  columns.append(diagnosis, trace);
  body.append(columns);
  card.append(summary, body);
  return card;
}

function filterGroups() {
  if (!currentReport) return;
  const query = $("searchInput").value.trim().toLowerCase();
  const mod = $("modFilter").value;
  const filtered = currentReport.groups.filter((group) => {
    const levelMatches = activeLevel === "all" || (activeLevel === "error" ? ["ERROR", "FATAL"].includes(group.level) : group.level === activeLevel);
    const modMatches = !mod || group.related_mods.includes(mod);
    const text = [group.message, group.excerpt, group.exception_type, group.finding.title, group.finding.category, ...group.related_mods].join(" ").toLowerCase();
    return levelMatches && modMatches && (!query || text.includes(query));
  });
  $("groupsList").replaceChildren(...filtered.map((group, index) => renderGroup(group, index === 0)));
  $("visibleCount").textContent = `${number(filtered.length)} из ${number(currentReport.groups.length)}`;
  $("noResults").hidden = filtered.length > 0;
  $("noResultsText").textContent = currentReport.groups.length ? "Попробуй изменить фильтр, мод или поисковый запрос." : "В этом журнале не найдено записей ERROR, FATAL и WARN.";
}

function renderReport(report) {
  currentReport = report;
  activeLevel = "all";
  $("emptyState").hidden = true;
  $("reportSection").hidden = false;
  $("reportFilename").textContent = report.filename;
  $("reportMeta").textContent = `${shortDate(report.analyzed_at)} · tModLoader ${report.tml_version || "— версия не указана"} · ${report.mods.length} модов в журнале`;
  $("statErrors").textContent = number(report.summary.errors);
  $("statWarnings").textContent = number(report.summary.warnings);
  $("statGroups").textContent = number(report.summary.problem_groups);
  $("statLines").textContent = number(report.summary.total_lines);
  $("allCount").textContent = number(report.groups.length);
  $("searchInput").value = "";
  const allOption = element("option", "", "Все моды");
  allOption.value = "";
  $("modFilter").replaceChildren(allOption);
  for (const mod of report.mods) { const option = element("option", "", mod); option.value = mod; $("modFilter").append(option); }
  const notices = [...report.notices];
  if (report.redactions > 0) notices.push(`Замаскировано фрагментов: ${report.redactions}. Проверь содержимое отчёта перед передачей другим людям.`);
  $("reportNotices").replaceChildren(...notices.map((notice) => element("div", "notice", notice)));
  document.querySelectorAll("[data-level]").forEach((button) => {
    const selected = button.dataset.level === "all";
    button.classList.toggle("selected", selected);
    button.setAttribute("aria-pressed", String(selected));
  });
  updateSaveButton();
  filterGroups();
  $("reportSection").scrollIntoView({ behavior: "smooth", block: "start" });
}

function readHistory() {
  try {
    const entries = JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]");
    return Array.isArray(entries) ? entries.filter((item) => item && typeof item.id === "string" && item.summary && Array.isArray(item.groups) && Array.isArray(item.mods)).slice(0, 5) : [];
  } catch { return []; }
}

function updateSaveButton() {
  const saved = currentReport && readHistory().some((item) => item.id === currentReport.id);
  $("saveReport").replaceChildren(icon(saved ? "check" : "save"), document.createTextNode(saved ? "Сохранено" : "В историю"));
  $("saveReport").disabled = Boolean(saved);
}

function renderHistory() {
  const entries = readHistory();
  $("historyCount").textContent = String(entries.length);
  $("historyEmpty").hidden = entries.length > 0;
  $("clearHistory").hidden = entries.length === 0;
  $("historyList").replaceChildren(...entries.map((report) => {
    const button = element("button", "history-item");
    button.type = "button";
    const description = element("span");
    description.append(element("span", "history-item-name", report.filename), element("span", "history-item-meta", shortDate(report.analyzed_at)));
    button.append(icon("file"), description, element("span", "history-item-count", `${report.summary.errors} ошибок · ${report.summary.problem_groups} групп`), icon("arrow", true));
    button.addEventListener("click", () => { try { renderReport(report); } catch { toast("Не удалось открыть сохранённый отчёт."); } });
    return button;
  }));
}

function saveCurrentReport() {
  if (!currentReport) return;
  try {
    const entries = [currentReport, ...readHistory().filter((item) => item.id !== currentReport.id)].slice(0, 5);
    while (JSON.stringify(entries).length > 1_500_000 && entries.length > 1) entries.pop();
    if (JSON.stringify(entries).length > 1_500_000) { toast("Отчёт слишком большой для истории. Скачай TXT или JSON."); return; }
    localStorage.setItem(HISTORY_KEY, JSON.stringify(entries));
    renderHistory(); updateSaveButton(); toast("Отчёт сохранён в этом браузере.");
  } catch { toast("Браузер не разрешил сохранить историю. Можно скачать отчёт."); }
}

function downloadReport(format) {
  if (!currentReport) return;
  const report = currentReport;
  let content;
  if (format === "json") content = JSON.stringify(report, null, 2);
  else {
    const lines = ["TerraTrace — отчёт по журналу", `Файл: ${report.filename}`, `Дата анализа: ${report.analyzed_at}`, `Версия tModLoader: ${report.tml_version || "не указана"}`, `Моды: ${report.mods.join(", ") || "не указаны"}`, "", `Ошибки: ${report.summary.errors}`, `Предупреждения: ${report.summary.warnings}`, `Группы: ${report.summary.problem_groups}`, `Обработано строк: ${report.summary.total_lines}`, ...report.notices, ""];
    for (const [index, group] of report.groups.entries()) {
      lines.push(`${index + 1}. [${group.level}] ${group.finding.title}`, `Повторений: ${group.count}. Строки: ${group.first_line}…${group.last_line}.`, `Упомянутые моды: ${group.related_mods.join(", ") || "не определены"}`, group.finding.explanation, ...group.finding.steps.map((step) => `• ${step}`), "Первый фрагмент:", group.excerpt, "");
    }
    lines.push("Подсказки основаны на шаблонах; причину сбоя нужно подтвердить тестом.");
    content = "\ufeff" + lines.join("\n");
  }
  const blob = new Blob([content], { type: format === "json" ? "application/json;charset=utf-8" : "text/plain;charset=utf-8" });
  const link = document.createElement("a");
  const base = report.filename.replace(/\.[^.]+$/, "").replace(/[^\p{L}\p{N}._ -]/gu, "_").slice(0, 70);
  const url = URL.createObjectURL(blob);
  link.href = url; link.download = `${base}_report.${format}`;
  document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  toast("Отчёт подготовлен к скачиванию.");
}

// Обработчики кнопок. Эта часть — удобная точка входа для обучения.
$("fileTab").addEventListener("click", () => setMode("file"));
$("textTab").addEventListener("click", () => setMode("text"));
$("logText").addEventListener("input", refreshAnalyzeButton);
$("logFile").addEventListener("change", (event) => chooseFile(event.target.files[0]));
$("clearFile").addEventListener("click", clearSelectedFile);
$("dropZone").addEventListener("keydown", (event) => { if (["Enter", " "].includes(event.key)) { event.preventDefault(); if (!busy) $("logFile").click(); } });
for (const type of ["dragenter", "dragover"]) $("dropZone").addEventListener(type, (event) => { event.preventDefault(); if (!busy) $("dropZone").classList.add("drag-over"); });
$("dropZone").addEventListener("dragleave", () => $("dropZone").classList.remove("drag-over"));
$("dropZone").addEventListener("drop", (event) => { event.preventDefault(); $("dropZone").classList.remove("drag-over"); chooseFile(event.dataTransfer.files[0]); });

$("logForm").addEventListener("submit", (event) => {
  event.preventDefault(); // Не даём форме перезагрузить страницу.
  if (mode === "text") {
    if (!$("logText").value.trim()) return;
    return runAnalysis(() => fetchJSON("/api/logs/text", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: $("logText").value }) }));
  }
  if (!selectedFile) return;
  const data = new FormData();
  data.append("file", selectedFile);
  // Имя file совпадает с параметром file в routers/logs.py.
  runAnalysis(() => fetchJSON("/api/logs/analyze", { method: "POST", body: data }));
});

$("demoButton").addEventListener("click", () => runAnalysis(() => fetchJSON("/api/logs/demo")));
$("searchInput").addEventListener("input", filterGroups);
$("modFilter").addEventListener("change", filterGroups);
document.querySelectorAll("[data-level]").forEach((button) => button.addEventListener("click", () => {
  activeLevel = button.dataset.level;
  document.querySelectorAll("[data-level]").forEach((item) => { const selected = item === button; item.classList.toggle("selected", selected); item.setAttribute("aria-pressed", String(selected)); });
  filterGroups();
}));
$("saveReport").addEventListener("click", saveCurrentReport);
$("exportTxt").addEventListener("click", () => downloadReport("txt"));
$("exportJson").addEventListener("click", () => downloadReport("json"));
$("clearHistory").addEventListener("click", () => { try { localStorage.removeItem(HISTORY_KEY); renderHistory(); updateSaveButton(); toast("История очищена."); } catch { toast("Не удалось очистить историю."); } });
renderHistory();
