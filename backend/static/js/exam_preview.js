document.addEventListener("DOMContentLoaded", () => {
  const form = document.querySelector("#exam-form");
  if (!form) return;

  const title = form.querySelector('[name="title"]');
  const subject = form.querySelector('[name="materia"]');
  const duration = form.querySelector('[name="duration_minutes"]');
  const trimester = form.querySelector('[name="trimestre"]');
  const partial = form.querySelector('[name="parcial"]');
  const questionList = form.querySelector("#question-list");
  const previewTitle = document.querySelector("#preview-title");
  const previewSubject = document.querySelector("#preview-subject");
  const previewPeriod = document.querySelector("#preview-period");
  const previewDuration = document.querySelector("#preview-duration");
  const previewCourses = document.querySelector("#preview-courses");
  const previewQuestionCount = document.querySelector("#preview-question-count");
  const previewTotalPoints = document.querySelector("#preview-total-points");

  const selectedLabel = (field) => field?.selectedOptions[0]?.textContent.trim() || "Sin seleccionar";

  const updatePreview = () => {
    previewTitle.textContent = title?.value.trim() || "Nueva evaluaciÃ³n";
    previewSubject.textContent = selectedLabel(subject);
    previewPeriod.textContent = trimester?.value
      ? `${selectedLabel(trimester)} Â· ${selectedLabel(partial)}`
      : "Sin seleccionar";    previewDuration.textContent = duration?.value || "0";
    const selected = [...form.querySelectorAll('[name="cursos"]:checked')]
      .map((checkbox) => checkbox.closest("label")?.textContent.trim())
      .filter(Boolean);
    previewCourses.textContent = selected.length ? selected.join(", ") : "Ninguno seleccionado";
    const cards = [...(questionList?.querySelectorAll(".question-card") || [])];
    const points = cards.reduce((total, card) => {
      const value = Number(card.querySelector('.question-input-row input[type="number"]')?.value);
      return total + (Number.isFinite(value) && value > 0 ? value : 0);
    }, 0);
    previewQuestionCount.textContent = String(cards.length);
    previewTotalPoints.textContent = new Intl.NumberFormat("es-EC", {
      minimumFractionDigits: 0,
      maximumFractionDigits: 2,
    }).format(points);