"""
Scraper del Ranking Nacional de Empresas (eleconomista.es).
"""
import re
import time
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://ranking-empresas.eleconomista.es/ranking_empresas_nacional.html"


def normalizar(txt):
    """Normaliza texto para comparación: minúsculas, sin tildes, sin comas."""
    if not txt: return ""
    txt = txt.lower().strip()
    for k, v in {"á":"a","é":"e","í":"i","ó":"o","ú":"u","ñ":"n",
                 "à":"a","è":"e","ì":"i","ò":"o","ù":"u",
                 "ä":"a","ë":"e","ï":"i","ö":"o","ü":"u"}.items():
        txt = txt.replace(k, v)
    return txt

def provincia_coincide(prov_dato, prov_filtro):
    """
    Comprueba si la provincia del dato coincide con el filtro.
    Maneja casos como "Arava,Álava" que debe coincidir con "Álava".
    """
    if not prov_filtro:
        return True
    d = normalizar(prov_dato)
    f = normalizar(prov_filtro)
    # Coincidencia exacta
    if d == f:
        return True
    # El dato puede contener comas: "Arava,Álava" → split y buscar en partes
    partes = [p.strip() for p in d.split(",")]
    if f in partes:
        return True
    # Coincidencia parcial (el filtro está contenido en el dato o viceversa)
    if f in d or d in f:
        return True
    return False


def make_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/124.0.0.0 Safari/537.36"),
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9",
    })
    return s


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
    params = {"qSectorNorm": cnae}
    if pagina > 1:
        params["pagina"] = pagina
    for intento in range(3):
        try:
            if intento > 0:
                time.sleep(2 * intento)
            r = session.get(BASE_URL, params=params, timeout=20)
            r.raise_for_status()
            return BeautifulSoup(r.text, "lxml"), None
        except requests.HTTPError as e:
            if e.response.status_code == 403 and intento < 2:
                time.sleep(4)
                continue
            return None, f"HTTP {e.response.status_code}"
        except Exception as e:
            if intento < 2:
                time.sleep(2)
                continue
            return None, str(e)
    return None, "Sin conexión"


def parse_tabla(soup, provincia_filtro=None):
    """
    Devuelve lista de empresas con datos básicos.
    La tabla tiene 7 columnas: pos | evol | nombre(link) | fact | CNAE | prov | botón
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

        if provincia_filtro and not provincia_coincide(prov, provincia_filtro):
            continue

        # URL ficha
        url = ""
        for td in tds:
            a = td.find("a", href=True)
            if a:
                href = a["href"]
                if href and not href.startswith(("javascript:", "#")):
                    url = href if href.startswith("http") else \
                          "https://ranking-empresas.eleconomista.es" + href
                    break

        try: posicion = int(re.sub(r"\D", "", pos_txt))
        except: posicion = None

        evol_num, tendencia = None, "Igual"
        m = re.search(r"([\d\.]+)", evol_txt)
        if m:
            try: evol_num = int(m.group(1).replace(".", ""))
            except: pass
        if "Sube" in evol_txt:   tendencia = "Sube"
        elif "Baja" in evol_txt: tendencia = "Baja"
        elif "ND" in evol_txt:   tendencia = "ND"

        fact_num, fact_label = parse_facturacion(factura)

        rows.append({
            "nombre":            nombre,
            "cnae":              sector,
            "provincia":         prov,
            "posicion":          posicion,
            "evolucion":         evol_num,
            "tendencia":         tendencia,
            "facturacion_num":   fact_num,
            "facturacion_raw":   fact_label,
            "url":               url,
        })
    return rows


def scrape_cnae(cnae, provincia=None, paginas=3, delay=1.5, on_progress=None):
    """
    Descarga N páginas del ranking nacional filtrado por CNAE.
    Si hay provincia, filtra localmente.
    Si la provincia tiene pocas empresas, continúa aunque la página esté vacía.
    Devuelve (lista_empresas, error).
    """
    session = make_session()
    try:
        session.get("https://ranking-empresas.eleconomista.es/", timeout=15)
        time.sleep(1)
    except:
        pass

    empresas = []
    paginas_vacias_sin_filtro = 0

    for p in range(1, paginas + 1):
        if on_progress:
            on_progress(
                int((p / paginas) * 100),
                f"Página {p}/{paginas} — {len(empresas)} encontradas{' en ' + provincia if provincia else ''}…"
            )
        soup, err = fetch_page(session, cnae, p)
        if err:
            # Si ya tenemos algo, no es error fatal
            if empresas:
                break
            return [], err

        # Sin filtro de provincia: si la página está vacía, el CNAE no tiene más datos
        rows_sin_filtro = parse_tabla(soup, provincia_filtro=None)
        if not rows_sin_filtro:
            paginas_vacias_sin_filtro += 1
            if paginas_vacias_sin_filtro >= 2:
                break  # El ranking se acabó para este CNAE

        # Con filtro de provincia
        rows = parse_tabla(soup, provincia_filtro=provincia)
        empresas.extend(rows)
        time.sleep(delay)

    if not empresas and provincia:
        # Mensaje claro: encontramos empresas del CNAE pero no en esa provincia
        total_cnae = sum(1 for _ in parse_tabla(soup, provincia_filtro=None)) if soup else 0
        return [], (
            f"No se encontraron empresas con CNAE {cnae} en {provincia} "
            f"en las primeras {paginas} páginas. "
            f"Prueba a aumentar el número de páginas (hay {total_cnae * paginas} "
            f"empresas del sector en España, pero pocas pueden estar en esa provincia)."
        )

    return empresas, None
