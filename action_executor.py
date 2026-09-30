"""
action_executor.py — Ejecutor de Acciones del Sistema

Traduce los nombres de acciones (strings) en operaciones reales
del sistema operativo: control de volumen, simulación de teclado,
clicks de mouse, y apertura de aplicaciones.

Dependencias del sistema:
  - pycaw + comtypes: Control de audio nativo de Windows
  - pyautogui: Simulación de mouse y teclado
"""

import time
import pyautogui

from pycaw.pycaw import AudioUtilities


# Desactivar el failsafe de pyautogui (el sistema tiene su propio
# mecanismo de pausa con el gesto "pause_toggle")
pyautogui.FAILSAFE = False
# Pausa mínima entre acciones de pyautogui para evitar conflictos
pyautogui.PAUSE = 0.05


class ActionExecutor:
    """
    Ejecuta acciones del sistema operativo basadas en nombres de acción.
    
    Implementa cooldown entre acciones para evitar ejecuciones
    excesivas cuando un gesto se mantiene activo.
    """

    def __init__(self, config_manager):
        """
        Inicializa el ejecutor con acceso al volumen del sistema.
        
        Args:
            config_manager: Instancia de ConfigManager para leer parámetros
        """
        self._config = config_manager
        self._cooldown_ms = config_manager.obtener("detection", "cooldown_ms") or 300

        # ─── Inicializar control de audio de Windows ──────────────────
        try:
            dispositivos = AudioUtilities.GetSpeakers()
            self._volumen = dispositivos.EndpointVolume
            print("[ActionExecutor] Control de audio inicializado correctamente.")
        except Exception as e:
            print(f"[ActionExecutor] Error inicializando audio: {e}")
            self._volumen = None

        # Timestamp de la última acción ejecutada (para cooldown)
        self._ultimo_tiempo_accion = 0

        # Referencia al motor de gestos (se setea externamente para pause_toggle)
        self._gesture_engine = None

        # Callback para notificar acciones ejecutadas
        self._on_accion = None

        # ─── Mapa de acción → método ─────────────────────────────────
        # Cada acción mapea a una función lambda o método bound
        self._acciones = {
            "none":           lambda: None,
            "volume_up":      self._volumen_subir,
            "volume_down":    self._volumen_bajar,
            "mute_toggle":    self._mute_toggle,
            "scroll_up":      self._scroll_arriba,
            "scroll_down":    self._scroll_abajo,
            "new_tab":        self._nueva_pestana,
            "close_tab":      self._cerrar_pestana,
            "tab_prev":       self._pestana_anterior,
            "tab_next":       self._pestana_siguiente,
            "nav_back":       self._navegar_atras,
            "nav_forward":    self._navegar_adelante,
            "click_left":     self._click_izquierdo,
            "click_right":    self._click_derecho,
            "double_click":   self._doble_click,
            "open_explorer":  self._abrir_explorador,
            "select_all":     self._seleccionar_todo,
            "pause_toggle":   self._pausar_toggle,
        }

    def set_gesture_engine(self, engine):
        """Conecta la referencia al motor de gestos para pause_toggle."""
        self._gesture_engine = engine

    def set_callback(self, callback):
        """
        Registra un callback que se invoca tras ejecutar una acción.
        
        Args:
            callback: Función que recibe (nombre_accion: str, exito: bool)
        """
        self._on_accion = callback

    def ejecutar(self, nombre_accion):
        """
        Ejecuta una acción por su nombre, respetando el cooldown.
        
        Args:
            nombre_accion: String con el nombre de la acción (ej: "volume_up")
        
        Returns:
            True si la acción se ejecutó, False si está en cooldown o es inválida.
        """
        if nombre_accion == "none" or nombre_accion is None:
            return False

        # Verificar cooldown
        ahora = time.time() * 1000
        if (ahora - self._ultimo_tiempo_accion) < self._cooldown_ms:
            return False

        ejecutor = self._acciones.get(nombre_accion)
        if ejecutor is None:
            print(f"[ActionExecutor] Acción desconocida: '{nombre_accion}'")
            return False

        try:
            ejecutor()
            self._ultimo_tiempo_accion = ahora
            print(f"[ActionExecutor] Ejecutado: {nombre_accion}")
            if self._on_accion:
                self._on_accion(nombre_accion, True)
            return True
        except Exception as e:
            print(f"[ActionExecutor] Error ejecutando '{nombre_accion}': {e}")
            if self._on_accion:
                self._on_accion(nombre_accion, False)
            return False

    def ejecutar_para_gesto(self, gesto):
        """
        Busca la acción asignada al gesto y la ejecuta.
        
        Args:
            gesto: Nombre del gesto detectado
        
        Returns:
            Nombre de la acción ejecutada o None si no se ejecutó nada.
        """
        accion = self._config.obtener_accion_para_gesto(gesto)
        if self.ejecutar(accion):
            return accion
        return None

    # ─── Implementación de acciones: VOLUMEN ──────────────────────────────

    def _volumen_subir(self):
        """Incrementa el volumen del sistema en ~5%."""
        if not self._volumen:
            return
        actual = self._volumen.GetMasterVolumeLevelScalar()
        nuevo = min(1.0, actual + 0.05)
        self._volumen.SetMasterVolumeLevelScalar(nuevo, None)

    def _volumen_bajar(self):
        """Decrementa el volumen del sistema en ~5%."""
        if not self._volumen:
            return
        actual = self._volumen.GetMasterVolumeLevelScalar()
        nuevo = max(0.0, actual - 0.05)
        self._volumen.SetMasterVolumeLevelScalar(nuevo, None)

    def _mute_toggle(self):
        """Alterna el estado de silencio del sistema."""
        if not self._volumen:
            return
        estado_actual = self._volumen.GetMute()
        self._volumen.SetMute(not estado_actual, None)

    # ─── Implementación de acciones: SCROLL ───────────────────────────────

    def _scroll_arriba(self):
        """Desplaza hacia arriba (scroll up)."""
        pyautogui.scroll(5)

    def _scroll_abajo(self):
        """Desplaza hacia abajo (scroll down)."""
        pyautogui.scroll(-5)

    # ─── Implementación de acciones: NAVEGACIÓN WEB ───────────────────────

    def _nueva_pestana(self):
        """Abre una nueva pestaña en el navegador (Ctrl+T)."""
        pyautogui.hotkey("ctrl", "t")

    def _cerrar_pestana(self):
        """Cierra la pestaña actual del navegador (Ctrl+W)."""
        pyautogui.hotkey("ctrl", "w")

    def _pestana_anterior(self):
        """Cambia a la pestaña anterior (Ctrl+Shift+Tab)."""
        pyautogui.hotkey("ctrl", "shift", "tab")

    def _pestana_siguiente(self):
        """Cambia a la pestaña siguiente (Ctrl+Tab)."""
        pyautogui.hotkey("ctrl", "tab")

    def _navegar_atras(self):
        """Navega atrás en el historial del navegador (Alt+Left)."""
        pyautogui.hotkey("alt", "left")

    def _navegar_adelante(self):
        """Navega adelante en el historial del navegador (Alt+Right)."""
        pyautogui.hotkey("alt", "right")

    # ─── Implementación de acciones: MOUSE ────────────────────────────────

    def _click_izquierdo(self):
        """Ejecuta un click izquierdo en la posición actual del cursor."""
        pyautogui.click()

    def _click_derecho(self):
        """Ejecuta un click derecho en la posición actual del cursor."""
        pyautogui.click(button="right")

    def _doble_click(self):
        """Ejecuta un doble click en la posición actual del cursor."""
        pyautogui.doubleClick()

    # ─── Implementación de acciones: ARCHIVOS ─────────────────────────────

    def _abrir_explorador(self):
        """Abre el Explorador de archivos de Windows (Win+E)."""
        pyautogui.hotkey("win", "e")

    def _seleccionar_todo(self):
        """Selecciona todo en la ventana activa (Ctrl+A)."""
        pyautogui.hotkey("ctrl", "a")

    # ─── Implementación de acciones: SISTEMA ──────────────────────────────

    def _pausar_toggle(self):
        """Alterna el estado de pausa de la detección de gestos."""
        if self._gesture_engine:
            self._gesture_engine.toggle_pausa()

    # ─── Estado ───────────────────────────────────────────────────────────

    def obtener_volumen_actual(self):
        """
        Retorna el volumen actual del sistema como porcentaje (0-100).
        
        Returns:
            Float entre 0 y 100, o -1 si el control de audio no está disponible.
        """
        if not self._volumen:
            return -1
        return round(self._volumen.GetMasterVolumeLevelScalar() * 100, 1)

    def obtener_estado_mute(self):
        """
        Retorna si el sistema está silenciado.
        
        Returns:
            True si está en mute, False si no, None si no está disponible.
        """
        if not self._volumen:
            return None
        return bool(self._volumen.GetMute())
