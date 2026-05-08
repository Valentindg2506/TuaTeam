# Enriquecedor de Leads - TuaTeam (Comp-Scrappeo)

Este software automatiza la búsqueda de datos de contacto (Email, Teléfono, Página Web y Nombre del Gerente/Administrador) a partir de una lista de nombres de empresas en un archivo Excel.

## 🚀 Características Principales

1. **Inteligencia de Columnas**: El script no requiere un formato estricto. Busca automáticamente la columna que contenga los nombres de las empresas (reconoce columnas llamadas `nombre`, `empresa`, `nombre_empresa`, `razon social`, `company`, sin importar mayúsculas o minúsculas).
2. **Scraping en Cascada Profundo**:
   - Intenta deducir y raspar la web oficial de la empresa buscando emails de contacto, teléfonos y directivos.
   - Utiliza buscadores como **Bing** para rastrear datos públicos de contacto en directorios y redes sociales de forma automática.
3. **Integración con Datoscif.es por API (Sin Bloqueos)**:
   - Este es el motor principal para los nombres de los directivos. El script se conecta directamente a la **API privada de sugerencias de Datoscif** simulando ser un usuario real.
   - Encuentra la ficha exacta de la empresa en menos de 1 segundo sin pasar por buscadores.
   - Extrae el nombre limpio del Administrador Único, Consejero Delegado, Gerente, Presidente o Apoderado.
   - Aprovecha y extrae teléfono y página web si figuran en Datoscif.
4. **Exportación Automatizada**: No altera tu archivo original. Crea un nuevo archivo llamado `tu_archivo_enriquecido.xlsx` con las nuevas columnas llenas de datos listos para usar en tus campañas comerciales.

---

## 🛠️ Requisitos Previos

Dado que el entorno Linux (Ubuntu/Debian) en el servidor utiliza un entorno Python protegido (`externally-managed-environment`), este proyecto funciona dentro de un Entorno Virtual aislado (`venv`). Todas las dependencias (Pandas, Openpyxl, BeautifulSoup, Requests, Lxml) ya están preinstaladas en este entorno.

**No es necesario instalar nada más.**

---

## 📖 Instrucciones de Uso

Para enriquecer un archivo Excel, sigue estos simples pasos:

### 1. Sube tu archivo Excel
Coloca tu archivo Excel (por ejemplo, `empresas.xlsx`) dentro de la carpeta:
`/var/www/html/TuaTeam/Comp-scrappeo/`

### 2. Abre la terminal y colócate en la carpeta
Abre tu terminal y ejecuta el siguiente comando para entrar en el directorio del proyecto:
```bash
cd /var/www/html/TuaTeam/Comp-scrappeo
```

### 3. Ejecuta el Software
Lanza el comando indicando el nombre de tu archivo Excel. Recuerda usar el Python del entorno virtual (`./venv/bin/python`):

```bash
./venv/bin/python main.py nombre_de_tu_archivo.xlsx
```

**Ejemplo si tu archivo se llama `clientes.xlsx`:**
```bash
./venv/bin/python main.py clientes.xlsx
```

*(Nota: Si no especificas ningún archivo al lanzar el comando, el programa intentará buscar por defecto un archivo que se llame exactamente `empresas.xlsx`).*

### 4. Recoge tus Resultados
Verás en la pantalla cómo el programa va procesando empresa por empresa informándote de los resultados encontrados. 
Al terminar, aparecerá en la misma carpeta un archivo nuevo con el sufijo `_enriquecido.xlsx` (ej. `clientes_enriquecido.xlsx`). Este archivo contendrá las nuevas columnas `email` y `gerente` llenas con todos los datos que el sistema fue capaz de encontrar en Internet.
