"""
recolector.py — Herramienta de recolección de datos para Machine Learning

Este script captura el video de la cámara, detecta los landmarks de la mano,
los normaliza y los guarda en un archivo CSV cuando presionas una tecla.
"""

import cv2
import os
import csv
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import (
    HandLandmarker,
    HandLandmarkerOptions,
    HandLandmarksConnections,
    RunningMode,
    drawing_utils,
)

# Archivo de salida
ARCHIVO_DATASET = "dataset.csv"

# Diccionario de gestos a recolectar
# Puedes cambiar las teclas o agregar nuevos gestos aquí
GESTOS = {
    ord('1'): "fist",
    ord('2'): "open_palm",
    ord('3'): "point_up",
    ord('4'): "peace",
    ord('5'): "pinch",
    ord('6'): "thumb_up",
    ord('7'): "thumb_down"
}

def normalizar_landmarks(landmarks):
    """
    Normaliza los landmarks para que sean invariantes a la escala y posición.
    1. Centra los puntos respecto a la muñeca.
    2. Escala los valores usando la distancia máxima.
    3. Devuelve un array plano de 63 características.
    """
    base_x, base_y, base_z = landmarks[0]
    
    puntos_relativos = []
    for x, y, z in landmarks:
        puntos_relativos.append((x - base_x, y - base_y, z - base_z))
        
    # Encontrar el valor máximo absoluto para escalar
    max_val = 0.0
    for x, y, z in puntos_relativos:
        max_val = max(max_val, abs(x), abs(y), abs(z))
        
    if max_val == 0:
        max_val = 1.0 # Evitar división por cero
        
    # Escalar y aplanar a una sola lista de 63 elementos
    caracteristicas = []
    for x, y, z in puntos_relativos:
        caracteristicas.extend([x / max_val, y / max_val, z / max_val])
        
    return caracteristicas

def main():
    print("==================================================")
    print("  RECOLECTOR DE GESTOS - CREACIÓN DE DATASET")
    print("==================================================")
    
    # Escribir encabezados si el archivo no existe
    if not os.path.exists(ARCHIVO_DATASET):
        with open(ARCHIVO_DATASET, mode='w', newline='') as f:
            writer = csv.writer(f)
            header = ["label"] + [f"{coord}{i}" for i in range(21) for coord in ('x', 'y', 'z')]
            writer.writerow(header)
            
    # Inicializar MediaPipe
    modelo_path = os.path.join(os.path.dirname(__file__), "models", "hand_landmarker.task")
    opciones = HandLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=modelo_path),
        running_mode=RunningMode.IMAGE,
        num_hands=1,
        min_hand_detection_confidence=0.7,
        min_hand_presence_confidence=0.5,
    )
    landmarker = HandLandmarker.create_from_options(opciones)
    
    # Inicializar cámara
    camara = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    
    # Contadores de muestras para la sesión actual
    contadores = {nombre: 0 for nombre in GESTOS.values()}
    
    print("\nInstrucciones:")
    for tecla, nombre in GESTOS.items():
        print(f"  Presiona '{chr(tecla)}' -> Guardar muestra de '{nombre}'")
    print("\n  Presiona 'Q' -> Salir y guardar todo")
    print("\nRecomendación: Mueve tu mano en diferentes ángulos y distancias al tomar muestras.")
    print("Intenta conseguir al menos 30-50 muestras por gesto.")
    
    while True:
        ret, frame = camara.read()
        if not ret:
            break
            
        frame = cv2.flip(frame, 1) # Espejo
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
        
        resultado = landmarker.detect(mp_image)
        
        landmarks_normalizados = None
        
        # Dibujar mano si se detecta
        if resultado.hand_landmarks:
            hand_lms = resultado.hand_landmarks[0]
            drawing_utils.draw_landmarks(frame, hand_lms, HandLandmarksConnections.HAND_CONNECTIONS)
            
            # Extraer landmarks
            puntos = [(lm.x, lm.y, lm.z) for lm in hand_lms]
            landmarks_normalizados = normalizar_landmarks(puntos)
            
            cv2.putText(frame, "Mano Detectada - Lista para capturar", (10, 30), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        else:
            cv2.putText(frame, "Esperando mano...", (10, 30), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                        
        # Mostrar contadores
        y_pos = 60
        for nombre, count in contadores.items():
            cv2.putText(frame, f"{nombre}: {count}", (10, y_pos), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
            y_pos += 20
            
        cv2.imshow("Recolector de Gestos", frame)
        
        tecla = cv2.waitKey(1) & 0xFF
        
        if tecla == ord('q') or tecla == ord('Q'):
            break
            
        if tecla in GESTOS and landmarks_normalizados:
            gesto_nombre = GESTOS[tecla]
            
            # Guardar en CSV
            with open(ARCHIVO_DATASET, mode='a', newline='') as f:
                writer = csv.writer(f)
                fila = [gesto_nombre] + landmarks_normalizados
                writer.writerow(fila)
                
            contadores[gesto_nombre] += 1
            print(f"[{gesto_nombre}] Muestra #{contadores[gesto_nombre]} guardada.")
            
            # Flash visual para feedback
            cv2.rectangle(frame, (0, 0), (frame.shape[1], frame.shape[0]), (255, 255, 255), -1)
            cv2.imshow("Recolector de Gestos", frame)
            cv2.waitKey(50)

    camara.release()
    cv2.destroyAllWindows()
    print("\n[Recolector] Sesión terminada. Datos guardados en dataset.csv")

if __name__ == "__main__":
    main()
