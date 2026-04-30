"""
Configuración de Radar CRM.
Edita los valores de DB_* para conectar con tu MySQL/MariaDB.
"""
import os

# ── Base de datos MySQL/MariaDB ───────────────────────────────────────────────
DB_USER     = os.environ.get("RADAR_DB_USER",     "radar")
DB_PASSWORD = os.environ.get("RADAR_DB_PASSWORD", "Radar123$")
DB_HOST     = os.environ.get("RADAR_DB_HOST",     "localhost")
DB_PORT     = os.environ.get("RADAR_DB_PORT",     "3306")
DB_NAME     = os.environ.get("RADAR_DB_NAME",     "radar_crm")

SQLALCHEMY_DATABASE_URI = (
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    "?charset=utf8mb4"
)
SQLALCHEMY_TRACK_MODIFICATIONS = False
SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 300}

# ── Seguridad ─────────────────────────────────────────────────────────────────
SECRET_KEY = os.environ.get("RADAR_SECRET_KEY", "cambiame-en-produccion-por-algo-aleatorio")

# ── Scraping ──────────────────────────────────────────────────────────────────
SCRAPE_DELAY_SECONDS   = 2.0
# Modo exhaustivo por defecto: cada asignación intenta barrer todo el CNAE/provincia.
# (Se mantienen constantes legacy para compatibilidad con asignaciones antiguas).
SCRAPE_EXHAUSTIVE_DEFAULT = True
SCRAPE_PAGES_DEFAULT   = 0
SCRAPE_MAX_PAGES       = 0
# Salvaguardas para evitar loops infinitos cuando el portal responde mal.
SCRAPE_EXHAUSTIVE_MAIN_MAX_PAGES = 260
SCRAPE_EXHAUSTIVE_MAIN_EMPTY_STREAK = 3
SCRAPE_EXHAUSTIVE_FALLBACK_MAX_FICHAS = 4200
# Número de scrapers simultáneos hacia eleconomista (subirlo aumenta riesgo 429).
SCRAPE_MAX_CONCURRENT_JOBS = 1
# Reintentos automáticos de una asignación cuando aparece bloqueo 429.
SCRAPE_RETRY_429_ATTEMPTS = 6
# Reintentos inteligentes ante fallos transitorios de fuentes fallback.
SCRAPE_RESCUE_ATTEMPTS = 4
ENRICHMENT_TIMEOUT     = 10
ENRICHMENT_MAX_WORKERS = 10
# Segunda pasada de enriquecimiento para leads incompletos.
ENRICHMENT_SECOND_PASS = True
ENRICHMENT_MIN_COMPLETENESS = 2

# ── Roles ─────────────────────────────────────────────────────────────────────
ROLE_ADMIN      = "admin"
ROLE_SUPERVISOR = "supervisor"
ROLE_COMERCIAL  = "comercial"
ROLES           = [ROLE_ADMIN, ROLE_SUPERVISOR, ROLE_COMERCIAL]

# ── Estados Kanban para licitaciones ──────────────────────────────────────────
KANBAN_ESTADOS = [
    ("nuevo",        "Nuevo",               "#64748b"),
    ("contactado",   "1er Contacto",        "#3b82f6"),
    ("interesado",   "Interesado",          "#a855f7"),
    ("propuesta",    "Propuesta Enviada",   "#f59e0b"),
    ("negociacion",  "Negociación",         "#ec4899"),
    ("ganado",       "Cliente",             "#16a34a"),
    ("perdido",      "Descartado",          "#dc2626"),
]
