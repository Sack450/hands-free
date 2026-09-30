"""
config_manager.py — Gestor de Configuración Persistente

Maneja la carga, validación y guardado de la configuración del sistema.
Permite actualizar mappings gesto→acción en caliente sin reiniciar.
La persistencia se hace en un archivo JSON local.
"""

import json
import os
import threading
from copy import deepcopy


# ─── Constantes: gestos y acciones válidas ────────────────────────────────────
# Estas listas definen el "vocabulario" del sistema.
# Cualquier mapping debe usar un gesto y una acción de estas listas.
GESTOS_VALIDOS = [
    "fist",          # Puño cerrado
    "open_palm",     # Palma abierta
    "point_up",      # Dedo índice señalando
    "peace",         # Señal de paz (índice + medio)
    "pinch",         # Pinza (pulgar + índice juntos)
    "thumb_up",      # Pulgar arriba
    "thumb_down",    # Pulgar abajo
    "swipe_left",    # Deslizar a la izquierda
    "swipe_right",   # Deslizar a la derecha
    "swipe_up",      # Deslizar hacia arriba
    "swipe_down",    # Deslizar hacia abajo
]

ACCIONES_VALIDAS = [
    "none",           # Sin acción (deshabilitar gesto)
    "volume_up",      # Subir volumen +5%
    "volume_down",    # Bajar volumen -5%
    "mute_toggle",    # Silenciar / Activar audio
    "scroll_up",      # Desplazamiento hacia arriba
    "scroll_down",    # Desplazamiento hacia abajo
    "new_tab",        # Abrir nueva pestaña (Ctrl+T)
    "close_tab",      # Cerrar pestaña actual (Ctrl+W)
    "tab_prev",       # Pestaña anterior (Ctrl+Shift+Tab)
    "tab_next",       # Pestaña siguiente (Ctrl+Tab)
    "nav_back",       # Navegar atrás (Alt+Left)
    "nav_forward",    # Navegar adelante (Alt+Right)
    "click_left",     # Click izquierdo
    "click_right",    # Click derecho
    "double_click",   # Doble click
    "open_explorer",  # Abrir explorador (Win+E)
    "select_all",     # Seleccionar todo (Ctrl+A)
    "pause_toggle",   # Pausar/Reanudar detección
]

# Descripciones legibles para la UI
GESTO_LABELS = {
    "fist": "✊ Puño cerrado",
    "open_palm": "🖐️ Palma abierta",
    "point_up": "☝️ Señalar arriba",
    "peace": "✌️ Señal de paz",
    "pinch": "🤏 Pinza",
    "thumb_up": "👍 Pulgar arriba",
    "thumb_down": "👎 Pulgar abajo",
    "swipe_left": "👈 Deslizar izquierda",
    "swipe_right": "👉 Deslizar derecha",
    "swipe_up": "⬆️ Deslizar arriba",
    "swipe_down": "⬇️ Deslizar abajo",
}

ACCION_LABELS = {
    "none": "🚫 Sin acción",
    "volume_up": "🔊 Subir volumen",
    "volume_down": "🔉 Bajar volumen",
    "mute_toggle": "🔇 Silenciar/Activar",
    "scroll_up": "⬆️ Scroll arriba",
    "scroll_down": "⬇️ Scroll abajo",
    "new_tab": "➕ Nueva pestaña",
    "close_tab": "❌ Cerrar pestaña",
    "tab_prev": "◀️ Pestaña anterior",
    "tab_next": "▶️ Pestaña siguiente",
    "nav_back": "⏪ Ir atrás",
    "nav_forward": "⏩ Ir adelante",
    "click_left": "🖱️ Click izquierdo",
    "click_right": "🖱️ Click derecho",
    "double_click": "🖱️ Doble click",
    "open_explorer": "📁 Abrir explorador",
    "select_all": "📋 Seleccionar todo",
    "pause_toggle": "⏸️ Pausar/Reanudar",
}

# Configuración por defecto (se usa si config.json no existe o está corrupto)
CONFIG_DEFECTO = {
    "camera": {
        "device_index": 0,
        "width": 640,
        "height": 480,
    },
    "detection": {
        "max_hands": 1,
        "min_detection_confidence": 0.7,
        "min_tracking_confidence": 0.6,
        "swipe_threshold": 0.15,
        "swipe_frames": 8,
        "pinch_threshold": 0.06,
        "debounce_ms": 600,
        "cooldown_ms": 300,
    },
    "mappings": {
        "fist": "mute_toggle",
        "open_palm": "none",
        "point_up": "scroll_up",
        "peace": "scroll_down",
        "pinch": "click_left",
        "thumb_up": "volume_up",
        "thumb_down": "volume_down",
        "swipe_left": "tab_prev",
        "swipe_right": "tab_next",
        "swipe_up": "new_tab",
        "swipe_down": "close_tab",
    },
    "server": {
        "host": "127.0.0.1",
        "port": 5000,
    },
}


class ConfigManager:
    """
    Gestiona la configuración del sistema con persistencia en JSON.
    
    Thread-safe: usa un lock para proteger lecturas/escrituras
    concurrentes entre el hilo principal y el servidor Flask.
    """

    def __init__(self, ruta_config="config.json"):
        # Ruta absoluta al archivo de configuración
        self._ruta = os.path.abspath(ruta_config)
        self._lock = threading.Lock()
        self._config = {}
        self._cargar()

    def _cargar(self):
        """
        Carga la configuración desde disco.
        Si el archivo no existe o está corrupto, usa los valores por defecto
        y crea/sobrescribe el archivo para tener un estado limpio.
        """
        with self._lock:
            if os.path.exists(self._ruta):
                try:
                    with open(self._ruta, "r", encoding="utf-8") as f:
                        datos = json.load(f)
                    # Mezclar con defaults para cubrir claves faltantes
                    self._config = self._mezclar_con_defaults(datos)
                    print(f"[ConfigManager] Configuración cargada desde {self._ruta}")
                except (json.JSONDecodeError, IOError) as e:
                    print(f"[ConfigManager] Error leyendo config: {e}. Usando defaults.")
                    self._config = deepcopy(CONFIG_DEFECTO)
            else:
                print("[ConfigManager] Archivo de config no encontrado. Creando con defaults.")
                self._config = deepcopy(CONFIG_DEFECTO)
            # Guardar para asegurar que el archivo refleje el estado completo
            self._guardar_sin_lock()

    def _mezclar_con_defaults(self, datos):
        """
        Mezcla recursivamente los datos del usuario con los valores por defecto.
        Esto asegura que las claves nuevas agregadas en actualizaciones
        se incluyan sin perder la configuración personalizada del usuario.
        """
        resultado = deepcopy(CONFIG_DEFECTO)
        for clave, valor in datos.items():
            if clave in resultado and isinstance(resultado[clave], dict) and isinstance(valor, dict):
                resultado[clave].update(valor)
            else:
                resultado[clave] = valor
        return resultado

    def _guardar_sin_lock(self):
        """Guarda la configuración a disco (sin adquirir lock — uso interno)."""
        try:
            with open(self._ruta, "w", encoding="utf-8") as f:
                json.dump(self._config, f, indent=4, ensure_ascii=False)
        except IOError as e:
            print(f"[ConfigManager] Error guardando config: {e}")

    def guardar(self):
        """Guarda la configuración actual a disco (thread-safe)."""
        with self._lock:
            self._guardar_sin_lock()

    def obtener_todo(self):
        """Retorna una copia completa de la configuración."""
        with self._lock:
            return deepcopy(self._config)

    def obtener(self, seccion, clave=None):
        """
        Obtiene un valor de configuración.
        
        Args:
            seccion: Sección principal (camera, detection, mappings, server)
            clave: Clave específica dentro de la sección (opcional)
        
        Returns:
            El valor solicitado, o la sección completa si no se especifica clave.
        """
        with self._lock:
            if seccion not in self._config:
                return None
            if clave is None:
                return deepcopy(self._config[seccion])
            return self._config[seccion].get(clave)

    def obtener_mappings(self):
        """Retorna una copia del diccionario de mappings gesto→acción."""
        return self.obtener("mappings")

    def actualizar_mapping(self, gesto, accion):
        """
        Actualiza un mapping individual gesto→acción.
        
        Valida que tanto el gesto como la acción sean válidos
        antes de persistir el cambio.
        
        Returns:
            True si se actualizó correctamente, False si los valores son inválidos.
        """
        if gesto not in GESTOS_VALIDOS:
            print(f"[ConfigManager] Gesto inválido: '{gesto}'")
            return False
        if accion not in ACCIONES_VALIDAS:
            print(f"[ConfigManager] Acción inválida: '{accion}'")
            return False

        with self._lock:
            self._config["mappings"][gesto] = accion
            self._guardar_sin_lock()
        print(f"[ConfigManager] Mapping actualizado: {gesto} → {accion}")
        return True

    def actualizar_mappings_completos(self, nuevos_mappings):
        """
        Reemplaza todos los mappings de una vez.
        Valida cada par antes de aplicar cambios.
        
        Returns:
            True si todos son válidos y se actualizaron, False si hay errores.
        """
        # Validar todo antes de aplicar cambios (operación atómica)
        for gesto, accion in nuevos_mappings.items():
            if gesto not in GESTOS_VALIDOS:
                print(f"[ConfigManager] Gesto inválido en batch: '{gesto}'")
                return False
            if accion not in ACCIONES_VALIDAS:
                print(f"[ConfigManager] Acción inválida en batch: '{accion}'")
                return False

        with self._lock:
            self._config["mappings"] = dict(nuevos_mappings)
            self._guardar_sin_lock()
        print("[ConfigManager] Todos los mappings actualizados correctamente.")
        return True

    def actualizar_deteccion(self, parametros):
        """
        Actualiza parámetros de detección (umbrales, sensibilidad, etc.).
        Solo actualiza las claves proporcionadas, preserva el resto.
        """
        claves_validas = set(CONFIG_DEFECTO["detection"].keys())
        with self._lock:
            for clave, valor in parametros.items():
                if clave in claves_validas:
                    self._config["detection"][clave] = valor
            self._guardar_sin_lock()

    def resetear(self):
        """Restaura toda la configuración a los valores por defecto."""
        with self._lock:
            self._config = deepcopy(CONFIG_DEFECTO)
            self._guardar_sin_lock()
        print("[ConfigManager] Configuración restaurada a defaults.")

    def obtener_accion_para_gesto(self, gesto):
        """
        Busca la acción asignada a un gesto específico.
        
        Returns:
            Nombre de la acción o "none" si el gesto no tiene mapping.
        """
        with self._lock:
            return self._config["mappings"].get(gesto, "none")
