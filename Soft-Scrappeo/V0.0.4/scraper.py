"""
Scraper del Ranking Nacional de Empresas (eleconomista.es) v2.
Mejoras:
  - Deduplicación por nombre normalizado
  - División automática competidores/leads
  - Extracción de 3 competidores por lead
"""
import re
import time
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://ranking-empresas.eleconomista.es/ranking_empresas_nacional.html"


# ── Utilidades ────────────────────────────────────────────────────────────────

def normalizar(txt):
    if not txt: return ""
    txt = txt.lower().strip()
    for k, v in {"á":"a","é":"e","í":"i","ó":"o","ú":"u","ñ":"n",
                 "à":"a","è":"e","ì":"i","ò":"o","ù":"u"}.items():
        txt = txt.replace(k, v)
    # Quitar sufijos legales comunes para deduplicar mejor
    for sufijo in [" sl", " sa", " slu", " sau", " slp", " slu.", " sa.", " sl.", " s.a", " s.l"]:
        if txt.endswith(sufijo):
            txt = txt[:-len(sufijo)].strip()
    return txt


def provincia_coincide(prov_dato, prov_filtro):
    if not prov_filtro: return True
    d = normalizar(prov_dato)
    f = normalizar(prov_filtro)
    if d == f: return True
    # "Arava,Álava" → buscar en partes
    for parte in d.split(","):
        if parte.strip() == f: return True
    if f in d or d in f: return True
    return False


FICHA_BASE = "https://ranking-empresas.eleconomista.es/"

def make_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/124.0.0.0 Safari/537.36"),
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9",
        "Connection": "keep-alive",
    })
    return s


def nombre_a_slug(nombre):
    """
    Convierte el nombre de empresa al slug que usa eleconomista en sus URLs.
    Ej: 'PECOMARK SA' -> 'PECOMARK-SA'
    """
    import unicodedata
    # Normalizar unicode (quitar acentos)
    nombre = unicodedata.normalize('NFKD', nombre)
    nombre = ''.join(c for c in nombre if not unicodedata.combining(c))
    # Reemplazar caracteres especiales
    nombre = re.sub(r'[^A-Za-z0-9\s\-]', '', nombre)
    nombre = re.sub(r'\s+', '-', nombre.strip())
    return nombre.upper()


def construir_url_ficha(nombre):
    """Construye la URL de la ficha de empresa en eleconomista."""
    slug = nombre_a_slug(nombre)
    return f"https://ranking-empresas.eleconomista.es/{slug}.html"


def parse_facturacion(texto):
    t = (texto or "").strip()
    solo = t.replace(".", "").replace(",", "").replace(" ", "")
    if solo.isdigit() and len(solo) > 4:
        n = int(solo)
        return n, f"{n:,.0f}".replace(",", ".") + " €"
    t_low = t.lower()
    for clave, num, label in [
        ("corporativa", 50_000_000, "Corporativa (>50M€)"),
        ("grande",      10_000_000, "Grande (>10M€)"),
        ("mediana",      2_000_000, "Mediana (>2M€)"),
        ("pequeña",        500_000, "Pequeña (<2M€)"),
        ("pequena",        500_000, "Pequeña (<2M€)"),
    ]:
        if clave in t_low:
            return num, label
    return None, t or "—"


def fetch_page(session, cnae, pagina):
    for intento in range(3):
        try:
            if intento > 0:
                time.sleep(2 * intento)
                
            if pagina == 1:
                params = {"qSectorNorm": cnae}
                r = session.get(BASE_URL, params=params, timeout=20)
            else:
                ajax_url = "https://ranking-empresas.eleconomista.es/servlet/app/prod/PRINCIPAL_RANKING_EMPRESAS_AJAX/"
                data = {
                    'tipoPagina': 'nacional',
                    'qProvNorm': '',
                    'qSectorNorm': str(cnae),
                    'qVentasNorm': '',
                    'qNombreNorm': '',
                    'qPagina': str(pagina)
                }
                r = session.post(ajax_url, data=data, timeout=20)
                
            r.raise_for_status()
            return BeautifulSoup(r.text, "lxml"), None
        except requests.HTTPError as e:
            code = e.response.status_code
            if code == 403 and intento < 2:
                time.sleep(4)
                continue
            return None, f"HTTP {code}"
        except Exception as e:
            if intento < 2:
                time.sleep(2)
                continue
            return None, str(e)
    return None, "Sin conexión tras 3 intentos"


def parse_tabla(soup, provincia_filtro=None):
    """
    Parsea la tabla del ranking. 7 cols: pos|evol|nombre(link)|fact|cnae|prov|btn
    """
    rows = []
    table = soup.find("table")
    if not table: return rows

    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 7:
            continue

        pos_txt  = tds[0].get_text(strip=True)
        evol_txt = tds[1].get_text(strip=True)
        nombre   = tds[2].get_text(strip=True)
        factura  = tds[3].get_text(strip=True)
        sector   = tds[4].get_text(strip=True)
        prov     = tds[5].get_text(strip=True)

        if not nombre or nombre.lower() in ("nombre", "empresa"):
            continue

        if provincia_filtro and not provincia_coincide(prov, provincia_filtro):
            continue

        # URL ficha — buscar en links de la fila, o construir desde nombre
        url = ""
        for td in tds:
            for a in td.find_all("a", href=True):
                href = a["href"]
                if href and not href.startswith(("javascript:", "#", "mailto:")):
                    if href.startswith("http"):
                        url = href
                    else:
                        url = "https://ranking-empresas.eleconomista.es" + href
                    break
            if url: break
        # Si no encontramos URL, construir desde el nombre
        if not url and nombre:
            url = construir_url_ficha(nombre)

        try:    posicion = int(re.sub(r"\D", "", pos_txt))
        except: posicion = None

        evol_num, tendencia = None, "Igual"
        m = re.search(r"([\d\.]+)", evol_txt)
        if m:
            try: evol_num = int(m.group(1).replace(".", ""))
            except: pass
        if "Sube" in evol_txt:   tendencia = "Sube"
        elif "Baja" in evol_txt: tendencia = "Baja"
        elif "ND"   in evol_txt: tendencia = "ND"

        fact_num, fact_label = parse_facturacion(factura)

        rows.append({
            "nombre":          nombre,
            "cnae":            sector,
            "provincia":       prov,
            "posicion":        posicion,
            "evolucion":       evol_num,
            "tendencia":       tendencia,
            "facturacion_num": fact_num,
            "facturacion_raw": fact_label,
            "url":             url,
        })
    return rows


def deduplicar(empresas):
    """
    Elimina duplicados manteniendo el de mejor posición (menor número).
    Dos empresas son duplicado si su nombre normalizado coincide.
    """
    vistas = {}  # nombre_norm → empresa
    for e in empresas:
        clave = normalizar(e["nombre"])
        if clave not in vistas:
            vistas[clave] = e
        else:
            # Quedarse con la de mejor posición (posición numérica menor)
            actual_pos = vistas[clave].get("posicion") or 999999
            nueva_pos  = e.get("posicion") or 999999
            if nueva_pos < actual_pos:
                vistas[clave] = e
    return list(vistas.values())


def calcular_competidores(lead, pool, ratio_min=3, ratio_max=30, n=3):
    """
    Devuelve los N mejores competidores para un lead.
    Prioriza: misma provincia → ratio 3-30× → mejor posición.
    """
    cands = [c for c in pool if normalizar(c["nombre"]) != normalizar(lead["nombre"])]
    if not cands:
        return []

    misma_prov = [c for c in cands if provincia_coincide(c["provincia"], lead["provincia"])]
    fuente = misma_prov if len(misma_prov) >= 1 else cands

    # Filtrar por ratio si hay facturación
    if lead.get("facturacion_num") and lead["facturacion_num"] > 0:
        con_ratio = [
            c for c in fuente
            if c.get("facturacion_num") and
               ratio_min <= c["facturacion_num"] / lead["facturacion_num"] <= ratio_max
        ]
        # Si con ratio no hay suficientes, relajar el filtro
        if len(con_ratio) >= 1:
            fuente = con_ratio
        elif misma_prov:
            fuente = misma_prov  # Misma provincia sin restricción de ratio

    # Ordenar por posición (mejor = menor número)
    ordenados = sorted(
        [c for c in fuente if c.get("posicion")],
        key=lambda x: x["posicion"]
    )
    return ordenados[:n]


def scrape_cnae(cnae, provincia=None, paginas=3, delay=1.5, on_progress=None):
    """
    Descarga N páginas del ranking nacional filtrado por CNAE.
    Devuelve (empresas_leads, competidores_pool, error, meta_dict).
    meta_dict incluye: paginas_reales (int), agotado (bool).
    """
    session = make_session()
    try:
        session.get("https://ranking-empresas.eleconomista.es/", timeout=15)
        time.sleep(1)
    except:
        pass

    # Descargar TODAS las páginas a nivel nacional (sin filtro de provincia)
    # para tener un pool de competidores completo
    todas_nacional = []
    todas_provincia = []
    paginas_vacias = 0
    paginas_con_datos = 0   # Cuántas páginas tuvieron datos reales
    agotado = False         # True si el CNAE se agotó antes de llegar al límite

    for p in range(1, paginas + 1):
        if on_progress:
            on_progress(
                int(p / paginas * 85),
                f"Descargando página {p}/{paginas}…"
            )

        soup, err = fetch_page(session, cnae, p)
        if err:
            if todas_nacional:
                agotado = True
                break  # Tenemos algo, no es fatal
            return [], [], err, {"paginas_reales": paginas_con_datos, "agotado": True}

        rows_nac = parse_tabla(soup, provincia_filtro=None)
        if not rows_nac:
            paginas_vacias += 1
            if paginas_vacias >= 2:
                agotado = True
                break  # Se acabó el ranking del CNAE
        else:
            paginas_vacias = 0
            paginas_con_datos += 1
            todas_nacional.extend(rows_nac)

            # Solo las de la provincia buscada
            if provincia:
                todas_provincia.extend(
                    parse_tabla(soup, provincia_filtro=provincia)
                )

        time.sleep(delay)

    meta = {"paginas_reales": paginas_con_datos, "agotado": agotado}

    if not todas_nacional:
        return [], [], f"No se encontraron empresas con CNAE {cnae}. Verifica el código.", meta

    # Deduplicar
    todas_nacional = deduplicar(todas_nacional)
    if provincia:
        todas_provincia = deduplicar(todas_provincia)

    # Los leads son: empresas de la provincia (si se filtró) o todas
    leads_raw = todas_provincia if provincia else todas_nacional

    if not leads_raw and provincia:
        return [], [], (
            f"No hay empresas con CNAE {cnae} en {provincia} en las {paginas} páginas. "
            f"Hay {len(todas_nacional)} empresas del sector en España. "
            f"Prueba a aumentar el nº de páginas."
        ), meta

    if on_progress:
        on_progress(90, f"{len(leads_raw)} empresas encontradas. Calculando competidores…")

    # Pool de competidores = TODAS las empresas nacionales del sector
    # (incluso las de otras provincias) para tener opciones
    pool_competidores = todas_nacional

    return leads_raw, pool_competidores, None, meta
