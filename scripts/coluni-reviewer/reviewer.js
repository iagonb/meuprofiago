(() => {
  const $ = (selector) => document.querySelector(selector);
  const elements = {
    year: $("[data-year]"),
    statusFilter: $("[data-status-filter]"),
    picker: $("[data-question-picker]"),
    progress: $("[data-progress]"),
    meta: $("[data-question-meta]"),
    title: $("[data-question-title]"),
    status: $("[data-question-status]"),
    pdf: $("[data-pdf]"),
    pdfLink: $("[data-pdf-link]"),
    source: $("[data-source]"),
    saveState: $("[data-save-state]"),
    previewContent: $("[data-preview-content]"),
    previewState: $("[data-preview-state]"),
    notice: $("[data-notice]"),
    regenerateDialog: $("[data-regenerate-dialog]"),
    regenerateOutput: $("[data-regenerate-output]"),
  };
  let allQuestions = [];
  let reviewed = new Set();
  let queue = [];
  let currentId = null;
  let currentIndex = -1;
  let dirty = false;
  let isLoading = false;

  async function request(url, options = {}) {
    const response = await fetch(url, {
      ...options,
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `Erro ${response.status}`);
    return data;
  }

  function statusLabel(question) {
    return `${question.year} · Q${String(question.number).padStart(2, "0")} · ${question.subject} · ${reviewed.has(question.id) ? "Revisada" : "Pendente"}`;
  }

  function filteredQuestions() {
    return allQuestions.filter((question) => {
      if (elements.year.value !== "all" && String(question.year) !== elements.year.value) return false;
      if (elements.statusFilter.value === "pending" && reviewed.has(question.id)) return false;
      if (elements.statusFilter.value === "reviewed" && !reviewed.has(question.id)) return false;
      return true;
    });
  }

  function updateQueue(preferredId = currentId) {
    const oldIndex = Math.max(0, currentIndex);
    queue = filteredQuestions();
    elements.picker.replaceChildren();
    queue.forEach((question) => {
      const option = document.createElement("option");
      option.value = question.id;
      option.textContent = statusLabel(question);
      elements.picker.append(option);
    });
    if (!queue.length) {
      currentIndex = -1;
      currentId = null;
      elements.picker.disabled = true;
      elements.progress.textContent = `${reviewed.size} revisadas de ${allQuestions.length} · 0 nesta lista`;
      elements.meta.textContent = "";
      elements.title.textContent = "Nenhuma questão neste filtro";
      elements.status.textContent = "—";
      elements.status.className = "status pending";
      elements.source.value = "";
      elements.source.disabled = true;
      elements.pdf.removeAttribute("src");
      elements.pdfLink.removeAttribute("href");
      elements.previewContent.replaceChildren();
      elements.saveState.textContent = "";
      elements.previewState.textContent = "";
      return null;
    }
    elements.picker.disabled = false;
    const keepIndex = queue.findIndex((question) => question.id === preferredId);
    currentIndex = keepIndex >= 0 ? keepIndex : queue.length ? Math.min(oldIndex, queue.length - 1) : -1;
    elements.progress.textContent = `${reviewed.size} revisadas de ${allQuestions.length} · ${queue.length} nesta lista`;
    if (currentIndex >= 0) elements.picker.value = queue[currentIndex].id;
    return currentIndex >= 0 ? queue[currentIndex].id : null;
  }

  function updateStatus(reviewedNow) {
    elements.status.textContent = reviewedNow ? "Revisada" : "Pendente";
    elements.status.className = `status ${reviewedNow ? "reviewed" : "pending"}`;
    $("[data-toggle-status]").hidden = !reviewedNow;
  }

  async function saveSource(showNotice = true) {
    if (!currentId || !dirty) return;
    elements.saveState.textContent = "Salvando…";
    await request(`/api/question/${currentId}`, {
      method: "POST",
      body: JSON.stringify({ source: elements.source.value }),
    });
    dirty = false;
    elements.saveState.textContent = "Salvo na fonte LaTeX";
    await renderPreview();
    if (showNotice) setNotice("Fonte LaTeX salva.");
  }

  async function renderPreview() {
    elements.previewState.textContent = "Renderizando…";
    try {
      const result = await request("/api/preview", {
        method: "POST",
        body: JSON.stringify({ source: elements.source.value }),
      });
      if (window.MathJax?.typesetClear) window.MathJax.typesetClear([elements.previewContent]);
      elements.previewContent.innerHTML = result.preview;
      elements.previewState.textContent = "Prévia atualizada";
      if (window.MathJax?.typesetPromise) await window.MathJax.typesetPromise([elements.previewContent]);
    } catch (error) {
      elements.previewState.textContent = "Prévia indisponível";
      elements.previewContent.innerHTML = `<p class="preview-error"></p>`;
      elements.previewContent.querySelector(".preview-error").textContent = error.message;
    }
  }

  function setNotice(message) {
    elements.notice.textContent = message;
  }

  async function loadQuestion(questionId) {
    if (!questionId || isLoading) return;
    isLoading = true;
    elements.saveState.textContent = "Carregando…";
    setNotice("");
    try {
      const data = await request(`/api/question/${questionId}`);
      currentId = questionId;
      const question = data.question;
      elements.source.value = data.source;
      elements.source.disabled = false;
      dirty = false;
      elements.meta.textContent = `${question.subject} · Prova ${question.year} · Questão original ${String(question.number).padStart(2, "0")}`;
      elements.title.textContent = `Questão ${String(question.number).padStart(2, "0")}`;
      const pdfUrl = `/asset/static${question.pdf}#page=${question.page}&view=FitH`;
      elements.pdf.src = pdfUrl;
      elements.pdfLink.href = `/asset/static${question.pdf}#page=${question.page}`;
      elements.pdfLink.textContent = `Abrir PDF · página ${question.page}`;
      if (window.MathJax?.typesetClear) window.MathJax.typesetClear([elements.previewContent]);
      elements.previewContent.innerHTML = data.preview;
      elements.previewState.textContent = "Fonte carregada";
      elements.saveState.textContent = "Fonte carregada";
      updateStatus(data.reviewed);
      currentIndex = queue.findIndex((item) => item.id === questionId);
      elements.picker.value = questionId;
      if (window.MathJax?.typesetPromise) await window.MathJax.typesetPromise([elements.previewContent]);
    } catch (error) {
      setNotice(`Não foi possível abrir a questão: ${error.message}`);
      elements.saveState.textContent = "Falha ao carregar";
    } finally {
      isLoading = false;
    }
  }

  async function navigateTo(index) {
    if (index < 0 || index >= queue.length || isLoading) return;
    try {
      await saveSource(false);
      await loadQuestion(queue[index].id);
    } catch (error) {
      setNotice(`Não foi possível salvar antes de avançar: ${error.message}`);
    }
  }

  async function setReviewed(value) {
    await saveSource(false);
    await request(`/api/review/${currentId}`, {
      method: "POST",
      body: JSON.stringify({ reviewed: value }),
    });
    if (value) reviewed.add(currentId);
    else reviewed.delete(currentId);
    updateStatus(value);
    const oldIndex = currentIndex;
    const wasPendingList = elements.statusFilter.value === "pending";
    const wasReviewedList = elements.statusFilter.value === "reviewed";
    updateQueue(value && !wasPendingList ? currentId : null);
    if (value) {
      if (wasPendingList) {
        const nextId = queue[oldIndex]?.id;
        if (nextId) await loadQuestion(nextId);
        else if (queue.length) {
          await loadQuestion(queue[currentIndex].id);
          setNotice("Fim desta lista. Use o filtro para acessar as questões pendentes restantes.");
        } else setNotice("Lote concluído: todas as questões desta lista foram revisadas.");
      } else if (oldIndex + 1 < queue.length) {
        await loadQuestion(queue[oldIndex + 1].id);
      } else {
        setNotice("Questão marcada como revisada. Você chegou ao fim desta lista.");
      }
    } else if (wasReviewedList) {
      const nextId = queue[oldIndex]?.id;
      if (nextId) await loadQuestion(nextId);
      else if (queue.length) {
        await loadQuestion(queue[currentIndex].id);
        setNotice("A questão voltou para pendente; fim desta lista revisada.");
      } else setNotice("A questão voltou para pendente; não há mais questões revisadas nesta lista.");
    } else if (queue.some((question) => question.id === currentId)) {
      await loadQuestion(currentId);
    } else {
      setNotice("A questão voltou para pendente.");
    }
  }

  async function regenerateBank() {
    if (dirty) await saveSource(false);
    if (!window.confirm("Gerar novamente questions.json a partir de todas as fontes LaTeX?")) return;
    setNotice("Regenerando o banco. Aguarde…");
    const button = $("[data-regenerate]");
    button.disabled = true;
    try {
      const result = await request("/api/regenerate", { method: "POST", body: JSON.stringify({}) });
      elements.regenerateOutput.textContent = result.output || (result.success ? "Banco gerado." : "A geração falhou.");
      elements.regenerateDialog.showModal();
      if (result.success) setNotice("Banco do simulador regenerado a partir das fontes LaTeX.");
    } catch (error) {
      setNotice(`Falha ao regenerar o banco: ${error.message}`);
    } finally {
      button.disabled = false;
    }
  }

  async function init() {
    const data = await request("/api/questions");
    allQuestions = data.questions;
    reviewed = new Set(data.reviewed);
    [...new Set(allQuestions.map((question) => question.year))].sort().forEach((year) => {
      const option = document.createElement("option");
      option.value = String(year);
      option.textContent = String(year);
      elements.year.append(option);
    });
    const first = updateQueue(null);
    if (first) await loadQuestion(first);
    else setNotice("Não há questões nesta lista.");
  }

  elements.source.addEventListener("input", () => {
    dirty = true;
    elements.saveState.textContent = "Alterações não salvas";
  });
  $("[data-save]").addEventListener("click", () => saveSource().catch((error) => setNotice(`Falha ao salvar: ${error.message}`)));
  $("[data-preview]").addEventListener("click", renderPreview);
  $("[data-previous]").addEventListener("click", () => navigateTo(currentIndex - 1));
  $("[data-next]").addEventListener("click", () => navigateTo(currentIndex + 1));
  $("[data-review-next]").addEventListener("click", () => setReviewed(true).catch((error) => setNotice(`Falha ao marcar como revisada: ${error.message}`)));
  $("[data-toggle-status]").addEventListener("click", () => setReviewed(false).catch((error) => setNotice(`Falha ao reabrir questão: ${error.message}`)));
  elements.picker.addEventListener("change", () => {
    const index = queue.findIndex((question) => question.id === elements.picker.value);
    navigateTo(index);
  });
  elements.year.addEventListener("change", () => {
    const id = updateQueue(null);
    if (id) loadQuestion(id);
    else setNotice("Não há questões para o filtro escolhido.");
  });
  elements.statusFilter.addEventListener("change", () => {
    const id = updateQueue(null);
    if (id) loadQuestion(id);
    else setNotice("Não há questões para o filtro escolhido.");
  });
  $("[data-regenerate]").addEventListener("click", () => regenerateBank().catch((error) => setNotice(error.message)));
  window.addEventListener("beforeunload", (event) => {
    if (dirty) {
      event.preventDefault();
      event.returnValue = "";
    }
  });

  init().catch((error) => {
    elements.title.textContent = "Não foi possível carregar o banco de questões";
    setNotice(error.message);
  });
})();
