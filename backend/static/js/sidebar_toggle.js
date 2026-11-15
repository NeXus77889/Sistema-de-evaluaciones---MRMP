document.addEventListener("DOMContentLoaded", () => {
  const shell = document.querySelector(".app-shell");
  const toggle = document.querySelector("[data-sidebar-toggle]");
  if (!shell || !toggle) return;

  const mobile = window.matchMedia("(max-width: 820px)");
  const storageKey = "aula-sidebar-collapsed";

  const isCollapsed = () => localStorage.getItem(storageKey) === "true";

  const updateLabel = () => {
    const expanded = mobile.matches
      ? shell.classList.contains("sidebar-open")
      : !shell.classList.contains("sidebar-collapsed");
    const label = mobile.matches
      ? (expanded ? "Cerrar menú" : "Abrir menú")
      : (expanded ? "Ocultar menú" : "Mostrar menú");
    toggle.setAttribute("aria-expanded", String(expanded));
    toggle.setAttribute("aria-label", label);
    toggle.title = label;
  };

  if (!mobile.matches && isCollapsed()) shell.classList.add("sidebar-collapsed");
  updateLabel();

  toggle.addEventListener("click", () => {
    if (mobile.matches) {
      shell.classList.toggle("sidebar-open");
    } else {
      shell.classList.toggle("sidebar-collapsed");
      localStorage.setItem(storageKey, String(shell.classList.contains("sidebar-collapsed")));
    }
    updateLabel();
  });

  // Cerrar al hacer clic fuera del sidebar en móviles
  document.addEventListener("click", (event) => {
    if (!mobile.matches) return;
    if (!shell.classList.contains("sidebar-open")) return;

    const sidebar = document.querySelector(".sidebar");
    const isClickInsideSidebar = sidebar && sidebar.contains(event.target);
    const isClickOnToggle = toggle.contains(event.target);

    if (!isClickInsideSidebar && !isClickOnToggle) {
      shell.classList.remove("sidebar-open");
      updateLabel();
    }
  });

  // Cerrar al presionar Escape
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && shell.classList.contains("sidebar-open")) {
      shell.classList.remove("sidebar-open");
      updateLabel();
    }
  });

  // Cerrar drawer tras hacer clic en un enlace de navegación en móvil
  const navLinks = document.querySelectorAll(".sidebar .nav-link");
  navLinks.forEach((link) => {
    link.addEventListener("click", () => {
      if (mobile.matches && shell.classList.contains("sidebar-open")) {
        shell.classList.remove("sidebar-open");
        updateLabel();
      }
    });
  });

  mobile.addEventListener("change", () => {
    shell.classList.remove("sidebar-open");
    if (mobile.matches) {
      shell.classList.remove("sidebar-collapsed");
    } else if (isCollapsed()) {
      shell.classList.add("sidebar-collapsed");
    }
    updateLabel();
  });
});
