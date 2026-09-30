"""
gesture_engine.py -- Motor de Deteccion de Gestos

Usa MediaPipe Tasks HandLandmarker para extraer 21 landmarks de la mano
y aplica heuristicas geometricas para clasificar el gesto actual.
Incluye deteccion de swipes mediante analisis de velocidad en un
buffer circular de posiciones historicas.

Landmarks de referencia (MediaPipe):
  0: Muneca
  1-4: Pulgar (CMC, MCP, IP, TIP)
  5-8: Indice (MCP, PIP, DIP, TIP)
  9-12: Medio (MCP, PIP, DIP, TIP)
  13-16: Anular (MCP, PIP, DIP, TIP)
  17-20: Menique (MCP, PIP, DIP, TIP)
"""

import math
import os
import time
import pickle
from collections import deque

import cv2
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import (
    HandLandmarker,
    HandLandmarkerOptions,
    HandLandmarksConnections,
    RunningMode,
    drawing_utils,
)


class GestureEngine:
    """
    Motor de reconocimiento de gestos basado en heuristicas geometricas.

    Procesa frames de OpenCV, extrae landmarks con MediaPipe Tasks API,
    y clasifica el gesto usando reglas sobre posiciones relativas
    de las articulaciones.
    """

    # --- Indices de landmarks por dedo ---
    # Cada dedo tiene: [MCP, PIP, DIP, TIP]
    # El pulgar es especial: [CMC, MCP, IP, TIP]
    PULGAR_TIP = 4
    PULGAR_IP = 3
    PULGAR_MCP = 2

    INDICE_TIP = 8
    INDICE_DIP = 7
    INDICE_PIP = 6
    INDICE_MCP = 5

    MEDIO_TIP = 12
    MEDIO_PIP = 10

    ANULAR_TIP = 16
    ANULAR_PIP = 14

    MENIQUE_TIP = 20
    MENIQUE_PIP = 18

    # Centro de la palma (aproximacion con MCP del medio)
    PALMA_CENTRO = 9

    MUNECA = 0

    def __init__(self, config_manager):
        """
        Inicializa MediaPipe HandLandmarker (Tasks API) y los parametros de deteccion.

        Args:
            config_manager: Instancia de ConfigManager para leer parametros
        """
        self._config = config_manager
        self._params = config_manager.obtener("detection")

        # Ruta al modelo descargado
        modelo_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "models", "hand_landmarker.task"
        )

        if not os.path.exists(modelo_path):
            raise FileNotFoundError(
                f"Modelo no encontrado en: {modelo_path}\n"
                "Descarga el modelo con:\n"
                "  Invoke-WebRequest -Uri 'https://storage.googleapis.com/mediapipe-models/"
                "hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task' "
                "-OutFile 'models/hand_landmarker.task'"
            )

        # Inicializar HandLandmarker con la nueva Tasks API
        # Usamos VIDEO mode porque procesamos frames secuenciales con timestamps
        opciones = HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=modelo_path),
            running_mode=RunningMode.VIDEO,
            num_hands=self._params.get("max_hands", 1),
            min_hand_detection_confidence=self._params.get("min_detection_confidence", 0.7),
            min_hand_presence_confidence=0.5,
            min_tracking_confidence=self._params.get("min_tracking_confidence", 0.6),
        )
        self._landmarker = HandLandmarker.create_from_options(opciones)

        # Conexiones para dibujar la mano
        self._hand_connections = HandLandmarksConnections.HAND_CONNECTIONS

        # Timestamp incremental para modo VIDEO (microsegundos)
        self._frame_timestamp_ms = 0

        # Buffer circular para deteccion de swipes
        # Almacena tuplas (timestamp, x_centro, y_centro)
        tamano_buffer = self._params.get("swipe_frames", 8)
        self._historial_posiciones = deque(maxlen=tamano_buffer)

        # Debouncing: evita reportar el mismo gesto repetidamente
        self._ultimo_gesto = None
        self._ultimo_tiempo_gesto = 0
        self._debounce_ms = self._params.get("debounce_ms", 600)

        # Umbrales configurables
        self._pinch_threshold = self._params.get("pinch_threshold", 0.06)
        self._swipe_threshold = self._params.get("swipe_threshold", 0.15)

        # Callback para notificar gestos detectados
        self._on_gesto = None

        # Estado de la deteccion
        self._pausado = False

        # --- Integración de Modelo ML (Opcional) ---
        self._ml_model = None
        ruta_ml = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "models", "clasificador_gestos.pkl"
        )
        if os.path.exists(ruta_ml):
            try:
                with open(ruta_ml, 'rb') as f:
                    self._ml_model = pickle.load(f)
                print(f"[GestureEngine] Modelo de IA cargado correctamente.")
            except Exception as e:
                print(f"[GestureEngine] Error al cargar modelo IA: {e}")

        print("[GestureEngine] HandLandmarker inicializado (Tasks API).")

    def set_callback(self, callback):
        """
        Registra un callback que se invoca cuando se detecta un gesto nuevo.

        Args:
            callback: Funcion que recibe (nombre_gesto: str)
        """
        self._on_gesto = callback

    def pausar(self):
        """Pausa la deteccion de gestos."""
        self._pausado = True

    def reanudar(self):
        """Reanuda la deteccion de gestos."""
        self._pausado = False

    def esta_pausado(self):
        """Retorna True si la deteccion esta pausada."""
        return self._pausado

    def toggle_pausa(self):
        """Alterna el estado de pausa."""
        self._pausado = not self._pausado
        return self._pausado

    def recargar_parametros(self):
        """Recarga los parametros de deteccion desde el ConfigManager."""
        self._params = self._config.obtener("detection")
        self._pinch_threshold = self._params.get("pinch_threshold", 0.06)
        self._swipe_threshold = self._params.get("swipe_threshold", 0.15)
        self._debounce_ms = self._params.get("debounce_ms", 600)

    def procesar_frame(self, frame):
        """
        Procesa un frame BGR de OpenCV y detecta gestos.

        Args:
            frame: Imagen BGR de OpenCV (numpy array)

        Returns:
            Tupla (frame_anotado, gesto_detectado, landmarks_data, gesto_raw)
            - frame_anotado: Frame con landmarks dibujados
            - gesto_detectado: Nombre del gesto o None si no hay mano/pausa
            - landmarks_data: Lista de landmarks normalizados o None
            - gesto_raw: Gesto detectado en el frame actual sin debounce
        """
        if frame is None:
            return frame, None, None

        # Voltear horizontalmente para efecto espejo (mas intuitivo)
        frame = cv2.flip(frame, 1)
        alto, ancho, _ = frame.shape

        # Convertir BGR a RGB para MediaPipe
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Crear mp.Image desde el array numpy
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)

        # Incrementar timestamp para modo VIDEO
        self._frame_timestamp_ms += 33  # ~30 FPS

        # Detectar landmarks
        resultado = self._landmarker.detect_for_video(mp_image, self._frame_timestamp_ms)

        # Preparar frame anotado (copia para dibujar)
        frame_anotado = frame.copy()

        gesto_detectado = None
        landmarks_data = None
        gesto_raw = None

        if resultado.hand_landmarks:
            for hand_lms in resultado.hand_landmarks:
                # Dibujar landmarks y conexiones en el frame
                drawing_utils.draw_landmarks(
                    frame_anotado,
                    hand_lms,
                    self._hand_connections,
                )

                # Extraer landmarks como lista de (x, y, z)
                landmarks = []
                for lm in hand_lms:
                    landmarks.append((lm.x, lm.y, lm.z))
                landmarks_data = landmarks

                if not self._pausado:
                    # Detectar gesto estatico primero
                    gesto = self._detectar_gesto_estatico(landmarks)

                    # Si no hay gesto estatico claro, verificar swipes
                    if gesto is None:
                        gesto = self._detectar_swipe(landmarks)

                    gesto_raw = gesto

                    # Aplicar debouncing
                    gesto_detectado = self._aplicar_debounce(gesto)

                    # Dibujar el nombre del gesto en el frame
                    if gesto_detectado:
                        self._dibujar_gesto(frame_anotado, gesto_detectado, ancho)

                # Actualizar historial de posiciones para swipe detection
                centro = landmarks[self.PALMA_CENTRO]
                self._historial_posiciones.append(
                    (time.time(), centro[0], centro[1])
                )

        else:
            # No se detecta mano -- limpiar historial
            self._historial_posiciones.clear()

        return frame_anotado, gesto_detectado, landmarks_data, gesto_raw

    # --- Deteccion de gestos estaticos ---

    def _normalizar_landmarks(self, landmarks):
        """Normaliza landmarks para inferencia ML (idéntico a recolector.py)"""
        base_x, base_y, base_z = landmarks[0]
        puntos_relativos = [(x - base_x, y - base_y, z - base_z) for x, y, z in landmarks]
        
        max_val = 0.0
        for x, y, z in puntos_relativos:
            max_val = max(max_val, abs(x), abs(y), abs(z))
            
        if max_val == 0: max_val = 1.0
            
        caracteristicas = []
        for x, y, z in puntos_relativos:
            caracteristicas.extend([x / max_val, y / max_val, z / max_val])
        return caracteristicas

    def _detectar_gesto_estatico(self, landmarks):
        """
        Clasifica el gesto actual usando el modelo ML personalizado si existe.
        Si no existe, utiliza heurísticas matemáticas como respaldo (fallback).
        """
        if self._ml_model is not None:
            # --- Inferencia con IA ---
            features = self._normalizar_landmarks(landmarks)
            prediccion = self._ml_model.predict([features])
            return prediccion[0]

        # --- Fallback: Heurísticas (Matemática Básica) ---
        dedos = self._obtener_estado_dedos(landmarks)
        pulgar, indice, medio, anular, menique = dedos

        # --- Pinza: pulgar e indice muy cerca ---
        dist_pinza = self._distancia(
            landmarks[self.PULGAR_TIP],
            landmarks[self.INDICE_TIP]
        )
        if dist_pinza < self._pinch_threshold:
            return "pinch"

        # --- Pulgar arriba: solo pulgar extendido, dedos cerrados ---
        if pulgar and not indice and not medio and not anular and not menique:
            # Determinar si es arriba o abajo comparando TIP vs MCP del pulgar
            if landmarks[self.PULGAR_TIP][1] < landmarks[self.PULGAR_MCP][1]:
                return "thumb_up"
            else:
                return "thumb_down"

        # --- Senalar: solo indice extendido ---
        if not pulgar and indice and not medio and not anular and not menique:
            return "point_up"

        # --- Paz: indice + medio extendidos, resto cerrado ---
        if not pulgar and indice and medio and not anular and not menique:
            return "peace"

        # --- Puno cerrado: ningun dedo extendido ---
        if not any(dedos):
            return "fist"

        # --- Palma abierta: todos los dedos extendidos ---
        if all(dedos):
            return "open_palm"

        # No se reconoce un gesto claro
        return None

    def _obtener_estado_dedos(self, landmarks):
        """
        Determina que dedos estan extendidos.

        Para los dedos 2-5: compara la coordenada Y del TIP vs PIP.
        Si TIP esta mas arriba (Y menor), el dedo esta extendido.

        Para el pulgar: compara la coordenada X del TIP vs IP,
        ajustando segun la lateralidad de la mano (se aproxima
        con la posicion relativa del pulgar respecto a la muneca).

        Returns:
            Tupla de 5 booleanos: (pulgar, indice, medio, anular, menique)
        """
        # Determinar si es mano izquierda o derecha (aproximacion)
        # Si el pulgar MCP esta a la derecha del menique MCP, es mano derecha
        es_mano_derecha = landmarks[self.PULGAR_MCP][0] > landmarks[self.MENIQUE_PIP][0]

        # Pulgar: comparar X del TIP vs IP
        # En mano derecha, el pulgar extendido tiene TIP mas a la derecha
        if es_mano_derecha:
            pulgar = landmarks[self.PULGAR_TIP][0] > landmarks[self.PULGAR_IP][0]
        else:
            pulgar = landmarks[self.PULGAR_TIP][0] < landmarks[self.PULGAR_IP][0]

        # Dedos 2-5: comparar Y del TIP vs PIP (Y menor = mas arriba en la imagen)
        indice = landmarks[self.INDICE_TIP][1] < landmarks[self.INDICE_PIP][1]
        medio = landmarks[self.MEDIO_TIP][1] < landmarks[self.MEDIO_PIP][1]
        anular = landmarks[self.ANULAR_TIP][1] < landmarks[self.ANULAR_PIP][1]
        menique = landmarks[self.MENIQUE_TIP][1] < landmarks[self.MENIQUE_PIP][1]

        return (pulgar, indice, medio, anular, menique)

    # --- Deteccion de swipes ---

    def _detectar_swipe(self, landmarks):
        """
        Detecta movimientos rapidos (swipes) analizando el desplazamiento
        del centro de la palma en los ultimos N frames.

        Un swipe se registra cuando:
        - Hay suficientes posiciones en el historial
        - El desplazamiento total excede el umbral
        - El movimiento ocurrio en un tiempo razonable (<0.5s)
        """
        if len(self._historial_posiciones) < 4:
            return None

        # Comparar la posicion mas antigua con la mas reciente
        tiempo_inicio, x_inicio, y_inicio = self._historial_posiciones[0]
        tiempo_fin, x_fin, y_fin = self._historial_posiciones[-1]

        delta_tiempo = tiempo_fin - tiempo_inicio

        # El swipe debe ser rapido (menos de 0.5 segundos)
        if delta_tiempo <= 0 or delta_tiempo > 0.5:
            return None

        delta_x = x_fin - x_inicio
        delta_y = y_fin - y_inicio

        # Determinar la direccion dominante
        if abs(delta_x) > abs(delta_y):
            # Movimiento horizontal
            if abs(delta_x) > self._swipe_threshold:
                # Limpiar historial para evitar swipes repetidos
                self._historial_posiciones.clear()
                # Nota: en la imagen espejada, izquierda/derecha estan invertidos
                return "swipe_right" if delta_x > 0 else "swipe_left"
        else:
            # Movimiento vertical
            if abs(delta_y) > self._swipe_threshold:
                self._historial_posiciones.clear()
                return "swipe_down" if delta_y > 0 else "swipe_up"

        return None

    # --- Utilidades ---

    def _distancia(self, p1, p2):
        """Calcula la distancia euclidiana 2D entre dos landmarks."""
        return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)

    def _aplicar_debounce(self, gesto):
        """
        Evita que el mismo gesto se dispare repetidamente.

        Solo reporta un gesto si:
        - Es diferente al ultimo gesto reportado, O
        - Ha pasado suficiente tiempo desde la ultima vez que se reporto

        Returns:
            El nombre del gesto si pasa el debounce, None en caso contrario.
        """
        if gesto is None:
            # Resetear el estado cuando no hay gesto
            self._ultimo_gesto = None
            return None

        ahora = time.time() * 1000  # Milisegundos

        if gesto != self._ultimo_gesto:
            # Gesto nuevo -- reportar inmediatamente
            self._ultimo_gesto = gesto
            self._ultimo_tiempo_gesto = ahora
            if self._on_gesto:
                self._on_gesto(gesto)
            return gesto
        elif (ahora - self._ultimo_tiempo_gesto) > self._debounce_ms:
            # Mismo gesto pero ya paso el tiempo de debounce -- reportar de nuevo
            self._ultimo_tiempo_gesto = ahora
            if self._on_gesto:
                self._on_gesto(gesto)
            return gesto

        return None

    # Mapa de labels ASCII-safe para el overlay de OpenCV
    # (cv2.putText no soporta emojis Unicode)
    _GESTO_LABELS_ASCII = {
        "fist": "Puno cerrado",
        "open_palm": "Palma abierta",
        "point_up": "Senalar",
        "peace": "Paz",
        "pinch": "Pinza",
        "thumb_up": "Pulgar arriba",
        "thumb_down": "Pulgar abajo",
        "swipe_left": "Swipe izquierda",
        "swipe_right": "Swipe derecha",
        "swipe_up": "Swipe arriba",
        "swipe_down": "Swipe abajo",
    }

    def _dibujar_gesto(self, frame, gesto, ancho_frame):
        """Dibuja el nombre del gesto detectado en la parte superior del frame."""
        label = self._GESTO_LABELS_ASCII.get(gesto, gesto)

        # Fondo semitransparente para el texto
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (ancho_frame, 50), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)

        # Texto del gesto
        cv2.putText(
            frame, label, (10, 35),
            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 200), 2,
            cv2.LINE_AA
        )

    def liberar(self):
        """Libera los recursos de MediaPipe."""
        self._landmarker.close()
        print("[GestureEngine] Recursos liberados.")
