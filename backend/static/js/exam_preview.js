document.addEventListener("DOMContentLoaded", () => {
  const form = document.querySelector("#exam-form");
  if (!form) return;

  const title = form.querySelector('[name="title"]');
  const subject = form.querySelector('[name="materia"]');
  const duration = form.querySelector('[name="duration_minutes"]');
  const previewTitle = document.querySelector("#preview-title");
  const previewSubject = document.querySelector("#preview-subject");
  const previewDuration = document.querySelector("#preview-duration");
  const previewCourses = document.querySelector("#preview-courses");

  const updatePreview = () => {
    previewTitle.textContent = title?.value.trim() || "Nueva evaluación";
    previewSubject.textContent = subject?.selectedOptions[0]?.text || "Sin seleccionar";
    previewDuration.textContent = duration?.value || "0";
    const selected = [...form.querySelectorAll('[name="cursos"]:checked')]
      .map((checkbox) => checkbox.closest("label")?.textContent.trim())
      .filter(Boolean);
    previewCourses.textContent = selected.length ? selected.join(", ") : "Ninguno seleccionado";
  };

  form.addEventListener("input", updatePreview);
  form.addEventListener("change", updatePreview);
  updatePreview();
});