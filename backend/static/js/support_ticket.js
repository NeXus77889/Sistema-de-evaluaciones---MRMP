(() => {
  const dialog = document.getElementById("support-notice-dialog");
  if (!dialog) return;
  document.querySelectorAll(".js-support-ticket").forEach((button) => {
    button.addEventListener("click", () => dialog.showModal());
  });
  dialog.querySelectorAll("[data-ticket-close]").forEach((button) => {
    button.addEventListener("click", () => dialog.close());
  });
})();
