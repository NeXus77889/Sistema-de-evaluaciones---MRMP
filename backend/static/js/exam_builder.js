(() => {
  const form = document.querySelector("#exam-form");
  const list = document.querySelector("#question-list");
  const serialized = document.querySelector("#questions-json");
  const error = document.querySelector("#question-error");
  const importFile = document.querySelector("#docx-file");
  const importStatus = document.querySelector("#docx-import-status");
  const previewDialog = document.querySelector("#docx-preview-dialog");
  const previewList = document.querySelector("#docx-preview-list");
  const previewError = document.querySelector("#docx-preview-error");
  if (!form || !list || !serialized) return;

  const initial = JSON.parse(document.querySelector("#initial-questions").textContent);

  function makeButton(text, className, action) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = className;
    button.textContent = text;
    button.addEventListener("click", action);
    return button;
  }

  function addOption(optionList, radioGroup, value = "", correct = false) {
    const row = document.createElement("div");
    row.className = "option-row";
    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = radioGroup;
    radio.checked = correct;
    radio.setAttribute("aria-label", "Marcar como respuesta correcta");
    const text = document.createElement("input");
    text.type = "text";
    text.maxLength = 1000;
    text.placeholder = "Texto de la opción";
    text.value = value;
    text.required = true;
    const remove = makeButton("Quitar", "remove-option", () => {
      if (optionList.children.length > 2) row.remove();
    });
    row.append(radio, text, remove);
    optionList.append(row);
  }

  function addQuestion(data = {}) {
    const card = document.createElement("article");
    card.className = "question-card";
    const radioGroup = `correct-${Math.random().toString(36).slice(2)}`;
    const header = document.createElement("div");
    header.className = "question-card-head";
    const title = document.createElement("strong");
    title.textContent = "Pregunta";
    const remove = makeButton("Eliminar pregunta", "remove-question", () => card.remove());
    header.append(title, remove);

    const fields = document.createElement("div");
    fields.className = "question-input-row";
    const prompt = document.createElement("input");
    prompt.type = "text";
    prompt.maxLength = 5000;
    prompt.placeholder = "Escribe la pregunta";
    prompt.value = data.text || "";
    prompt.required = true;
    const points = document.createElement("input");
    points.type = "number";
    points.min = "0.01";
    points.step = "0.01";
    points.value = data.points || "1";
    points.setAttribute("aria-label", "Puntaje de la pregunta");
    points.required = true;

    const optionList = document.createElement("div");
    optionList.className = "option-list";
    for (const option of data.options || [{}, {}]) addOption(optionList, radioGroup, option.text, option.correct);
    const add = makeButton("Añadir opción", "", () => {
      if (optionList.children.length < 12) addOption(optionList, radioGroup);
    });
    card.append(header, fields, optionList, add);
    fields.append(prompt, points);
    list.append(card);
    refreshQuestionNumbers();
  }

  function refreshQuestionNumbers() {
    list.querySelectorAll(".question-card-head strong").forEach((heading, index) => {
      heading.textContent = `Pregunta ${index + 1}`;
    });
  }

  function renderImportPreview(questions) {
    previewList.replaceChildren();
    for (const [questionIndex, question] of questions.entries()) {
      const card = document.createElement("article");
      card.className = "docx-preview-question";
      const prompt = document.createElement("h3");
      prompt.textContent = `${questionIndex + 1}. ${question.text}`;
      const options = document.createElement("fieldset");
      options.className = "docx-preview-options";
      const legend = document.createElement("legend");
      legend.textContent = "Respuesta correcta";
      options.append(legend);
      for (const [optionIndex, option] of question.options.entries()) {
        const label = document.createElement("label");
        const radio = document.createElement("input");
        radio.type = "radio";
        radio.name = `docx-correct-${questionIndex}`;
        radio.value = String(optionIndex);
        radio.checked = option.correct;
        radio.required = true;
        const text = document.createElement("span");
        text.textContent = option.text;
        label.append(radio, text);
        options.append(label);
      }
      card.append(prompt, options);
      previewList.append(card);
    }
  }

  importFile.addEventListener("change", async () => {
    const file = importFile.files[0];
    if (!file) return;
    importStatus.textContent = "Leyendo documento…";
    previewError.textContent = "";
    const payload = new FormData();
    payload.append("archivo", file);
    try {
      const response = await fetch(previewDialog.dataset.previewUrl, {
        method: "POST",
        headers: { "X-CSRFToken": document.querySelector('meta[name="csrf-token"]').content },
        body: payload,
        credentials: "same-origin",
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "No se pudo importar el documento.");
      renderImportPreview(data.questions);
      previewDialog.showModal();
      importStatus.textContent = `${data.questions.length} preguntas encontradas.`;
    } catch (importError) {
      importStatus.textContent = "";
      error.textContent = importError.message || "No se pudo importar el documento.";
    } finally {
      importFile.value = "";
    }
  });

  function closeImportPreview() {
    previewDialog.close();
  }

  document.querySelector("#close-docx-preview").addEventListener("click", closeImportPreview);
  document.querySelector("#cancel-docx-preview").addEventListener("click", closeImportPreview);
  document.querySelector("#use-imported-questions").addEventListener("click", () => {
    previewError.textContent = "";
    const cards = [...previewList.querySelectorAll(".docx-preview-question")];
    if (list.children.length + cards.length > 100) {
      previewError.textContent = "El examen admite hasta 100 preguntas en total.";
      return;
    }
    const imported = [];
    for (const [questionIndex, card] of cards.entries()) {
      const selected = card.querySelector("input[type=radio]:checked");
      if (!selected) {
        previewError.textContent = `Selecciona la respuesta correcta de la pregunta ${questionIndex + 1}.`;
        card.scrollIntoView({ behavior: "smooth", block: "center" });
        return;
      }
      imported.push({
        text: card.querySelector("h3").textContent.replace(/^\d+\.\s*/, ""),
        points: "1",
        options: [...card.querySelectorAll("input[type=radio]")].map((radio) => ({
          text: radio.nextElementSibling.textContent,
          correct: radio === selected,
        })),
      });
    }
    for (const question of imported) addQuestion(question);
    refreshQuestionNumbers();
    closeImportPreview();
  });

  document.querySelector("#add-question").addEventListener("click", () => {
    if (list.children.length < 100) addQuestion();
    refreshQuestionNumbers();
  });
  list.addEventListener("click", (event) => {
    if (event.target.closest(".remove-question")) refreshQuestionNumbers();
  });
  for (const question of initial) addQuestion(question);
  if (!initial.length) addQuestion();

  form.addEventListener("submit", (event) => {
    error.textContent = "";
    const questions = [];
    for (const card of list.querySelectorAll(".question-card")) {
      const [prompt, points] = card.querySelectorAll(".question-input-row input");
      const options = [...card.querySelectorAll(".option-row")].map((row) => ({
        text: row.querySelector("input[type=text]").value.trim(),
        correct: row.querySelector("input[type=radio]").checked,
      }));
      if (!prompt.value.trim() || options.length < 2 || options.filter((option) => option.correct).length !== 1) {
        event.preventDefault();
        error.textContent = "Completa cada pregunta con al menos dos opciones y exactamente una respuesta correcta.";
        card.scrollIntoView({ behavior: "smooth", block: "center" });
        return;
      }
      questions.push({ text: prompt.value.trim(), points: points.value, options });
    }
    if (!questions.length) {
      event.preventDefault();
      error.textContent = "Agrega al menos una pregunta.";
      return;
    }
    serialized.value = JSON.stringify(questions);
  });
})();