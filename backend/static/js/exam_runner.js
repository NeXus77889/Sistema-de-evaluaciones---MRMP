(() => {
  const preflight = document.querySelector("#preflight");
  if (!preflight) return;

  const csrf = document.querySelector('meta[name="csrf-token"]').content;
  const preview = document.querySelector("#camera-preview");
  const cameraFrame = document.querySelector("#camera-frame");
  const enableDevices = document.querySelector("#enable-devices");
  const begin = document.querySelector("#begin-exam");
  const preflightError = document.querySelector("#preflight-error");
  const shell = document.querySelector("#exam-shell");
  const warning = document.querySelector("#monitor-warning");
  const lock = document.querySelector("#focus-lock");
  const restoreDevicesButton = document.querySelector("#restore-devices");
  const restoreDeviceStatus = document.querySelector("#restore-device-status");
  const statusLabels = {
    camera: [document.querySelector("#camera-status"), document.querySelector("#camera-label")],
    microphone: [document.querySelector("#microphone-status"), document.querySelector("#microphone-label")],
  };
  let stream;
  let attemptId;
  let questions = [];
  let answers = new Map();
  let currentIndex = 0;
  let deadline = 0;
  let away = null;
  let timerHandle;
  let incidentPollHandle;
  let incidentPollBusy = false;
  let deviceIncidentActive = false;
  let cameraMonitor = null;
  const tracks = {};

  function renderIncidentCount(count) {
    const counter = document.querySelector("#incident-count");
    if (counter) counter.textContent = `${Math.min(Number(count) || 0, 3)} / 3`;
  }

  async function refreshIncidentCount() {
    if (!attemptId || incidentPollBusy) return;
    incidentPollBusy = true;
    try {
      const response = await fetch(`/api/evaluaciones/intento/${attemptId}/incidencias/conteo/`, {
        credentials: "same-origin",
        cache: "no-store",
      });
      if (!response.ok) return;
      const data = await response.json();
      renderIncidentCount(data.incident_count);
      if (data.status !== "in_progress" && !shell.hidden) {
        await finishExam(true, "La evaluación ya fue entregada.");
      }
    } catch (_) {
      // El siguiente sondeo recupera el contador al volver la conexión.
    } finally {
      incidentPollBusy = false;
    }
  }

  function updateDevice(name, ready, label) {
    const [indicator, text] = statusLabels[name];
    indicator.classList.toggle("is-ready", ready);
    text.textContent = label;
  }

  function makeEventId() {
    if (crypto.randomUUID) return crypto.randomUUID();
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (character) => {
      const value = Math.random() * 16 | 0;
      return (character === "x" ? value : (value & 3 | 8)).toString(16);
    });
  }

  async function sendIncident(kind, durationMs = null) {
    if (!attemptId) return;
    try {
      const response = await fetch(`/api/evaluaciones/intento/${attemptId}/incidencias/`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
        body: JSON.stringify({ kind, duration_ms: durationMs, client_event_id: makeEventId() }),
        credentials: "same-origin",
      });
      if (!response.ok) throw new Error("incident confirmation failed");
      const result = await response.json();
      renderIncidentCount(result.incident_count ?? result.focus_offense_count);
      if (result.counts_as_strike === false) {
        warning.hidden = false;
        warning.textContent = kind === "phone_detected"
          ? "Se detectó un teléfono frente a la cámara. Queda registrado en el informe del docente."
          : "No se te ve en la cámara. Mantente frente a ella durante la evaluación.";
        window.setTimeout(() => { if (lock.hidden) warning.hidden = true; }, 8000);
        return;
      }
      if (result.focus_offense_count !== null && result.focus_offense_count !== undefined) {
        warning.hidden = false;
        warning.textContent = `Advertencia: ${result.focus_offense_count} de 3 infracciones registradas.`;
      }
      if (result.security_ticket_code) {
        warning.hidden = false;
        warning.textContent = `Se registró la incidencia ${result.security_ticket_code}.`;
      }
      if (result.auto_submitted) {
        await finishExam(true, "Evaluación entregada automáticamente por tres infracciones.");
      }
    } catch (error) {
      warning.hidden = false;
      warning.textContent = "No se pudo confirmar una señal con el servidor. Comprueba tu conexión.";
    }
  }

  function setLocked(locked, message) {
    const wasHidden = lock.hidden;
    lock.hidden = !locked;
    document.querySelector("#answer-options").disabled = locked;
    document.querySelector("#previous-question").disabled = locked;
    document.querySelector("#next-question").disabled = locked;
    if (locked) {
      warning.hidden = false;
      warning.textContent = message;
      if (wasHidden && !shell.hidden) restoreDevicesButton.focus();
    } else {
      warning.hidden = true;
    }
  }

  function monitorTrack(name, track) {
    tracks[name] = track;
    const setState = () => {
      if (tracks[name] !== track) return;
      const ready = track.readyState === "live" && track.enabled && !track.muted;
      updateDevice(name, ready, ready ? "Activo" : "Sin señal del dispositivo");
      const other = name === "camera" ? tracks.microphone : tracks.camera;
      const bothReady = ready && other && other.readyState === "live" && other.enabled && !other.muted;
      if (!attemptId) {
        begin.disabled = !bothReady;
        enableDevices.hidden = Boolean(bothReady);
        enableDevices.disabled = false;
      }
      setLocked(!bothReady, "La interacción está pausada. Restablece cámara y micrófono para continuar.");
    };
    track.addEventListener("mute", () => {
      if (tracks[name] !== track) return;
      setState();
    });
    track.addEventListener("unmute", setState);
    track.addEventListener("ended", () => {
      if (tracks[name] !== track) return;
      updateDevice(name, false, "Dispositivo desconectado");
      setLocked(true, "La interacción está pausada. Restablece cámara y micrófono para continuar.");
    });
    setState();
  }

  async function restoreDevices() {
    restoreDevicesButton.disabled = true;
    restoreDeviceStatus.textContent = "Solicitando acceso a cámara y micrófono…";
    try {
      const replacementStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
      const videoTrack = replacementStream.getVideoTracks()[0];
      const audioTrack = replacementStream.getAudioTracks()[0];
      if (!videoTrack || !audioTrack) throw new Error("El navegador no proporcionó ambos dispositivos.");
      const previousStream = stream;
      tracks.camera = videoTrack;
      tracks.microphone = audioTrack;
      stream = replacementStream;
      preview.srcObject = replacementStream;
      if (previousStream) previousStream.getTracks().forEach((track) => track.stop());
      monitorTrack("camera", videoTrack);
      monitorTrack("microphone", audioTrack);
      restoreDeviceStatus.textContent = "";
    } catch (error) {
      restoreDeviceStatus.textContent = error.message || "No se pudo restaurar el acceso a los dispositivos.";
    } finally {
      restoreDevicesButton.disabled = false;
    }
  }

  restoreDevicesButton.addEventListener("click", restoreDevices);

  window.setInterval(() => {
    if (!attemptId) return;
    const ready = [tracks.camera, tracks.microphone].every((track) =>
      track && track.readyState === "live" && track.enabled && !track.muted
    );
    if (ready) {
      deviceIncidentActive = false;
    } else if (!deviceIncidentActive) {
      deviceIncidentActive = true;
      sendIncident("device_disabled");
    }
  }, 500);

  function maybeResumeAway() {
    if (!away || document.visibilityState !== "visible" || !document.hasFocus()) return;
    const elapsed = Math.max(0, Date.now() - away.startedAt);
    sendIncident(away.kind, elapsed);
    away = null;
  }

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") {
      if (!away) away = { kind: "tab_hidden", startedAt: Date.now() };
    } else {
      maybeResumeAway();
    }
  });
  window.addEventListener("blur", () => {
    if (!away) away = { kind: "window_blur", startedAt: Date.now() };
  });
  window.addEventListener("focus", maybeResumeAway);
  document.addEventListener("fullscreenchange", () => {
    if (attemptId && !shell.hidden && !document.fullscreenElement) sendIncident("fullscreen_exit");
  });

  // Modo demostración (solo exposiciones): pulsar y soltar Alt muestra una alerta simulada.
  // No llama al servidor: no registra incidencias ni afecta la nota.
  const demoAlert = document.querySelector("#demo-alert");
  if (preflight.dataset.demo === "true" && demoAlert) {
    let altAlone = false;
    let demoTimer;
    document.addEventListener("keydown", (event) => {
      if (event.key === "Alt") {
        if (!event.repeat) altAlone = true;
      } else {
        altAlone = false; // Alt usada como combinación (Alt+Tab, etc.): no es la señal
      }
    });
    document.addEventListener("keyup", (event) => {
      if (event.key !== "Alt" || !altAlone) return;
      altAlone = false;
      event.preventDefault(); // evita que Firefox muestre su barra de menú
      if (!attemptId || shell.hidden) return;
      demoAlert.hidden = false;
      window.clearTimeout(demoTimer);
      demoTimer = window.setTimeout(() => { demoAlert.hidden = true; }, 10000);
    });
    demoAlert.addEventListener("click", () => { demoAlert.hidden = true; });
  }

  function renderQuestion() {
    const question = questions[currentIndex];
    if (!question) return;
    document.querySelector("#question-progress").textContent = `Pregunta ${currentIndex + 1} de ${questions.length}`;
    document.querySelector("#question-number").textContent = String(currentIndex + 1).padStart(2, "0");
    document.querySelector("#question-text").textContent = question.text;
    const options = document.querySelector("#answer-options");
    options.replaceChildren();
    for (const option of question.options) {
      const label = document.createElement("label");
      label.className = "answer-option";
      const radio = document.createElement("input");
      radio.type = "radio";
      radio.name = `question-${question.id}`;
      radio.value = option.id;
      radio.checked = answers.get(question.id) === option.id;
      radio.disabled = answers.has(question.id) || lock.hidden === false;
      const text = document.createElement("span");
      text.textContent = option.text;
      radio.addEventListener("change", () => saveAnswer(question.id, option.id));
      label.append(radio, text);
      options.append(label);
    }
    document.querySelector("#previous-question").disabled = true;
    document.querySelector("#next-question").disabled = currentIndex === questions.length - 1 || lock.hidden === false;
    document.querySelectorAll("#question-nav button").forEach((button, index) => {
      button.classList.toggle("is-current", index === currentIndex);
      button.classList.toggle("is-answered", answers.has(questions[index].id));
      button.disabled = index < currentIndex || lock.hidden === false;
    });
  }

  async function saveAnswer(questionId, optionId) {
    const saveStatus = document.querySelector("#save-status");
    saveStatus.textContent = "Guardando respuesta…";
    document.querySelectorAll(`#answer-options input[name="question-${questionId}"]`).forEach((input) => { input.disabled = true; });
    try {
      const response = await fetch(`/api/evaluaciones/intento/${attemptId}/respuesta/`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
        body: JSON.stringify({ question_id: questionId, option_id: optionId }),
        credentials: "same-origin",
      });
      if (!response.ok) throw new Error("save failed");
      answers.set(questionId, optionId);
      saveStatus.textContent = "Respuesta guardada.";
      renderQuestion();
    } catch (error) {
      saveStatus.textContent = "No se guardó. Comprueba tu conexión y vuelve a seleccionar la respuesta.";
      renderQuestion();
    }
  }

  function updateTimer() {
    const remaining = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
    const minutes = Math.floor(remaining / 60);
    const seconds = remaining % 60;
    document.querySelector("#exam-timer").textContent = `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
    if (!remaining) {
      clearInterval(timerHandle);
      clearInterval(incidentPollHandle);
      finishExam(true);
    }
  }

  async function finishExam(automatic = false, automaticTitle = "Tiempo agotado") {
    const submit = document.querySelector("#submit-exam");
    submit.disabled = true;
    try {
      const response = await fetch(`/api/evaluaciones/intento/${attemptId}/entregar/`, {
        method: "POST",
        headers: { "X-CSRFToken": csrf },
        credentials: "same-origin",
      });
      if (!response.ok) throw new Error("submit failed");
      clearInterval(timerHandle);
      shell.innerHTML = "";
      const done = document.createElement("div");
      done.className = "submission-complete";
      const title = document.createElement("h2");
      title.textContent = automatic ? automaticTitle : "Evaluación entregada";
      const copy = document.createElement("p");
      copy.textContent = "Tu intento quedó registrado correctamente.";
      const back = document.createElement("a");
      back.className = "button button-primary";
      back.href = "/";
      back.textContent = "Volver al panel";
      done.append(title, copy, back);
      shell.append(done);
    } catch (error) {
      submit.disabled = false;
      warning.hidden = false;
      warning.textContent = "No se pudo confirmar la entrega. Inténtalo de nuevo; tus respuestas siguen guardadas.";
    }
  }

  async function loadExam(id, stateUrl) {
    const response = await fetch(stateUrl, { credentials: "same-origin" });
    if (!response.ok) throw new Error("No se pudo cargar el intento.");
    const state = await response.json();
    if (state.status !== "in_progress") {
      throw new Error("Este intento ya fue entregado.");
    }
    attemptId = id;
    questions = state.questions;
    answers = new Map(questions.filter((question) => question.selected_option_id).map((question) => [question.id, question.selected_option_id]));
    deadline = Date.parse(state.deadline);
    const nav = document.querySelector("#question-nav");
    questions.forEach((question, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = String(index + 1).padStart(2, "0");
      button.setAttribute("aria-label", `Ir a pregunta ${index + 1}`);
      button.addEventListener("click", () => {
        if (index < currentIndex || lock.hidden === false) return;
        currentIndex = index;
        renderQuestion();
      });
      nav.append(button);
    });
    document.querySelector("#next-question").addEventListener("click", () => { currentIndex = Math.min(questions.length - 1, currentIndex + 1); renderQuestion(); });
    document.querySelector("#submit-exam").addEventListener("click", () => {
      if (window.confirm("¿Entregar la evaluación? Esta acción no se puede deshacer.")) finishExam(false);
    });
    renderQuestion();
    updateTimer();
    timerHandle = window.setInterval(updateTimer, 1000);
    await refreshIncidentCount();
    incidentPollHandle = window.setInterval(refreshIncidentCount, 1000);
    shell.append(cameraFrame);
    cameraFrame.classList.add("exam-camera-preview");
    preflight.hidden = true;
    shell.hidden = false;
  }

  function cameraIsLive() {
    const camera = tracks.camera;
    return Boolean(camera && camera.readyState === "live" && camera.enabled && !camera.muted);
  }

  function startCameraMonitor() {
    if (preflight.dataset.cameraAi !== "true" || !window.ExamCameraMonitor || cameraMonitor) return;
    cameraMonitor = window.ExamCameraMonitor.start({
      video: preview,
      status: document.querySelector("#camera-ai-status"),
      // No analizar si la evaluación está pausada, la pestaña oculta o la cámara sin señal.
      skip: () => !lock.hidden || document.visibilityState !== "visible" || !cameraIsLive(),
      report: (kind) => sendIncident(kind),
    });
  }

  enableDevices.addEventListener("click", async () => {
    enableDevices.disabled = true;
    preflightError.textContent = "";
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
      preview.srcObject = stream;
      const videoTrack = stream.getVideoTracks()[0];
      const audioTrack = stream.getAudioTracks()[0];
      if (!videoTrack || !audioTrack) throw new Error("El navegador no proporcionó ambos dispositivos.");
      updateDevice("camera", true, videoTrack.label || "Permiso concedido");
      updateDevice("microphone", true, audioTrack.label || "Permiso concedido");
      monitorTrack("camera", videoTrack);
      monitorTrack("microphone", audioTrack);
      enableDevices.hidden = true;
      begin.disabled = false;
    } catch (error) {
      if (stream) stream.getTracks().forEach((track) => track.stop());
      stream = null;
      begin.disabled = true;
      enableDevices.disabled = false;
      preflightError.textContent = error.message || "Sin permisos activos no puedes iniciar el examen.";
    }
  });

  begin.addEventListener("click", async () => {
    if (!tracks.camera || !tracks.microphone ||
        tracks.camera.readyState !== "live" || tracks.microphone.readyState !== "live" ||
      !tracks.camera.enabled || !tracks.microphone.enabled ||
        tracks.camera.muted || tracks.microphone.muted) {
      begin.disabled = true;
      preflightError.textContent = "Activa cámara y micrófono antes de iniciar el examen.";
      return;
    }
    begin.disabled = true;
    preflightError.textContent = "";
    try {
      if (document.documentElement.requestFullscreen) {
        try { await document.documentElement.requestFullscreen(); } catch (_) { /* El navegador puede denegar pantalla completa. */ }
      }
      const startResponse = await fetch(preflight.dataset.startUrl, {
        method: "POST",
        headers: { "X-CSRFToken": csrf },
        credentials: "same-origin",
      });
      const startData = await startResponse.json();
      if (!startResponse.ok) throw new Error(startData.detail || "No se pudo iniciar la evaluación.");
      attemptId = startData.attempt_id;
      await loadExam(attemptId, `${preflight.dataset.apiRoot}${attemptId}/`);
      startCameraMonitor();
    } catch (error) {
      preflightError.textContent = error.message || "No se pudieron habilitar cámara y micrófono. Revisa los permisos del navegador.";
      begin.disabled = !(tracks.camera?.readyState === "live" && tracks.microphone?.readyState === "live");
    }
  });
})();
