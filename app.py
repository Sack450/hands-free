"""
app.py — Servidor Web Flask + API REST + WebSocket (Socket.IO)

Provee:
- Panel de control web en la ruta raíz (/)
- Stream MJPEG del video con landmarks (/video_feed)
- API REST para gestionar configuración (/api/*)
- WebSocket para notificaciones en tiempo real (gesture_detected, action_executed)
"""

import threading

from flask import Flask, Response, render_template, jsonify, request
from flask_socketio import SocketIO

from config_manager import (
    GESTOS_VALIDOS, ACCIONES_VALIDAS,
    GESTO_LABELS, ACCION_LABELS,
)


# ─── Inicialización de Flask ─────────────────────────────────────────────────
app = Flask(__name__)
app.config["SECRET_KEY"] = "gestos-control-2026"

# SocketIO con threading async mode (compatible con el loop de OpenCV)
socketio = SocketIO(app, async_mode="threading", cors_allowed_origins="*")

# Referencias globales (se inyectan desde main.py)
_config_manager = None
_gesture_engine = None
_action_executor = None
_video_generador = None


def inicializar_app(config_manager, gesture_engine, action_executor, video_gen):
    """
    Inyecta las dependencias del sistema en el servidor Flask.
    Se llama desde main.py antes de arrancar el servidor.
    """
    global _config_manager, _gesture_engine, _action_executor, _video_generador
    _config_manager = config_manager
    _gesture_engine = gesture_engine
    _action_executor = action_executor
    _video_generador = video_gen


# ─── Funciones para emitir eventos WebSocket ─────────────────────────────────

def emitir_gesto(nombre_gesto):
    """Notifica al frontend que se detectó un gesto."""
    label = GESTO_LABELS.get(nombre_gesto, nombre_gesto)
    socketio.emit("gesture_detected", {
        "gesture": nombre_gesto,
        "label": label,
    })


def emitir_accion(nombre_accion, exito):
    """Notifica al frontend que se ejecutó una acción."""
    label = ACCION_LABELS.get(nombre_accion, nombre_accion)
    socketio.emit("action_executed", {
        "action": nombre_accion,
        "label": label,
        "success": exito,
    })


def emitir_estado(data):
    """Envía un update de estado al frontend (FPS, volumen, pausa, etc.)."""
    socketio.emit("status_update", data)


# ─── Rutas de la UI ──────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Sirve el panel de control principal."""
    return render_template("index.html")


@app.route("/video_feed")
def video_feed():
    """
    Stream MJPEG del video procesado con landmarks.
    Se consume desde el frontend con una etiqueta <img>.
    """
    return Response(
        _video_generador(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


# ─── API REST ────────────────────────────────────────────────────────────────

@app.route("/api/config", methods=["GET"])
def api_get_config():
    """Retorna la configuración completa actual."""
    return jsonify(_config_manager.obtener_todo())


@app.route("/api/config", methods=["PUT"])
def api_put_config():
    """
    Actualiza los mappings gesto→acción.
    Body esperado: { "mappings": { "gesto": "accion", ... } }
    """
    datos = request.get_json()
    if not datos or "mappings" not in datos:
        return jsonify({"error": "Se requiere el campo 'mappings'"}), 400

    exito = _config_manager.actualizar_mappings_completos(datos["mappings"])
    if exito:
        return jsonify({"status": "ok", "message": "Mappings actualizados"})
    else:
        return jsonify({"error": "Mappings inválidos"}), 400


@app.route("/api/mapping", methods=["PUT"])
def api_put_mapping():
    """
    Actualiza un mapping individual.
    Body esperado: { "gesture": "nombre_gesto", "action": "nombre_accion" }
    """
    datos = request.get_json()
    if not datos or "gesture" not in datos or "action" not in datos:
        return jsonify({"error": "Se requieren 'gesture' y 'action'"}), 400

    exito = _config_manager.actualizar_mapping(datos["gesture"], datos["action"])
    if exito:
        return jsonify({"status": "ok"})
    else:
        return jsonify({"error": "Gesto o acción inválidos"}), 400


@app.route("/api/gestures", methods=["GET"])
def api_get_gestures():
    """Retorna la lista de gestos disponibles con sus labels."""
    return jsonify([
        {"id": g, "label": GESTO_LABELS.get(g, g)}
        for g in GESTOS_VALIDOS
    ])


@app.route("/api/actions", methods=["GET"])
def api_get_actions():
    """Retorna la lista de acciones disponibles con sus labels."""
    return jsonify([
        {"id": a, "label": ACCION_LABELS.get(a, a)}
        for a in ACCIONES_VALIDAS
    ])


@app.route("/api/toggle", methods=["POST"])
def api_toggle():
    """Pausa o reanuda la detección de gestos."""
    pausado = _gesture_engine.toggle_pausa()
    estado = "pausado" if pausado else "activo"
    return jsonify({"status": estado, "paused": pausado})


@app.route("/api/reset", methods=["POST"])
def api_reset():
    """Restaura la configuración a los valores por defecto."""
    _config_manager.resetear()
    _gesture_engine.recargar_parametros()
    return jsonify({"status": "ok", "message": "Configuración restaurada"})


@app.route("/api/status", methods=["GET"])
def api_status():
    """Retorna el estado actual del sistema."""
    return jsonify({
        "paused": _gesture_engine.esta_pausado(),
        "volume": _action_executor.obtener_volumen_actual(),
        "muted": _action_executor.obtener_estado_mute(),
    })


# ─── WebSocket Events ────────────────────────────────────────────────────────

@socketio.on("connect")
def handle_connect():
    """Cliente conectado — enviar estado inicial."""
    print("[WebSocket] Cliente conectado")
    socketio.emit("status_update", {
        "paused": _gesture_engine.esta_pausado() if _gesture_engine else False,
        "volume": _action_executor.obtener_volumen_actual() if _action_executor else 0,
        "muted": _action_executor.obtener_estado_mute() if _action_executor else False,
    })


@socketio.on("disconnect")
def handle_disconnect():
    print("[WebSocket] Cliente desconectado")


def iniciar_servidor(host="127.0.0.1", port=5000):
    """
    Inicia el servidor Flask+SocketIO en un hilo daemon.
    Se ejecuta en segundo plano para no bloquear el loop de captura.
    """
    def _run():
        socketio.run(
            app,
            host=host,
            port=port,
            debug=False,
            use_reloader=False,
            allow_unsafe_werkzeug=True,
        )

    hilo = threading.Thread(target=_run, daemon=True)
    hilo.start()
    print(f"[Servidor] Panel de control en http://{host}:{port}")
    return hilo
