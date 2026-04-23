# Scraper de Competidores — Aplicación Web

Herramienta para generar automáticamente un Excel con leads y sus competidores 
más relevantes a partir de ranking-empresas.eleconomista.es

## Estructura de archivos

```
app/
├── app.py              ← Servidor web (Flask)
└── templates/
    └── index.html      ← Interfaz de usuario
```

## Instalación (una sola vez)

```bash
pip install flask requests beautifulsoup4 openpyxl lxml
```

## Cómo ejecutar

```bash
cd app
python app.py
```

Después abrir en el navegador: **http://localhost:5000**

## Uso

1. Introducir el **código CNAE** del sector (o usar uno de los ejemplos rápidos)
2. Seleccionar **provincia** (opcional — vacío = búsqueda nacional)
3. Pulsar **Generar Excel**
4. Esperar a que termine el proceso (barra de progreso en pantalla)
5. Pulsar **Descargar** para obtener el Excel

## El Excel generado tiene 4 hojas

| Hoja | Contenido |
|---|---|
| **Leads** | Empresas medianas/pequeñas del sector (posibles clientes) |
| **Competidores** | Top del ranking — las más grandes del sector |
| **Resumen Lead vs Competidor** | Cada lead emparejado con su competidor óptimo + ratio de tamaño |
| **Leyenda** | Explicación de campos y colores |

## Colores en el Excel

- 🟢 **Verde** — la empresa sube posiciones en el ranking (crecimiento)  
- 🔴 **Rojo** — la empresa baja posiciones (decrecimiento)  
- ⬜ **Gris** — posición estable

## Opciones avanzadas

| Opción | Descripción | Por defecto |
|---|---|---|
| Páginas de competidores | Cuántas páginas del top del ranking (25 empresas/pág) | 2 |
| Páginas de leads | Cuántas páginas de empresas medianas/pequeñas | 3 |
| Ratio mínimo | Factor mínimo de tamaño del competidor vs lead | 3x |
| Ratio máximo | Factor máximo | 20x |

## Nota sobre bloqueos

El sitio puede bloquear peticiones si se hacen demasiado rápido.  
Si aparece un error 403, esperar 2-3 minutos y reintentar.  
El script ya incluye pausas entre peticiones para minimizar este riesgo.

## Fuente de datos

- **Sitio**: ranking-empresas.eleconomista.es  
- **Proveedor**: eInforma / INFORMA D&B  
- **Datos**: ejercicio fiscal 2023, publicados en 2024
