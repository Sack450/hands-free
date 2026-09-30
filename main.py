"""
main.py — Punto de Entrada del Sistema Gestos

Orquesta todos los módulos:
1. Inicializa la cámara con OpenCV
2. Crea instancias del motor de gestos, ejecutor de acciones y config manager
3. Lanza el servidor Flask en un hilo separado
4. Ejecuta el loop principal: captura → procesa → detecta → ejecuta → emite
5. Maneja el cierre limpio (Ctrl+C) liberando todos los recursos

Uso:
    python main.py
"""

import os
import sys
import time
import signal
import threading

import cv2

# Módulos del proyecto
from config_manager import ConfigManager
from gesture_engine import GestureEngine
from action_executor import ActionExecutor
from cursor_controller import CursorController
from app import (
    inicializar_app, iniciar_servidor,
    emitir_gesto, emitir_accion, emitir_estado,
)


# ─── Variables globales del sistema ───────────────────────────────────────────
ejecutando = True      # Flag para el loop principal
camara = None          # Objeto cv2.VideoCapture
frame_actual = None    # Frame procesado más reciente (para el stream MJPEG)
frame_lock = threading.Lock()  # Lock para acceso concurrente al frame


def senal_salida(sig, frame):
    """Manejador de señal para cierre limpio (Ctrl+C)."""
    global ejecutando
    print("\n[Main] Señal de salida recibida. Cerrando...")
    ejecutando = False


def generador_video():
    """
    Generador que produce frames JPEG para el stream MJPEG.
    Flask consume este generador en la ruta /video_feed.
    """
    global frame_actual
    while ejecutando:
        with frame_lock:
            if frame_actual is None:
                continue
            # Codificar el frame como JPEG
            ret, buffer = cv2.imencode(".jpg", frame_actual, [
                cv2.IMWRITE_JPEG_QUALITY, 80  # Calidad 80% (balance calidad/velocidad)
            ])
            if not ret:
                continue
            frame_bytes = buffer.tobytes()

        # Formato multipart para MJPEG
        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
        )
        # Limitar FPS del stream para no saturar la red
        time.sleep(0.033)  # ~30 FPS


def main():
    """Función principal que orquesta todo el sistema."""
    global ejecutando, camara, frame_actual

    # Registrar manejador de señales para cierre limpio
    signal.signal(signal.SIGINT, senal_salida)
    signal.signal(signal.SIGTERM, senal_salida)

    print("=" * 60)
    print("  GESTOS -- Controlador de Interfaz por Gestos de Mano")
    print("=" * 60)

    # ─── 1. Cargar configuración ──────────────────────────────────────────
    ruta_config = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    config = ConfigManager(ruta_config)
    print("[Main] Configuración cargada.")

    # ─── 2. Inicializar cámara ────────────────────────────────────────────
    cam_config = config.obtener("camera")
    device_index = cam_config.get("device_index", 0)
    cam_width = cam_config.get("width", 640)
    cam_height = cam_config.get("height", 480)

    print(f"[Main] Abriendo cámara (dispositivo {device_index})...")
    camara = cv2.VideoCapture(device_index, cv2.CAP_DSHOW)
    camara.set(cv2.CAP_PROP_FRAME_WIDTH, cam_width)
    camara.set(cv2.CAP_PROP_FRAME_HEIGHT, cam_height)

    if not camara.isOpened():
        print("[Main] ERROR: No se pudo abrir la cámara.")
        print("       Verifica que la cámara esté conectada y no esté en uso.")
        sys.exit(1)

    print(f"[Main] Cámara abierta ({cam_width}x{cam_height}).")

    # ─── 3. Inicializar módulos ───────────────────────────────────────────
    motor_gestos = GestureEngine(config)
    ejecutor_acciones = ActionExecutor(config)
    controlador_cursor = CursorController(smoothing=0.4)

    # Conectar el motor de gestos al ejecutor (para pause_toggle)
    ejecutor_acciones.set_gesture_engine(motor_gestos)

    # ─── 4. Registrar callbacks para WebSocket ────────────────────────────
    # Cuando se detecta un gesto, emitir al frontend Y ejecutar la acción
    def on_gesto_detectado(nombre_gesto):
        """Callback del motor de gestos — emite al WS y ejecuta la acción."""
        emitir_gesto(nombre_gesto)
        accion = ejecutor_acciones.ejecutar_para_gesto(nombre_gesto)
        if accion:
            emitir_accion(accion, True)

    motor_gestos.set_callback(on_gesto_detectado)

    # ─── 5. Inicializar servidor web ──────────────────────────────────────
    inicializar_app(config, motor_gestos, ejecutor_acciones, generador_video)

    server_config = config.obtener("server")
    host = server_config.get("host", "127.0.0.1")
    port = server_config.get("port", 5000)

    iniciar_servidor(host, port)

    # ─── 6. Loop principal ────────────────────────────────────────────────
    print("[Main] Sistema listo. Mostrando cámara y detectando gestos...")
    print(f"[Main] Panel de control: http://{host}:{port}")
    print("[Main] Presiona 'Q' en la ventana de cámara o Ctrl+C para salir.")
    print("-" * 60)

    # Contadores para calcular FPS
    fps_tiempo_inicio = time.time()
    fps_contador = 0
    fps_actual = 0
    ultimo_envio_estado = 0

    try:
        while ejecutando:
            ret, frame = camara.read()
            if not ret:
                print("[Main] Error leyendo frame de la cámara.")
                time.sleep(0.1)
                continue

            # Procesar frame con el motor de gestos
            frame_anotado, gesto, landmarks, gesto_raw = motor_gestos.procesar_frame(frame)

            # Control de cursor si la mano está abierta y no está pausado
            if gesto_raw == "open_palm" and landmarks and not motor_gestos.esta_pausado():
                centro_palma = landmarks[motor_gestos.PALMA_CENTRO]
                controlador_cursor.actualizar(centro_palma[0], centro_palma[1])
            else:
                controlador_cursor.reset()

            # Actualizar el frame global para el stream MJPEG
            with frame_lock:
                frame_actual = frame_anotado.copy()

            # Calcular FPS
            fps_contador += 1
            tiempo_transcurrido = time.time() - fps_tiempo_inicio
            if tiempo_transcurrido >= 1.0:
                fps_actual = round(fps_contador / tiempo_transcurrido)
                fps_contador = 0
                fps_tiempo_inicio = time.time()

            # Enviar estado periódicamente al frontend (~cada 2 segundos)
            ahora = time.time()
            if (ahora - ultimo_envio_estado) >= 2.0:
                emitir_estado({
                    "fps": fps_actual,
                    "paused": motor_gestos.esta_pausado(),
                    "volume": ejecutor_acciones.obtener_volumen_actual(),
                    "muted": ejecutor_acciones.obtener_estado_mute(),
                })
                ultimo_envio_estado = ahora

            # Mostrar ventana local de OpenCV (opcional, para debug)
            cv2.imshow("Gestos - Camara", frame_anotado)

            # 'Q' para salir desde la ventana de OpenCV
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q") or key == ord("Q"):
                ejecutando = False
                break

    except KeyboardInterrupt:
        print("\n[Main] Interrupción de teclado.")
    finally:
        # ─── 7. Cierre limpio ─────────────────────────────────────────────
        print("[Main] Cerrando sistema...")

        if camara is not None and camara.isOpened():
            camara.release()
            print("[Main] Cámara liberada.")

        motor_gestos.liberar()
        cv2.destroyAllWindows()

        print("[Main] Hasta luego!")


if __name__ == "__main__":
    main()
