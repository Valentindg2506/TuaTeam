import pandas as pd
import time
import os
from enriquecer import enrich_lead

def procesar_excel(file_path):
    print(f"Cargando archivo {file_path}...")
    try:
        df = pd.read_excel(file_path)
    except Exception as e:
        print(f"Error al leer el excel: {e}")
        return

    # Verificar si la columna 'nombre' u otras similares existen
    col_nombre = None
    nombres_posibles = ['nombre', 'empresa', 'nombre_empresa', 'nombre empresa', 'razon social', 'razón social', 'company']
    for col in df.columns:
        if str(col).strip().lower() in nombres_posibles:
            col_nombre = col
            break
    
    if not col_nombre:
        print("El archivo Excel no contiene una columna llamada 'nombre'.")
        print(f"Columnas encontradas: {list(df.columns)}")
        return

    print("Archivo cargado correctamente. Iniciando enriquecimiento...")

    # Crear columnas si no existen
    if 'email' not in df.columns:
        df['email'] = None
    if 'gerente' not in df.columns:
        df['gerente'] = None

    total = len(df)
    for index, row in df.iterrows():
        nombre = row[col_nombre]
        if pd.isna(nombre) or not str(nombre).strip():
            continue

        nombre_str = str(nombre).strip()
        print(f"\n[{index+1}/{total}] Buscando datos para: {nombre_str}")

        lead_dict = {"nombre": nombre_str, "provincia": ""}
        resultado = enrich_lead(lead_dict)

        email = resultado.get("email")
        gerente = resultado.get("gerente")

        if email:
            df.at[index, 'email'] = email
        if gerente:
            df.at[index, 'gerente'] = gerente

        print(f"   -> Email: {email} | Gerente: {gerente}")
        time.sleep(1)  # Pequeña pausa para no saturar

    # Guardar los resultados en un nuevo archivo
    output_file = file_path.replace(".xlsx", "_enriquecido.xlsx")
    if output_file == file_path:
        output_file = "resultado_enriquecido.xlsx"
        
    try:
        df.to_excel(output_file, index=False)
        print(f"\nProceso completado con éxito. Resultados guardados en: {output_file}")
    except Exception as e:
        print(f"Error al guardar el excel: {e}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        archivo = sys.argv[1]
    else:
        archivo = "empresas.xlsx"
        print(f"No se especificó un archivo Excel como argumento. Buscando '{archivo}' por defecto...")
    
    if os.path.exists(archivo):
        procesar_excel(archivo)
    else:
        print(f"El archivo '{archivo}' no existe en la ruta actual.")
        print("Uso: python main.py <archivo.xlsx>")
