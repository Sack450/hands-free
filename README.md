# Hands-Free 🖐️🤖

**Hands-Free** es un sistema de control del sistema operativo mediante gestos de manos en tiempo real, impulsado por visión por computadora y Machine Learning. Permite interactuar con la computadora (control de cursor, clic, volumen, multimedia, atajos de teclado y comandos personalizados) mediante la cámara web y una interfaz web interactiva para configuración y monitoreo.

---

## 🚀 Características principales

- **Control del Cursor en Tiempo Real**: Movimiento fluido del puntero mapeando la posición de la mano en pantalla.
- **Reconocimiento de Gestos**: Clasificación de gestos basados en puntos de referencia de la mano (*landmarks* de MediaPipe).
- **Ejecutor de Acciones Configurable**:
  - Control de Volumen (silenciar, subir/bajar volumen general y por aplicación en Windows usando PyCaw/COM).
  - Acciones de Teclado y Atajos (presionar teclas, combinaciones como `Ctrl+C`, `Alt+Tab`, etc.).
  - Control Multimedia (reproducir/pausar, siguiente/anterior pista).
  - Lanzamiento de Comandos del Sistema.
- **Entrenamiento y Recolección de Datos**:
  - `recolector.py`: Herramienta interactiva para capturar datos de gestos.
  - `entrenar.py`: Entrenamiento de modelos de clasificación (Scikit-Learn).
- **Panel Web de Control**: Interfaz construida con Flask y Socket.IO para visualizar la cámara en streaming, monitorear gestos detectados en tiempo real y cambiar configuraciones.

---

## 🛠️ Requisitos e Instalación

### Pre-requisitos
- Python 3.9 o superior
- Cámara web funcional
- Sistema Operativo Windows (algunas funciones de audio usan PyCaw específicas de Windows)

### Instalación

1. **Clonar el repositorio:**
   ```bash
   git clone https://github.com/Sack450/hands-free.git
   cd hands-free
   ```

2. **Crear y activar un entorno virtual (Recomendado):**
   ```bash
   python -m venv venv
   # En Windows:
   venv\Scripts\activate
   # En Linux/macOS:
   source venv/bin/activate
   ```

3. **Instalar dependencias:**
   ```bash
   pip install -r requirements.txt
   ```

---

## 📖 Modo de Uso

### 1. Ejecutar el Sistema Principal
Para iniciar el control por gestos y el servidor web:
```bash
python main.py
```
Abre tu navegador web y entra a `http://localhost:5000` para acceder a la interfaz de control y monitoreo.

### 2. Recolectar nuevos gestos (Opcional)
Si deseas registrar nuevos gestos para entrenar un modelo propio:
```bash
python recolector.py
```
> **Nota**: Los datos capturados se guardan localmente en `dataset.csv` (este archivo está excluido del control de versiones).

### 3. Entrenar el Modelo
Una vez recolectados datos en `dataset.csv`, entrena el modelo ejecutando:
```bash
python entrenar.py
```
El modelo entrenado se guardará en la carpeta `models/`.

---

## 📂 Estructura del Proyecto

```
hands-free/
├── main.py                # Punto de entrada principal (loop de captura, detección y servidor)
├── gesture_engine.py      # Procesamiento con MediaPipe y detección de gestos
├── action_executor.py     # Ejecución de acciones (volumen, teclado, comandos)
├── cursor_controller.py   # Control del movimiento del cursor del mouse
├── config_manager.py      # Gestión de la configuración (config.json)
├── recolector.py          # Captura de datos para nuevos gestos
├── entrenar.py            # Entrenamiento del modelo de Machine Learning
├── app.py                 # Servidor Flask y Socket.IO
├── config.json            # Archivo de configuración por defecto
├── requirements.txt       # Librerías de Python requeridas
├── static/                # Archivos estáticos de la interfaz web (CSS/JS)
├── templates/             # Plantillas HTML de la interfaz web
└── models/                # Modelos de ML entrenados
```

---

## 📝 Licencia

Este proyecto está distribuido bajo la licencia MIT.
