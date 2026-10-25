(() => {
  const app = document.querySelector("[data-coluni-app]");
  if (!app) return;

  const $ = (selector) => app.querySelector(selector);
  const views = {
    setup: $('[data-view="setup"]'),
    run: $('[data-view="run"]'),
    result: $('[data-view="result"]'),
  };
  const filterMode = $(`[data-filter-mode]`);
  const subjectSelect = $(`[data-subject]`);
  const yearSelect = $(`[data-year]`);
  const countSelect = $(`[data-count]`);
  const availability = $(`[data-availability]`);
  const timerOutput = $(`[data-timer]`);
  const questionContent = $(`[data-question-content]`);
  const answerLetters = ["A", "B", "C", "D"];
  let bank = [];
  let questions = [];
  let answers = [];
  let currentIndex = 0;
  let startedAt = 0;
  let timerInterval = null;

  function visiblePool() {
    return bank.filter((question) => {
      if (filterMode.value === "year") return question.year === Number(yearSelect.value);
      return subjectSelect.value === "Todos" || question.subject === subjectSelect.value;
    });
  }

  function updateSetup() {
    const bySubject = filterMode.value === "subject";
    $('[data-content-field]').hidden = !bySubject;
    $('[data-year-field]').hidden = bySubject;
    const available = visiblePool().length;
    const selected = countSelect.value;
    for (const option of countSelect.options) {
      if (option.value === "complete") continue;
      const count = Number(option.value);
      option.disabled = count > available;
      if (option.value === selected && option.disabled) countSelect.value = "complete";
    }
    const nextSelection = countSelect.value;
    const countLabel = nextSelection === "complete" ? `${available} questões (prova completa)` : `${nextSelection} questões`;
    availability.textContent = `${available} questões disponíveis · ${countLabel} neste simulado.`;
    $('[data-start]').disabled = available === 0;
  }

  function shuffle(items) {
    const result = [...items];
    for (let i = result.length - 1; i > 0; i -= 1) {
      const j = Math.floor(Math.random() * (i + 1));
      [result[i], result[j]] = [result[j], result[i]];
    }
    return result;
  }

  function formatClock(milliseconds) {
    const totalSeconds = Math.max(0, Math.floor(milliseconds / 1000));
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    if (hours > 0) return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
    return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }

  function formatDuration(milliseconds) {
    const totalSeconds = Math.max(0, Math.round(milliseconds / 1000));
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    if (hours) return `${hours} h ${minutes} min ${seconds} s`;
    if (minutes) return `${minutes} min ${seconds} s`;
    return `${seconds} s`;
  }

  function setView(name) {
    for (const [key, view] of Object.entries(views)) view.hidden = key !== name;
  }

  function typesetQuestion() {
    if (window.MathJax?.typesetPromise) {
      window.MathJax.typesetPromise([questionContent]).catch(() => {});
    }
  }

  function clearQuestionContent() {
    window.MathJax?.typesetClear?.([questionContent]);
    questionContent.replaceChildren();
  }

  window.addEventListener("load", typesetQuestion, { once: true });

  function renderQuestionMap() {
    const map = $('[data-question-map]');
    map.replaceChildren();
    questions.forEach((question, index) => {
      const button = document.createElement("button");
      button.className = "coluni-map-button";
      button.type = "button";
      button.textContent = String(index + 1);
      button.setAttribute("aria-label", `Ir para questão ${index + 1}${answers[index] ? ", respondida" : ", sem resposta"}`);
      if (answers[index] !== null) button.classList.add("is-answered");
      if (index === currentIndex) button.setAttribute("aria-current", "step");
      button.addEventListener("click", () => {
        currentIndex = index;
        renderQuestion();
      });
      map.append(button);
    });
  }

  function renderQuestion() {
    const question = questions[currentIndex];
    $('[data-question-source]').textContent = `${question.subject} · Prova ${question.year} · Questão original ${String(question.number).padStart(2, "0")}`;
    $('[data-question-heading]').textContent = `Questão ${currentIndex + 1}`;
    $('[data-progress]').textContent = `${currentIndex + 1} de ${questions.length} questões`;
    clearQuestionContent();
    questionContent.innerHTML = question.latexHtml || "<p>Transcrição desta questão indisponível. Consulte o recorte original abaixo.</p>";
    const transcriptionNote = $('[data-transcription-note]');
    const originalDetails = $('[data-original-details]');
    if (question.transcriptionSource === "latex") {
      transcriptionNote.textContent = "Enunciado digitado em LaTeX. Consulte o original para conferir figuras e textos de apoio.";
      originalDetails.open = false;
    } else {
      transcriptionNote.textContent = "Transcrição automática do texto do PDF. Confira o original para verificar símbolos, figuras e trechos de apoio.";
      originalDetails.open = ["Matemática", "Ciências"].includes(question.subject);
    }
    typesetQuestion();
    const pageImage = $('[data-page-image]');
    pageImage.src = question.pageImage;
    pageImage.alt = `Página ${question.page} da prova do COLUNI ${question.year}. Contém a questão ${question.number} de ${question.subject}.`;
    const originalLink = $('[data-original]');
    originalLink.href = `${question.pdf}#page=${question.page}`;
    const documentWrap = $('[data-document-wrap]');
    documentWrap.querySelectorAll("[data-extra-image]").forEach((element) => element.remove());
    (question.extraImages || []).forEach((part, index) => {
      const link = document.createElement("a");
      link.href = `${question.pdf}#page=${part.page}`;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.dataset.extraImage = "";
      link.setAttribute("aria-label", `Abrir continuação da questão ${question.number} na prova original`);
      const image = document.createElement("img");
      image.src = part.src;
      image.alt = `Continuação ${index + 1} da questão ${question.number} da prova do COLUNI ${question.year}.`;
      image.decoding = "async";
      link.append(image);
      documentWrap.append(link);
    });

    const options = $('[data-answer-options]');
    options.replaceChildren();
    answerLetters.forEach((letter) => {
      const label = document.createElement("label");
      label.className = "coluni-answer";
      const input = document.createElement("input");
      input.type = "radio";
      input.name = `answer-${question.id}`;
      input.value = letter;
      input.checked = answers[currentIndex] === letter;
      input.addEventListener("change", () => {
        answers[currentIndex] = letter;
        renderQuestionMap();
      });
      const text = document.createElement("span");
      text.textContent = letter;
      label.append(input, text);
      options.append(label);
    });
    $('[data-previous]').disabled = currentIndex === 0;
    $('[data-next]').disabled = currentIndex === questions.length - 1;
    renderQuestionMap();
  }

  function startSimulation() {
    const pool = visiblePool();
    const requested = countSelect.value === "complete" ? pool.length : Number(countSelect.value);
    if (!requested || requested > pool.length) return;
    questions = shuffle(pool).slice(0, requested);
    answers = Array(questions.length).fill(null);
    currentIndex = 0;
    startedAt = Date.now();
    timerOutput.textContent = "00:00";
    setView("run");
    renderQuestion();
    timerInterval = window.setInterval(() => {
      timerOutput.textContent = formatClock(Date.now() - startedAt);
    }, 1000);
  }

  function finishSimulation() {
    const unanswered = answers.filter((answer) => answer === null).length;
    if (unanswered && !window.confirm(`Você deixou ${unanswered} questão(ões) sem resposta. Quer finalizar?`)) return;
    window.clearInterval(timerInterval);
    const elapsed = Date.now() - startedAt;
    const correct = questions.reduce((total, question, index) => {
      if (answers[index] === null) return total;
      return total + (question.annulled || answers[index] === question.answer ? 1 : 0);
    }, 0);
    const grade = (correct / questions.length) * 10;
    $('[data-grade]').textContent = grade.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    $('[data-correct]').textContent = `${correct} de ${questions.length}`;
    $('[data-total-time]').textContent = formatDuration(elapsed);
    $('[data-average-time]').textContent = formatDuration(elapsed / questions.length);
    $('[data-page-image]').removeAttribute("src");
    clearQuestionContent();
    $('[data-document-wrap]').querySelectorAll("[data-extra-image]").forEach((element) => element.remove());
    setView("result");
  }

  function resetSimulation() {
    window.clearInterval(timerInterval);
    questions = [];
    answers = [];
    $('[data-page-image]').removeAttribute("src");
    clearQuestionContent();
    $('[data-document-wrap]').querySelectorAll("[data-extra-image]").forEach((element) => element.remove());
    updateSetup();
    setView("setup");
  }

  filterMode.addEventListener("change", updateSetup);
  subjectSelect.addEventListener("change", updateSetup);
  yearSelect.addEventListener("change", updateSetup);
  countSelect.addEventListener("change", updateSetup);
  $('[data-start]').addEventListener("click", startSimulation);
  $('[data-previous]').addEventListener("click", () => {
    if (currentIndex > 0) { currentIndex -= 1; renderQuestion(); }
  });
  $('[data-next]').addEventListener("click", () => {
    if (currentIndex < questions.length - 1) { currentIndex += 1; renderQuestion(); }
  });
  $('[data-finish]').addEventListener("click", finishSimulation);
  $('[data-new]').addEventListener("click", resetSimulation);

  fetch("/simulados/coluni/questions.json")
    .then((response) => {
      if (!response.ok) throw new Error("Falha ao carregar banco de questões");
      return response.json();
    })
    .then((data) => {
      if (!Array.isArray(data) || !data.length) throw new Error("Banco de questões vazio");
      bank = data;
      updateSetup();
    })
    .catch(() => {
      $('[data-error]').hidden = false;
      $('[data-start]').disabled = true;
      availability.textContent = "";
    });
})();
