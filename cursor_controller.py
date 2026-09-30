"""
cursor_controller.py — Controlador de Cursor
Maneja el movimiento continuo del mouse con suavizado (EMA)
usando la API nativa de Windows (ctypes) para lograr cero latencia
y mínima sobrecarga de CPU (más eficiente que pyautogui).
"""
import ctypes

class CursorController:
    def __init__(self, smoothing=0.4):
        self.user32 = ctypes.windll.user32
        # Cargar dimensiones de la pantalla primaria
        self.screen_width = self.user32.GetSystemMetrics(0)
        self.screen_height = self.user32.GetSystemMetrics(1)
        
        # Factor de suavizado (0.0 a 1.0). Menor = más suave, Mayor = más rápido
        self.smoothing = smoothing
        
        self.curr_x = None
        self.curr_y = None

        # Márgenes para alcanzar los bordes de la pantalla sin sacar la mano de la cámara
        # 15% horizontal y 20% vertical
        self.margin_x = 0.15
        self.margin_y = 0.20
        
    def actualizar(self, raw_x, raw_y):
        """
        Actualiza la posición del mouse dados x, y normalizados (0-1).
        Aplica márgenes y un filtro de media móvil exponencial (EMA) para evitar temblores.
        """
        # Mapear de [margin, 1 - margin] a [0, 1]
        mapped_x = (raw_x - self.margin_x) / (1.0 - 2 * self.margin_x)
        mapped_y = (raw_y - self.margin_y) / (1.0 - 2 * self.margin_y)
        
        # Clampear a [0, 1]
        mapped_x = max(0.0, min(1.0, mapped_x))
        mapped_y = max(0.0, min(1.0, mapped_y))
        
        # Convertir a píxeles absolutos
        target_x = int(mapped_x * self.screen_width)
        target_y = int(mapped_y * self.screen_height)
        
        if self.curr_x is None or self.curr_y is None:
            self.curr_x = target_x
            self.curr_y = target_y
        else:
            # Filtro EMA
            self.curr_x = self.curr_x + self.smoothing * (target_x - self.curr_x)
            self.curr_y = self.curr_y + self.smoothing * (target_y - self.curr_y)
            
        # Llamada directa a Win32 API (optimizada)
        self.user32.SetCursorPos(int(self.curr_x), int(self.curr_y))
        
    def reset(self):
        """Resetea el filtro de suavizado cuando se pierde el tracking o cambia el gesto."""
        self.curr_x = None
        self.curr_y = None
