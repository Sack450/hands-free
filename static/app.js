/**
 * app.js — Lógica del Frontend para el Panel de Control de Gestos
 *
 * Gestiona:
 * - Conexión WebSocket (Socket.IO) para recibir eventos en tiempo real
 * - Actualización dinámica del panel de estado (gesto, acción, volumen)
 * - Editor de mappings gesto↔acción con guardado automático
 * - Log de actividad reciente
 * - Notificaciones toast y micro-animaciones de feedback
 */

// ═══════════════════════════════════════════════════════════════════════════
// INICIALIZACIÓN
// ═══════════════════════════════════════════════════════════════════════════

/** Conexión Socket.IO al servidor Flask */
const socket = io();

/** Cache de gestos y acciones disponibles (cargados desde la API) */
let gestosDisponibles = [];
let accionesDisponibles = [];

/** Estado actual del sistema */
let estadoActual = {
    pausado: false,
    volumen: 0,
    silenciado: false,
};

/** Máximo de entradas en el log */
const MAX_LOG_ENTRIES = 50;

// ═══════════════════════════════════════════════════════════════════════════
// ELEMENTOS DEL DOM
// ═══════════════════════════════════════════════════════════════════════════

const elementosUI = {
    // Estado
    statusIndicator: document.getElementById("status-indicator"),
    statusText: document.getElementById("status-text"),
    toggleIcon: document.getElementById("toggle-icon"),
    btnToggle: document.getElementById("btn-toggle"),
    videoOverlay: document.getElementById("video-overlay"),
    fpsBadge: document.getElementById("fps-badge"),

    // Panel de estado
    currentGesture: document.getElementById("current-gesture"),
    lastAction: document.getElementById("last-action"),
    volumeValue: document.getElementById("volume-value"),
    muteBadge: document.getElementById("mute-badge"),
    handStatus: document.getElementById("hand-status"),
    statusPanel: document.getElementById("status-panel"),

    // Configuración
    mappingsContainer: document.getElementById("mappings-container"),
    btnReset: document.getElementById("btn-reset"),

    // Log
    logEntries: document.getElementById("log-entries"),
    btnClearLog: document.getElementById("btn-clear-log"),

    // Toast
    toastContainer: document.getElementById("toast-container"),
};

// ═══════════════════════════════════════════════════════════════════════════
// WEBSOCKET — RECEPCIÓN DE EVENTOS EN TIEMPO REAL
// ═══════════════════════════════════════════════════════════════════════════

socket.on("connect", () => {
    console.log("[WebSocket] Conectado al servidor");
    agregarLog("Conectado al servidor", "info");
});

socket.on("disconnect", () => {
    console.log("[WebSocket] Desconectado");
    agregarLog("Desconectado del servidor", "error");
});

/**
 * Evento: se detectó un gesto.
 * Actualiza el panel de estado y agrega la entrada al log.
 */
socket.on("gesture_detected", (data) => {
    // Actualizar indicador de gesto actual
    elementosUI.currentGesture.textContent = data.label || data.gesture;
    elementosUI.handStatus.textContent = "Detectada ✅";

    // Animación de flash en el panel de estado
    const panel = elementosUI.statusPanel;
    panel.classList.remove("gesture-active");
    // Forzar reflow para reiniciar la animación
    void panel.offsetWidth;
    panel.classList.add("gesture-active");

    // Flash en la fila del gesto correspondiente en la configuración
    resaltarMappingRow(data.gesture);

    // Flash en el status item del gesto
    flashElement(document.getElementById("si-gesture"));

    agregarLog(`Gesto: ${data.label}`, "gesture");
});

/**
 * Evento: se ejecutó una acción del sistema.
 */
socket.on("action_executed", (data) => {
    elementosUI.lastAction.textContent = data.label || data.action;

    // Flash en el status item de la acción
    flashElement(document.getElementById("si-action"));

    if (data.success) {
        agregarLog(`Acción: ${data.label}`, "action");
    } else {
        agregarLog(`Error en acción: ${data.label}`, "error");
    }
});

/**
 * Evento: actualización de estado del sistema (volumen, pausa, etc.)
 */
socket.on("status_update", (data) => {
    if (data.volume !== undefined) {
        elementosUI.volumeValue.textContent = Math.round(data.volume);
    }
    if (data.muted !== undefined) {
        estadoActual.silenciado = data.muted;
        if (data.muted) {
            elementosUI.muteBadge.classList.remove("hidden");
        } else {
            elementosUI.muteBadge.classList.add("hidden");
        }
    }
    if (data.paused !== undefined) {
        actualizarEstadoPausa(data.paused);
    }
    if (data.fps !== undefined) {
        elementosUI.fpsBadge.textContent = `${data.fps} FPS`;
    }
});

// ═══════════════════════════════════════════════════════════════════════════
// CARGA INICIAL DE CONFIGURACIÓN
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Carga los gestos, acciones y mappings actuales desde la API REST
 * y construye el editor de configuración.
 */
async function cargarConfiguracion() {
    try {
        // Cargar gestos y acciones disponibles en paralelo
        const [respGestos, respAcciones, respConfig] = await Promise.all([
            fetch("/api/gestures").then((r) => r.json()),
            fetch("/api/actions").then((r) => r.json()),
            fetch("/api/config").then((r) => r.json()),
        ]);

        gestosDisponibles = respGestos;
        accionesDisponibles = respAcciones;

        construirEditorMappings(respConfig.mappings);

        // Cargar estado inicial
        const respStatus = await fetch("/api/status").then((r) => r.json());
        if (respStatus.volume !== undefined) {
            elementosUI.volumeValue.textContent = Math.round(respStatus.volume);
        }
        if (respStatus.muted) {
            elementosUI.muteBadge.classList.remove("hidden");
        }
        actualizarEstadoPausa(respStatus.paused);
    } catch (error) {
        console.error("Error cargando configuración:", error);
        agregarLog("Error cargando configuración", "error");
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// EDITOR DE MAPPINGS
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Construye dinámicamente las filas del editor de mappings gesto↔acción.
 *
 * @param {Object} mappings - Diccionario { gesto: accion }
 */
function construirEditorMappings(mappings) {
    const contenedor = elementosUI.mappingsContainer;
    contenedor.innerHTML = "";

    for (const gesto of gestosDisponibles) {
        const gestoId = gesto.id;
        const gestoLabel = gesto.label;
        const accionActual = mappings[gestoId] || "none";

        // Fila del mapping
        const fila = document.createElement("div");
        fila.className = "mapping-row";
        fila.id = `mapping-${gestoId}`;

        // Nombre del gesto (lado izquierdo)
        const nombreGesto = document.createElement("div");
        nombreGesto.className = "mapping-gesture";
        nombreGesto.textContent = gestoLabel;

        // Flecha decorativa
        const flecha = document.createElement("span");
        flecha.className = "mapping-arrow";
        flecha.textContent = "→";

        // Dropdown de acción (lado derecho)
        const select = document.createElement("select");
        select.className = "mapping-select";
        select.id = `select-${gestoId}`;
        select.dataset.gesture = gestoId;

        for (const accion of accionesDisponibles) {
            const option = document.createElement("option");
            option.value = accion.id;
            option.textContent = accion.label;
            if (accion.id === accionActual) {
                option.selected = true;
            }
            select.appendChild(option);
        }

        // Guardar automáticamente al cambiar
        select.addEventListener("change", () => {
            guardarMapping(gestoId, select.value);
        });

        fila.appendChild(nombreGesto);
        fila.appendChild(flecha);
        fila.appendChild(select);
        contenedor.appendChild(fila);
    }
}

/**
 * Guarda un mapping individual vía la API REST.
 *
 * @param {string} gesto - ID del gesto
 * @param {string} accion - ID de la acción
 */
async function guardarMapping(gesto, accion) {
    try {
        const resp = await fetch("/api/mapping", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ gesture: gesto, action: accion }),
        });

        if (resp.ok) {
            mostrarToast(`Mapping actualizado: ${gesto} → ${accion}`, "success");
            agregarLog(`Config: ${gesto} → ${accion}`, "info");
        } else {
            const error = await resp.json();
            mostrarToast(`Error: ${error.error}`, "error");
        }
    } catch (error) {
        console.error("Error guardando mapping:", error);
        mostrarToast("Error de conexión al guardar", "error");
    }
}

/**
 * Resalta visualmente la fila del mapping correspondiente al gesto detectado.
 *
 * @param {string} gestoId - ID del gesto
 */
function resaltarMappingRow(gestoId) {
    // Quitar highlight previo
    document.querySelectorAll(".mapping-row.highlight").forEach((el) => {
        el.classList.remove("highlight");
    });

    const fila = document.getElementById(`mapping-${gestoId}`);
    if (fila) {
        fila.classList.add("highlight");
        // Quitar después de 1 segundo
        setTimeout(() => fila.classList.remove("highlight"), 1000);
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// CONTROLES DE ESTADO (PAUSA / RESET)
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Actualiza todos los elementos visuales según el estado de pausa.
 *
 * @param {boolean} pausado - true si la detección está pausada
 */
function actualizarEstadoPausa(pausado) {
    estadoActual.pausado = pausado;

    if (pausado) {
        elementosUI.statusIndicator.className = "status-badge status-paused";
        elementosUI.statusText.textContent = "Pausado";
        elementosUI.toggleIcon.textContent = "▶️";
        elementosUI.videoOverlay.classList.remove("hidden");
    } else {
        elementosUI.statusIndicator.className = "status-badge status-active";
        elementosUI.statusText.textContent = "Activo";
        elementosUI.toggleIcon.textContent = "⏸️";
        elementosUI.videoOverlay.classList.add("hidden");
    }
}

// Botón pausar/reanudar
elementosUI.btnToggle.addEventListener("click", async () => {
    try {
        const resp = await fetch("/api/toggle", { method: "POST" });
        const data = await resp.json();
        actualizarEstadoPausa(data.paused);
        agregarLog(
            data.paused ? "Detección pausada" : "Detección reanudada",
            "info"
        );
        mostrarToast(
            data.paused ? "⏸️ Detección pausada" : "▶️ Detección reanudada",
            "info"
        );
    } catch (error) {
        console.error("Error al togglear pausa:", error);
    }
});

// Botón restaurar configuración
elementosUI.btnReset.addEventListener("click", async () => {
    if (!confirm("¿Restaurar toda la configuración a los valores por defecto?")) {
        return;
    }
    try {
        const resp = await fetch("/api/reset", { method: "POST" });
        if (resp.ok) {
            mostrarToast("🔄 Configuración restaurada", "success");
            agregarLog("Configuración restaurada a defaults", "info");
            // Recargar los mappings
            await cargarConfiguracion();
        }
    } catch (error) {
        console.error("Error al restaurar:", error);
        mostrarToast("Error al restaurar configuración", "error");
    }
});

// ═══════════════════════════════════════════════════════════════════════════
// LOG DE ACTIVIDAD
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Agrega una entrada al log de actividad reciente.
 *
 * @param {string} mensaje - Texto del mensaje
 * @param {string} tipo - Tipo de entrada: "info", "gesture", "action", "error"
 */
function agregarLog(mensaje, tipo = "info") {
    const contenedor = elementosUI.logEntries;
    const ahora = new Date();
    const hora = ahora.toLocaleTimeString("es-MX", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
    });

    const entrada = document.createElement("div");
    entrada.className = `log-entry log-${tipo}`;
    entrada.innerHTML = `
        <span class="log-time">${hora}</span>
        <span class="log-msg">${mensaje}</span>
    `;

    // Insertar al inicio (más reciente arriba)
    contenedor.insertBefore(entrada, contenedor.firstChild);

    // Limitar el número de entradas
    while (contenedor.children.length > MAX_LOG_ENTRIES) {
        contenedor.removeChild(contenedor.lastChild);
    }
}

// Botón limpiar log
elementosUI.btnClearLog.addEventListener("click", () => {
    elementosUI.logEntries.innerHTML = "";
    agregarLog("Log limpiado", "info");
});

// ═══════════════════════════════════════════════════════════════════════════
// TOASTS (NOTIFICACIONES TEMPORALES)
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Muestra una notificación toast temporal en la esquina inferior derecha.
 *
 * @param {string} mensaje - Texto del toast
 * @param {string} tipo - "success", "error", o "info"
 * @param {number} duracion - Milisegundos antes de desaparecer (default: 3000)
 */
function mostrarToast(mensaje, tipo = "info", duracion = 3000) {
    const toast = document.createElement("div");
    toast.className = `toast toast-${tipo}`;
    toast.textContent = mensaje;

    elementosUI.toastContainer.appendChild(toast);

    // Remover después de la duración
    setTimeout(() => {
        toast.classList.add("toast-out");
        toast.addEventListener("animationend", () => toast.remove());
    }, duracion);
}

// ═══════════════════════════════════════════════════════════════════════════
// UTILIDADES DE ANIMACIÓN
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Aplica un efecto "flash" temporal a un elemento del DOM.
 * Útil para indicar visualmente que un valor cambió.
 *
 * @param {HTMLElement} elemento - Elemento a flashear
 */
function flashElement(elemento) {
    if (!elemento) return;
    elemento.classList.add("flash");
    setTimeout(() => elemento.classList.remove("flash"), 400);
}

// ═══════════════════════════════════════════════════════════════════════════
// ARRANQUE
// ═══════════════════════════════════════════════════════════════════════════

// Cargar la configuración al iniciar la página
document.addEventListener("DOMContentLoaded", () => {
    cargarConfiguracion();
    agregarLog("Panel de control iniciado", "info");
});
