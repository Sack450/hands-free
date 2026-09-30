"""
entrenar.py — Script de Entrenamiento de Machine Learning para Gestos

Lee el archivo 'dataset.csv' generado por 'recolector.py', entrena un modelo
RandomForestClassifier y guarda el modelo entrenado como un archivo .pkl
para que 'gesture_engine.py' pueda utilizarlo.
"""

import os
import sys
import pickle
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report

ARCHIVO_DATASET = "dataset.csv"
ARCHIVO_MODELO = os.path.join(os.path.dirname(__file__), "models", "clasificador_gestos.pkl")

def main():
    print("==================================================")
    print("  ENTRENAMIENTO DE MODELO DE GESTOS (ML)")
    print("==================================================")

    if not os.path.exists(ARCHIVO_DATASET):
        print(f"Error: No se encontró '{ARCHIVO_DATASET}'.")
        print("Debes ejecutar 'recolector.py' primero para recolectar datos.")
        sys.exit(1)

    print(f"[1/4] Cargando datos desde {ARCHIVO_DATASET}...")
    try:
        df = pd.read_csv(ARCHIVO_DATASET)
    except Exception as e:
        print(f"Error leyendo el CSV: {e}")
        sys.exit(1)

    if len(df) < 10:
        print("Advertencia: El dataset es muy pequeño. El modelo podría no funcionar bien.")
        print("Se recomienda tener al menos 30-50 muestras por gesto.")

    # Separar características (X) y etiquetas (y)
    # La columna 'label' es la etiqueta, el resto son las coordenadas (x0, y0, z0...)
    X = df.drop('label', axis=1).values
    y = df['label'].values

    # Dividir en entrenamiento y prueba (80% entreno, 20% prueba)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

    print(f"      - Total de muestras: {len(df)}")
    print(f"      - Gestos únicos encontrados: {len(set(y))} {list(set(y))}")

    print("\n[2/4] Entrenando modelo (Random Forest)...")
    # Usamos RandomForest porque es excelente para este tipo de características 
    # y no requiere escalar (aunque ya lo hicimos, lo cual es mejor).
    clf = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1)
    clf.fit(X_train, y_train)

    print("\n[3/4] Evaluando el modelo...")
    y_pred = clf.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    
    print(f"      - Precisión en el set de prueba: {acc * 100:.2f}%")
    if acc < 0.8:
        print("      - Advertencia: La precisión es baja. Intenta recolectar más datos.")
    else:
        print("\nReporte de clasificación detallado:")
        print(classification_report(y_test, y_pred))

    print(f"\n[4/4] Guardando modelo entrenado en {ARCHIVO_MODELO}...")
    # Asegurarse que la carpeta 'models' exista
    os.makedirs(os.path.dirname(ARCHIVO_MODELO), exist_ok=True)
    
    with open(ARCHIVO_MODELO, 'wb') as f:
        pickle.dump(clf, f)

    print("\n¡Listo! El modelo ha sido entrenado y guardado.")
    print("Ahora puedes ejecutar 'main.py' y el motor de gestos utilizará tu IA personalizada.")

if __name__ == "__main__":
    main()
