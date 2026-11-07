(() => {
  const dialog = document.getElementById("support-ticket-dialog");
  if (!dialog) return;

  const requestForm = document.getElementById("support-ticket-form");
  const resultPanel = document.getElementById("support-ticket-result");
  const emailWrap = document.getElementById("support-ticket-email-wrap");
  const emailInput = document.getElementById("support-ticket-email");
  const errorMessage = document.getElementById("support-ticket-error");
  const resultError = document.getElementById("support-ticket-result-error");
  const codeOutput = document.getElementById("support-ticket-code");
  let activeTicket = null;

  const randomDigits = (length) => {
    const values = new Uint32Array(1);
    crypto.getRandomValues(values);
    return String(values[0] % 10 ** length).padStart(length, "0");
  };

  const openDialog = (button) => {
    const kind = button.dataset.ticketKind;
    const rawIdentification = (button.dataset.identification || "").replace(/\D/g, "");
    const identification = /^\d{6,40}$/.test(rawIdentification) ? rawIdentification : "";
    const email = button.dataset.email || "";
    let code;
    if (kind === "PASS") code = `SEC-PASS-${identification || randomDigits(10)}`;
    if (kind === "USER") code = `SEC-USER-${randomDigits(6)}`;
    if (kind === "EXAM") {
      code = `SEC-EXAM-${button.dataset.examId}-${identification}`;
    }
    activeTicket = {
      tipo: kind,
      codigo: code,
      identificacion,
      correo: email,
      intento_id: button.dataset.attemptId || null,
    };

    document.getElementById("support-ticket-title").textContent =
      kind === "PASS" ? "Recuperar contraseña" :
      kind === "USER" ? "Recuperar usuario o cédula" : "Reportar evaluación";
    document.getElementById("support-ticket-description").textContent =
      kind === "USER" || (kind === "PASS" && !identification)
        ? "Ingresa el correo registrado en tu cuenta para que Secretaría pueda localizarte."
        : "Generaremos un código para presentar en Secretaría.";
    emailWrap.hidden = !(kind === "USER" || (kind === "PASS" && !identification));
    emailInput.required = !emailWrap.hidden;
    emailInput.value = email;
    requestForm.hidden = false;
    resultPanel.hidden = true;
    errorMessage.hidden = true;
    resultError.hidden = true;
    dialog.showModal();
  };

  document.querySelectorAll(".js-support-ticket").forEach((button) => {
    button.addEventListener("click", () => openDialog(button));
  });

  requestForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    errorMessage.hidden = true;
    activeTicket.correo = emailInput.value.trim() || activeTicket.correo;
    if (activeTicket.tipo === "EXAM" && !activeTicket.identificacion) {
      errorMessage.textContent = "Tu cuenta no tiene una cédula registrada. Contacta a Secretaría.";
      errorMessage.hidden = false;
      return;
    }

    try {
      const response = await fetch("/api/tickets/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": document.querySelector('meta[name="csrf-token"]').content,
        },
        body: JSON.stringify(activeTicket),
        credentials: "same-origin",
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "No se pudo generar el código.");
      codeOutput.textContent = data.codigo;
      requestForm.hidden = true;
      resultPanel.hidden = false;
    } catch (error) {
      errorMessage.textContent = error.message;
      errorMessage.hidden = false;
    }
  });

  dialog.querySelectorAll("[data-ticket-close]").forEach((button) => {
    button.addEventListener("click", () => dialog.close());
  });
  dialog.querySelector("[data-ticket-copy]").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(codeOutput.textContent);
      resultError.textContent = "Código copiado.";
      resultError.hidden = false;
    } catch {
      resultError.textContent = "No se pudo copiar. Selecciona el código manualmente.";
      resultError.hidden = false;
    }
  });
  dialog.querySelector("[data-ticket-print]").addEventListener("click", () => {
    document.body.classList.add("printing-support-ticket");
    window.addEventListener("afterprint", () => {
      document.body.classList.remove("printing-support-ticket");
    }, { once: true });
    window.print();
  });
})();