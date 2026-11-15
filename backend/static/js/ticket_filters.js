document.addEventListener("DOMContentLoaded", () => {
  const normalize = (value) => value.trim().toLocaleLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  document.querySelectorAll("[data-filter-directory]").forEach((directory) => {
    const rows = [...directory.querySelectorAll("[data-filter-row]")];
    const groups = [...directory.querySelectorAll("[data-ticket-group], [data-filter-group]")];
    const fields = {
      student: directory.querySelector("[data-filter-student]"),
      course: directory.querySelector("[data-filter-course]"),
      month: directory.querySelector("[data-filter-month]"),
      from: directory.querySelector("[data-filter-from]"),
      to: directory.querySelector("[data-filter-to]"),
    };
    const count = directory.querySelector("[data-filter-count]");
    const empty = directory.querySelector("[data-filter-empty]");
    const noData = directory.querySelector("[data-filter-no-data]");
    const activeFields = Object.fromEntries(Object.entries(fields).filter(([, field]) => field));

    const filter = () => {
      const student = normalize(fields.student?.value || "");
      const course = fields.course?.value || "";
      const month = fields.month?.value || "";
      const from = fields.from?.value || "";
      const to = fields.to?.value || "";
      let visibleCount = 0;
      rows.forEach((row) => {
        const date = row.dataset.date || "";
        const visible = (!student || normalize(row.dataset.student || "").includes(student))
          && (!course || row.dataset.course === course)
          && (!month || date.startsWith(month))
          && (!from || date >= from)
          && (!to || date <= to);
        row.hidden = !visible;
        if (visible) visibleCount += 1;
      });
      [...groups].reverse().forEach((group) => {
        const visibleRows = group.querySelectorAll("[data-filter-row]:not([hidden])").length;
        group.hidden = visibleRows === 0;
        const groupCount = group.querySelector("[data-ticket-group-count], [data-group-count]");
        const count = group.classList.contains("incident-course-group")
          ? group.querySelectorAll(".incident-student-group:not([hidden])").length
          : visibleRows;
        if (groupCount) groupCount.textContent = count;
      });
      if (count) {
        const tickets = directory.classList.contains("ticket-directory");
        count.textContent = tickets
          ? `${visibleCount} ticket${visibleCount === 1 ? "" : "s"} encontrado${visibleCount === 1 ? "" : "s"}`
          : `${visibleCount} incidencia${visibleCount === 1 ? "" : "s"} encontrada${visibleCount === 1 ? "" : "s"}`;
      }
      if (noData) noData.hidden = rows.length > 0;
      if (empty) empty.hidden = visibleCount > 0 || (rows.length === 0 && Boolean(noData));
    };

    Object.values(activeFields).forEach((field) => {
      field.addEventListener("input", filter);
      field.addEventListener("change", filter);
    });
    directory.querySelector("[data-filter-clear]")?.addEventListener("click", () => {
      Object.values(activeFields).forEach((field) => { field.value = ""; });
      filter();
    });
    filter();
  });
});