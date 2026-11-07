document.addEventListener("input", (event) => {
  const search = event.target.closest("[data-course-search]");
  if (!search) return;

  const picker = search.closest("[data-course-picker]");
  const query = search.value.trim().toLocaleLowerCase();
  picker.querySelectorAll("[data-course-group]").forEach((group) => {
    let visibleOptions = 0;
    group.querySelectorAll("[data-course-option]").forEach((option) => {
      const visible = option.dataset.courseLabel.includes(query);
      option.hidden = !visible;
      if (visible) visibleOptions += 1;
    });
    group.hidden = visibleOptions === 0;
    if (query && visibleOptions) group.open = true;
  });
});

document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-course-select-group]");
  if (!button) return;

  event.preventDefault();
  const group = button.closest("[data-course-group]");
  group.querySelectorAll('[data-course-option]:not([hidden]) input[type="checkbox"]').forEach((checkbox) => {
    checkbox.checked = true;
    checkbox.dispatchEvent(new Event("change", { bubbles: true }));
  });
});