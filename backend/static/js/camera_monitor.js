/*
 * Detección de teléfono por cámara (opcional por evaluación).
 *
 * El análisis ocurre en el navegador del estudiante con COCO-SSD (TensorFlow.js).
 * No se guardan ni se envían imágenes: solo se envía una incidencia al servidor
 * cuando se detecta un teléfono o cuando no se ve a ninguna persona.
 */
(() => {
  const TFJS_URL = "https://cdn.jsdelivr.net/npm/@tensorflow/tfjs@4.22.0/dist/tf.min.js";
  const COCO_URL = "https://cdn.jsdelivr.net/npm/@tensorflow-models/coco-ssd@2.2.3/dist/coco-ssd.min.js";
  const CHECK_INTERVAL_MS = 1000;
  const PHONE_CONSECUTIVE_HITS = 3;     // ~3 s seguidos con teléfono visible
  const NO_PERSON_CONSECUTIVE_HITS = 8; // ~8 s seguidos sin ver a nadie
  const COOLDOWN_MS = 30000;            // evita repetir la misma incidencia
  const PHONE_MIN_SCORE = 0.5;
  const PERSON_MIN_SCORE = 0.4;

  function loadScript(src) {
    return new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = src;
      script.onload = resolve;
      script.onerror = () => reject(new Error(`No se pudo cargar ${src}`));
      document.head.append(script);
    });
  }

  async function start({ video, status, skip, report }) {
    const setStatus = (text) => { if (status) status.textContent = text; };
    let model;
    setStatus("Detección por cámara: cargando…");
    try {
      await loadScript(TFJS_URL);
      await loadScript(COCO_URL);
      model = await window.cocoSsd.load({ base: "lite_mobilenet_v2" });
    } catch (_) {
      setStatus("Detección por cámara: no disponible en este navegador");
      return { stop() {} };
    }
    setStatus("Detección por cámara: activa");

    let phoneHits = 0;
    let noPersonHits = 0;
    let lastPhoneAt = 0;
    let lastNoPersonAt = 0;
    let busy = false;

    const timer = window.setInterval(async () => {
      if (busy || video.readyState < 2 || (skip && skip())) {
        phoneHits = 0;
        noPersonHits = 0;
        return;
      }
      busy = true;
      try {
        const detections = await model.detect(video, 10, 0.3);
        const phone = detections.some((item) => item.class === "cell phone" && item.score >= PHONE_MIN_SCORE);
        const person = detections.some((item) => item.class === "person" && item.score >= PERSON_MIN_SCORE);
        phoneHits = phone ? phoneHits + 1 : 0;
        noPersonHits = person ? 0 : noPersonHits + 1;
        const now = Date.now();
        if (phoneHits >= PHONE_CONSECUTIVE_HITS && now - lastPhoneAt > COOLDOWN_MS) {
          lastPhoneAt = now;
          phoneHits = 0;
          report("phone_detected");
        }
        if (noPersonHits >= NO_PERSON_CONSECUTIVE_HITS && now - lastNoPersonAt > COOLDOWN_MS) {
          lastNoPersonAt = now;
          noPersonHits = 0;
          report("face_missing");
        }
      } catch (_) {
        // Un fallo puntual de análisis no debe interrumpir la evaluación.
      } finally {
        busy = false;
      }
    }, CHECK_INTERVAL_MS);

    return { stop() { window.clearInterval(timer); } };
  }

  window.ExamCameraMonitor = { start };
})();
