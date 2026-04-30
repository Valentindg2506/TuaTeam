"""
Scraper del Ranking Nacional de Empresas (eleconomista.es) v2.
Mejoras:
  - Deduplicación por nombre normalizado
  - División automática competidores/leads
  - Extracción de 3 competidores por lead
"""
import re
import time
import random
import threading
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait, as_completed
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs, unquote, quote_plus

try:
    import config as _cfg
except Exception:
    _cfg = None

try:
    from cnae_catalog import CNAE_CATALOG as _CNAE_CATALOG
except Exception:
    _CNAE_CATALOG = {}

BASE_URL = "https://ranking-empresas.eleconomista.es/ranking_empresas_nacional.html"
AJAX_URL = "https://ranking-empresas.eleconomista.es/servlet/app/prod/PRINCIPAL_RANKING_EMPRESAS_AJAX/"

SCRAPE_EXHAUSTIVE_MAIN_MAX_PAGES = int(
    getattr(_cfg, "SCRAPE_EXHAUSTIVE_MAIN_MAX_PAGES", 260) if _cfg else 260
)
SCRAPE_EXHAUSTIVE_MAIN_EMPTY_STREAK = int(
    getattr(_cfg, "SCRAPE_EXHAUSTIVE_MAIN_EMPTY_STREAK", 3) if _cfg else 3
)
SCRAPE_EXHAUSTIVE_FALLBACK_MAX_FICHAS = int(
    getattr(_cfg, "SCRAPE_EXHAUSTIVE_FALLBACK_MAX_FICHAS", 4200) if _cfg else 4200
)

SCRAPE_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

FALLBACK_EXCLUDED_HOSTS = {
    "duckduckgo.com",
    "google.com",
    "bing.com",
    "supercontable.com",
    "infocnae.com",
    "actividadeseconomicas.net",
    "wikipedia.org",
    "rae.es",
    "ine.es",
    "camara.es",
    "cnae.com.es",
    "agenciatributaria.gob.es",
}

PROV_TO_EMPRESASCIF_SLUG = {
    "alava": "alava",
    "albacete": "albacete",
    "alicante": "alicante",
    "almeria": "almeria",
    "asturias": "asturias",
    "avila": "avila",
    "badajoz": "badajoz",
    "islas baleares": "baleares",
    "barcelona": "barcelona",
    "bizkaia": "vizcaya",
    "burgos": "burgos",
    "caceres": "caceres",
    "cadiz": "cadiz",
    "cantabria": "cantabria",
    "castellon": "castellon",
    "ciudad real": "ciudad-real",
    "cordoba": "cordoba",
    "a coruna": "la-coruna",
    "cuenca": "cuenca",
    "girona": "girona",
    "gipuzkoa": "guipuzcoa",
    "granada": "granada",
    "guadalajara": "guadalajara",
    "huelva": "huelva",
    "huesca": "huesca",
    "jaen": "jaen",
    "la rioja": "la-rioja",
    "las palmas": "las-palmas",
    "leon": "leon",
    "lleida": "lleida",
    "lugo": "lugo",
    "madrid": "madrid",
    "malaga": "malaga",
    "murcia": "murcia",
    "navarra": "navarra",
    "ourense": "orense",
    "palencia": "palencia",
    "pontevedra": "pontevedra",
    "salamanca": "salamanca",
    "segovia": "segovia",
    "sevilla": "sevilla",
    "soria": "soria",
    "tarragona": "tarragona",
    "tenerife": "santa-cruz-de-tenerife",
    "teruel": "teruel",
    "toledo": "toledo",
    "valencia": "valencia",
    "valladolid": "valladolid",
    "zamora": "zamora",
    "zaragoza": "zaragoza",
}

# Rate limiter global por proceso para no saturar la IP cuando hay varias asignaciones.
_RL_LOCK = threading.Lock()
_RL_NEXT_TS = 0.0
_RL_BLOCK_UNTIL = 0.0
_RL_PENALTY = 0.0

PROV_ALIAS = {
    "alava": "alava",
    "araba": "alava",
    "arava": "alava",
    "albacete": "albacete",
    "alicante": "alicante",
    "almeria": "almeria",
    "asturias": "asturias",
    "avila": "avila",
    "badajoz": "badajoz",
    "barcelona": "barcelona",
    "baleares": "islas baleares",
    "islas baleares": "islas baleares",
    "illes balears": "islas baleares",
    "bizkaia": "bizkaia",
    "vizcaya": "bizkaia",
    "burgos": "burgos",
    "caceres": "caceres",
    "cadiz": "cadiz",
    "cantabria": "cantabria",
    "castellon": "castellon",
    "castello": "castellon",
    "ciudad real": "ciudad real",
    "cordoba": "cordoba",
    "coruna": "a coruna",
    "a coruna": "a coruna",
    "la coruna": "a coruna",
    "cuenca": "cuenca",
    "girona": "girona",
    "gerona": "girona",
    "gipuzkoa": "gipuzkoa",
    "guipuzcoa": "gipuzkoa",
    "granada": "granada",
    "guadalajara": "guadalajara",
    "huelva": "huelva",
    "huesca": "huesca",
    "jaen": "jaen",
    "la rioja": "la rioja",
    "rioja": "la rioja",
    "las palmas": "las palmas",
    "palmas": "las palmas",
    "palmas las": "las palmas",
    "leon": "leon",
    "lleida": "lleida",
    "lerida": "lleida",
    "lugo": "lugo",
    "madrid": "madrid",
    "malaga": "malaga",
    "murcia": "murcia",
    "navarra": "navarra",
    "nafarroa": "navarra",
    "ourense": "ourense",
    "orense": "ourense",
    "palencia": "palencia",
    "pontevedra": "pontevedra",
    "salamanca": "salamanca",
    "segovia": "segovia",
    "sevilla": "sevilla",
    "soria": "soria",
    "tarragona": "tarragona",
    "tenerife": "tenerife",
    "santa cruz de tenerife": "tenerife",
    "teruel": "teruel",
    "toledo": "toledo",
    "valencia": "valencia",
    "valladolid": "valladolid",
    "zamora": "zamora",
    "zaragoza": "zaragoza",
}


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


def _safe_int(texto):
    s = re.sub(r"\D", "", (texto or ""))
    return int(s) if s else None


def _throttle_request(base_delay):
    global _RL_NEXT_TS
    now = time.time()
    with _RL_LOCK:
        ready = max(now, _RL_NEXT_TS, _RL_BLOCK_UNTIL)
        wait = max(0.0, ready - now)
        cadence = max(0.0, float(base_delay or 0.0)) + _RL_PENALTY + random.uniform(0.05, 0.25)
        _RL_NEXT_TS = ready + cadence
    if wait > 0:
        time.sleep(wait)


def _register_success():
    global _RL_PENALTY
    with _RL_LOCK:
        _RL_PENALTY = max(0.0, _RL_PENALTY - 0.12)


def _register_block(http_code=None, retry_after=None):
    global _RL_BLOCK_UNTIL, _RL_PENALTY
    cooldown = 10.0
    if http_code == 429:
        cooldown = 35.0
    elif http_code in (403, 503, 520, 522):
        cooldown = 18.0
    if isinstance(retry_after, (int, float)) and retry_after > 0:
        cooldown = max(cooldown, float(retry_after))
    with _RL_LOCK:
        _RL_PENALTY = min(6.0, _RL_PENALTY + 0.75)
        _RL_BLOCK_UNTIL = max(_RL_BLOCK_UNTIL, time.time() + cooldown + random.uniform(0.4, 2.2))


def _normalizar_provincia(txt):
    p = normalizar(txt or "")
    p = re.sub(r"[()\[\]{}]", " ", p)
    p = p.replace("/", " ").replace("-", " ")
    p = re.sub(r"\s+", " ", p).strip()
    # Casos de orden invertido en la fuente: "Palmas (las)" -> "las palmas"
    if p in ("palmas las", "palmas de gran canaria"):
        p = "las palmas"
    return PROV_ALIAS.get(p, p)


def provincia_coincide(prov_dato, prov_filtro):
    if not prov_filtro:
        return True

    filtro = _normalizar_provincia(prov_filtro)
    dato_raw = normalizar(prov_dato or "")
    if not filtro or not dato_raw:
        return False

    partes = [p.strip() for p in re.split(r"[,;|]", dato_raw) if p.strip()]
    candidatos = {_normalizar_provincia(p) for p in partes}
    candidatos.add(_normalizar_provincia(dato_raw))
    if filtro in candidatos:
        return True

    # Fallback tolerante por tokens
    f_toks = set(filtro.split())
    for c in candidatos:
        c_toks = set(c.split())
        if f_toks and c_toks and (f_toks.issubset(c_toks) or c_toks.issubset(f_toks)):
            return True
    return False


FICHA_BASE = "https://ranking-empresas.eleconomista.es/"


def _dominio(url):
    try:
        return urlparse(url).netloc.replace("www.", "").lower()
    except Exception:
        return ""


def _ddg_extract_url(href):
    if not href:
        return ""
    if "uddg=" in href:
        try:
            q = parse_qs(urlparse(href).query)
            val = q.get("uddg", [""])[0]
            if val:
                return unquote(val)
        except Exception:
            pass
    return href


def _titulo_a_nombre(titulo):
    t = (titulo or "").strip()
    if not t:
        return ""
    # Quitar sufijos típicos de directorios
    for sep in (" | ", " - ", " — "):
        if sep in t:
            t = t.split(sep)[0].strip()
    t = re.sub(r"\s+", " ", t).strip(" -|")
    return t


def _parece_empresa(nombre, snippet, url):
    n = normalizar(nombre)
    s = normalizar(snippet or "")
    dom = _dominio(url)
    path = (urlparse(url).path or "").lower()
    if not n:
        return False
    if dom in FALLBACK_EXCLUDED_HOSTS:
        return False
    # Descartar listados genéricos no-ficha
    if any(x in path for x in ("/provincia/", "/localidad/", "/actividad/", "/buscador", "/directorio")) and \
       "directorio-empresas/" not in path:
        return False
    # Evitar páginas de definición de CNAE
    if n.startswith("cnae ") or "codigo cnae" in n:
        return False
    if any(x in n for x in ("buscador", "consulta del censo", "clasificacion nacional")):
        return False

    # Reglas de URL de ficha empresarial conocidas
    known_profile = (
        dom.endswith("empresite.eleconomista.es") and path.endswith(".html") and not any(x in path for x in ("/provincia/", "/localidad/")),
        dom.endswith("einforma.com") and "/informacion-empresa/" in path,
        dom.endswith("axesor.es") and "/informes-empresas/" in path,
        dom.endswith("empresascif.com") and "/empresa/" in path,
        dom.endswith("bormedirectorio.com") and "/empresa/" in path,
        dom.endswith("expansion.com") and "/directorio-empresas/" in path,
        dom.endswith("infoempresa.com") and ("/empresa/" in path or "/informe-de-empresa/" in path),
    )
    if any(known_profile):
        return True

    marcadores = (
        "sociedad limitada", "s.l", " sl", "s.a", " sa", "cif", "nif",
        "razon social", "empresa", "sl.", "sa.", "sociedad anonima",
    )
    if any(m in s for m in marcadores):
        return True
    if any(m in n for m in ("sociedad limitada", "s.l", " s l ", "s.a", " sa ", " sl", " sa")):
        return True
    return False


def _inferir_provincia(texto, provincia_filtro=None):
    if provincia_filtro:
        return provincia_filtro
    t = normalizar(texto or "")
    if not t:
        return None
    for alias, canon in PROV_ALIAS.items():
        if alias and alias in t:
            # Devolver una forma legible (capitalizada simple).
            return " ".join(w.capitalize() for w in canon.split())
    return None


def _ddg_query(session, query):
    headers = {
        "User-Agent": random.choice(SCRAPE_USER_AGENTS),
        "Accept-Language": "es-ES,es;q=0.9",
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": "https://duckduckgo.com/",
    }
    r = session.post(
        "https://html.duckduckgo.com/html/",
        data={"q": query},
        headers=headers,
        timeout=20
    )
    if r.status_code != 200:
        return []
    soup = BeautifulSoup(r.text, "lxml")
    items = []
    for box in soup.select(".result"):
        a = box.select_one(".result__a") or box.find("a", href=True)
        if not a:
            continue
        title = a.get_text(" ", strip=True)
        href = _ddg_extract_url(a.get("href", ""))
        sn_el = box.select_one(".result__snippet")
        snippet = sn_el.get_text(" ", strip=True) if sn_el else ""
        if href.startswith("//"):
            href = "https:" + href
        items.append({"title": title, "url": href, "snippet": snippet})
    return items


def _bing_query(session, query, first=1, count=20):
    headers = {
        "User-Agent": random.choice(SCRAPE_USER_AGENTS),
        "Accept-Language": "es-ES,es;q=0.9",
        "Referer": "https://www.bing.com/",
    }
    first = max(1, int(first or 1))
    count = max(10, min(50, int(count or 20)))
    url = (
        f"https://www.bing.com/search?q={quote_plus(query)}"
        f"&setlang=es&count={count}&first={first}"
    )
    try:
        r = session.get(url, headers=headers, timeout=20, allow_redirects=True)
    except Exception:
        return []
    if r.status_code != 200:
        return []

    soup = BeautifulSoup(r.text, "lxml")
    items = []
    for box in soup.select("li.b_algo"):
        a = box.select_one("h2 a")
        if not a:
            continue
        title = a.get_text(" ", strip=True)
        href = (a.get("href") or "").strip()
        href = _bing_unwrap_url(href)
        if not href:
            continue
        sn = box.select_one(".b_caption p") or box.select_one("p")
        snippet = sn.get_text(" ", strip=True) if sn else ""
        items.append({"title": title, "url": href, "snippet": snippet})
    return items


def _bing_unwrap_url(href):
    h = (href or "").strip()
    if not h:
        return ""
    if h.startswith("//"):
        h = "https:" + h
    if h.startswith("/"):
        h = "https://www.bing.com" + h

    # Bing tracking redirect -> URL real en parámetro u=a1(base64)
    if "bing.com/ck/" in h and "&u=a1" in h:
        try:
            import base64
            u = h.split("&u=a1", 1)[1].split("&", 1)[0]
            # Normalizar padding base64
            pad = "=" * ((4 - len(u) % 4) % 4)
            dec = base64.b64decode(u + pad).decode("utf-8", errors="ignore")
            if dec.startswith("http"):
                return dec
        except Exception:
            pass
    return h


def _is_empresascif_company_url(url):
    try:
        u = (url or "").strip()
        if not u.startswith("http"):
            return False
        dom = _dominio(u)
        path = (urlparse(u).path or "").lower()
        return dom.endswith("empresascif.com") and "/empresa/" in path
    except Exception:
        return False


def scrape_cnae_fallback_search_empresascif(
    cnae,
    provincia=None,
    paginas=None,
    delay=1.2,
    on_progress=None,
    motivo="",
    max_runtime_override=None,
    max_candidates_override=None,
):
    """
    Fallback rápido por buscador:
    - Encuentra muchas URLs tipo /empresa/ en empresascif para el CNAE
    - Valida CNAE por ficha en paralelo
    """
    exhaustive = (paginas is None) or (int(paginas or 0) <= 0)
    started = time.time()
    if isinstance(max_runtime_override, (int, float)) and float(max_runtime_override) > 0:
        max_runtime = float(max_runtime_override)
    else:
        max_runtime = 140 if exhaustive else 70

    session = requests.Session()
    prov = (provincia or "").strip()
    prov_norm = _normalizar_provincia(prov) if prov else ""

    candidate_urls = []
    internas_usadas = 0
    externas_usadas = 0

    # 1) Buscador interno de empresascif (más estable que buscadores externos cuando hay bloqueos).
    term_slugs = _empresascif_build_search_terms(
        cnae=cnae,
        provincia=(prov if prov else None),
    )
    max_terms = 14 if prov else (34 if exhaustive else 14)
    for ti, term in enumerate(term_slugs[:max_terms], 1):
        if (time.time() - started) > max_runtime:
            break
        if on_progress:
            pct = 24 + int(ti / max(1, min(len(term_slugs), max_terms)) * 20)
            on_progress(min(pct, 58), f"Fallback buscador interno: término {ti}/{min(len(term_slugs), max_terms)}…")
        internas_usadas += 1
        try:
            candidate_urls.extend(_empresascif_query_company_urls(session, term))
        except Exception:
            pass
        time.sleep(max(0.05, delay * 0.08) + random.uniform(0.01, 0.08))

    # 2) Complemento con Bing cuando no hay suficiente muestra.
    queries = []
    if prov:
        queries.extend([
            f"site:empresascif.com/empresa cnae {cnae} {prov}",
            f"site:empresascif.com/empresa \"{cnae}\" {prov}",
            f"site:empresascif.com/empresa \"CNAE\" \"{cnae}\" {prov}",
            f"site:empresascif.com/empresa \"{prov}\" \"{cnae}\"",
        ])
    else:
        provincias_top = [
            "madrid", "barcelona", "valencia", "sevilla", "malaga", "bizkaia",
            "murcia", "zaragoza", "cadiz", "alicante", "asturias", "tarragona",
        ]
        queries.extend([
            f"site:empresascif.com/empresa cnae {cnae}",
            f"site:empresascif.com/empresa \"CNAE\" \"{cnae}\"",
            f"site:empresascif.com/empresa \"{cnae}\" \"{prov or 'espana'}\"",
        ])
        for p in provincias_top:
            queries.append(f"site:empresascif.com/empresa cnae {cnae} {p}")

    queries = list(dict.fromkeys([q.strip() for q in queries if q.strip()]))
    max_queries = 8 if prov else (16 if exhaustive else 9)
    queries = queries[:max_queries]
    min_candidates_before_external = 64 if exhaustive else 18

    if len(candidate_urls) < min_candidates_before_external:
        for qi, q in enumerate(queries, 1):
            if (time.time() - started) > max_runtime:
                break
            if on_progress:
                pct = 58 + int(qi / max(1, len(queries)) * 10)
                on_progress(min(pct, 68), f"Fallback buscador web: consulta {qi}/{len(queries)}…")
            externas_usadas += 1
            try:
                items = _bing_query(session, q, first=1, count=20)
            except Exception:
                items = []
            for it in items:
                u = (it.get("url") or "").strip()
                if _is_empresascif_company_url(u):
                    candidate_urls.append(u)
            time.sleep(max(0.05, delay * 0.1) + random.uniform(0.01, 0.08))

    candidate_urls = list(dict.fromkeys(candidate_urls))
    if not candidate_urls:
        return [], [], "Sin candidatos en buscador para empresascif.", {
            "paginas_reales": 0,
            "agotado": True,
            "fuente": "fallback_search_empresascif",
            "motivo": motivo or "sin_candidatos",
        }

    # Validación por CNAE en paralelo
    if isinstance(max_candidates_override, int) and max_candidates_override > 0:
        max_candidates = max_candidates_override
    else:
        max_candidates = 1600 if exhaustive else 280
    candidate_urls = candidate_urls[:max_candidates]
    workers = 7 if exhaustive else 6
    leads = []
    inspected = 0
    lock = threading.Lock()
    tls = threading.local()

    def _parse(url):
        sess = getattr(tls, "sess", None)
        if sess is None:
            sess = requests.Session()
            tls.sess = sess
        html = _empresascif_get(sess, url, timeout=4)
        return _empresascif_parse_company_page(
            html=html,
            url=url,
            cnae_objetivo=cnae,
            provincia_display=(prov if prov else None),
            allow_missing_cnae=True,
        )

    with ThreadPoolExecutor(max_workers=workers) as ex:
        pending = {}
        url_idx = 0
        stop_early = False
        soft_target = 300 if exhaustive else 30

        while url_idx < len(candidate_urls) and len(pending) < (workers * 4):
            u = candidate_urls[url_idx]
            url_idx += 1
            pending[ex.submit(_parse, u)] = u

        while pending:
            if (time.time() - started) > max_runtime:
                stop_early = True

            done, _ = wait(pending.keys(), timeout=1.0, return_when=FIRST_COMPLETED)
            if not done:
                if stop_early:
                    for fut in list(pending.keys()):
                        fut.cancel()
                    pending.clear()
                continue

            for f in done:
                pending.pop(f, None)
                lead = None
                try:
                    lead = f.result()
                except Exception:
                    lead = None
                with lock:
                    inspected += 1
                    if lead:
                        leads.append(lead)
                    if on_progress and inspected % 30 == 0:
                        pct = 66 + int(inspected / max(1, len(candidate_urls)) * 22)
                        on_progress(min(pct, 89), f"Fallback buscador: validando fichas {inspected}/{len(candidate_urls)}…")
                    if (not exhaustive) and len(leads) >= soft_target and inspected >= min(len(candidate_urls), soft_target * 5):
                        stop_early = True

                if not stop_early and url_idx < len(candidate_urls):
                    u = candidate_urls[url_idx]
                    url_idx += 1
                    pending[ex.submit(_parse, u)] = u

            if stop_early:
                for fut in list(pending.keys()):
                    fut.cancel()
                pending.clear()

    leads = deduplicar(leads)
    for idx, l in enumerate(leads, 1):
        if not l.get("posicion"):
            l["posicion"] = idx

    meta = {
        "paginas_reales": internas_usadas + externas_usadas,
        "agotado": len(leads) < (120 if exhaustive else 12),
        "fuente": "fallback_search_empresascif",
        "motivo": motivo or "buscador",
        "candidatos": len(candidate_urls),
        "fichas_validadas": inspected,
        "consultas_internas": internas_usadas,
        "consultas_externas": externas_usadas,
        "runtime_limited": (time.time() - started) > max_runtime,
    }
    if not leads:
        return [], [], "Sin empresas válidas tras validación de CNAE en buscador.", meta
    return leads, leads, None, meta


def scrape_cnae_fallback_search_empresascif_nacional(cnae, paginas=None, delay=1.1, on_progress=None, motivo=""):
    """
    Barrido nacional por provincias usando el fallback validado por CNAE.
    Diseñado para evitar quedarse en muestras de 30-40 cuando el portal principal bloquea.
    """
    exhaustive = (paginas is None) or (int(paginas or 0) <= 0)
    prioridad = [
        "madrid", "barcelona", "valencia", "sevilla", "malaga", "bizkaia",
        "murcia", "alicante", "zaragoza", "cadiz", "asturias", "tarragona",
        "pontevedra", "girona", "castellon", "granada", "huelva", "valladolid",
        "toledo", "navarra", "las palmas", "tenerife", "almeria", "leon",
    ]

    todas = list(dict.fromkeys(prioridad + list(PROV_TO_EMPRESASCIF_SLUG.keys())))
    if exhaustive:
        provs = todas[:36]
        min_expected = 140
        max_runtime_total = 420
        per_runtime = 13
        per_candidates = 520
        workers = 3
        paginas_prov = None
    else:
        provs = todas[:12]
        min_expected = 50
        max_runtime_total = 160
        per_runtime = 14
        per_candidates = 220
        workers = 2
        paginas_prov = 1
    started = time.time()
    leads_all = []
    pool_all = []
    errors = []
    done_count = 0

    def _task(prov):
        return scrape_cnae_fallback_search_empresascif(
            cnae=cnae,
            provincia=prov,
            paginas=paginas_prov,
            delay=delay,
            on_progress=None,
            motivo=f"nacional_buscador_{prov}",
            max_runtime_override=per_runtime,
            max_candidates_override=per_candidates,
        )

    with ThreadPoolExecutor(max_workers=workers) as ex:
        pending = {ex.submit(_task, p): p for p in provs}

        while pending:
            if (time.time() - started) > max_runtime_total:
                for fut in list(pending.keys()):
                    fut.cancel()
                pending.clear()
                break
            done, _ = wait(pending.keys(), timeout=1.2, return_when=FIRST_COMPLETED)
            if not done:
                continue
            for f in done:
                prov = pending.pop(f, None)
                done_count += 1
                try:
                    leads_p, pool_p, err_p, _ = f.result()
                except Exception as e:
                    leads_p, pool_p, err_p = [], [], str(e)

                if on_progress:
                    pct = 32 + int(done_count / max(1, len(provs)) * 54)
                    on_progress(min(pct, 89), f"Rescate nacional buscador: {done_count}/{len(provs)} provincias…")

                if not err_p and leads_p:
                    leads_all = combinar_leads(leads_all, leads_p)
                    pool_all = combinar_leads(pool_all, (pool_p or leads_p))
                elif err_p and len(errors) < 8:
                    errors.append(f"{prov}: {err_p}")

                if len(leads_all) >= min_expected and done_count >= max(6, len(provs) // (3 if exhaustive else 2)):
                    for fut in list(pending.keys()):
                        fut.cancel()
                    pending.clear()
                    break

    leads_all = deduplicar(leads_all)
    for idx, l in enumerate(leads_all, 1):
        if not l.get("posicion"):
            l["posicion"] = idx

    runtime_limited = (time.time() - started) > max_runtime_total
    meta = {
        "paginas_reales": done_count,
        "agotado": len(leads_all) < min_expected,
        "fuente": "fallback_search_empresascif_nacional",
        "motivo": motivo or "bloqueo_portal_nacional",
        "runtime_limited": runtime_limited,
        "target_estimado": min_expected,
        "provincias_planeadas": len(provs),
    }
    if not leads_all:
        if runtime_limited:
            return [], [], "Tiempo límite alcanzado en buscador nacional por provincias.", meta
        if errors:
            return [], [], f"No se encontraron resultados válidos en buscador nacional. ({errors[0][:120]})", meta
        return [], [], "No se encontraron resultados válidos en buscador nacional.", meta
    return leads_all, (pool_all or leads_all), None, meta


def scrape_cnae_fallback(cnae, provincia=None, paginas=None, delay=1.6, on_progress=None, motivo=""):
    """
    Fallback de emergencia cuando ranking-empresas bloquea la IP.
    Usa resultados HTML de DuckDuckGo para localizar fichas de empresas
    y construir leads básicos (sin ranking/facturación exacta).
    """
    q_base = [f"cnae {cnae}", "sociedad limitada", "empresa"]
    if provincia:
        q_base.append(provincia)

    queries = [
        " ".join(q_base),
        " ".join([f"{cnae}", "empresa", (provincia or "espana"), "cif"]),
        " ".join([f"{cnae}", "informe empresa", (provincia or "espana")]),
        " ".join([f"{cnae}", "actividad", (provincia or "espana"), "sl"]),
        " ".join([f"{cnae}", (provincia or "espana"), "sociedad limitada inmobiliaria"]),
    ]

    exhaustive = (paginas is None) or (int(paginas or 0) <= 0)
    # Más queries en modo exhaustivo o cuando se pedían muchas páginas.
    if exhaustive or int(paginas or 0) >= 6:
        queries.extend([
            " ".join([f"{cnae}", (provincia or "espana"), "razon social cif"]),
            " ".join([f"{cnae}", (provincia or "espana"), "directorio empresas"]),
            " ".join([f"{cnae}", (provincia or "espana"), "borme empresa"]),
            " ".join([f"{cnae}", (provincia or "espana"), "registro mercantil empresa"]),
            " ".join([f"{cnae}", (provincia or "espana"), "datos empresa contacto"]),
        ])

    session = requests.Session()
    leads = []
    pos = 1

    for i, q in enumerate(queries, 1):
        if on_progress:
            pct = 30 + int(i / max(1, len(queries)) * 50)
            on_progress(min(pct, 88), f"Fallback anti-bloqueo: buscando en web ({i}/{len(queries)})…")

        try:
            resultados = _ddg_query(session, q)
        except Exception:
            resultados = []

        # Si DDG trae poco o nada, complementar con Bing (menos bloqueos intermitentes).
        if len(resultados) < 6:
            try:
                resultados += _bing_query(session, q)
            except Exception:
                pass

        for it in resultados:
            try:
                nombre = _titulo_a_nombre(it["title"])
                url = (it["url"] or "").strip()
                snippet = it.get("snippet", "")
                if not url.startswith("http"):
                    continue
                if not _parece_empresa(nombre, snippet, url):
                    continue

                prov = _inferir_provincia(f"{it['title']} {snippet}", provincia_filtro=provincia)
                if provincia and prov and not provincia_coincide(prov, provincia):
                    continue

                leads.append({
                    "nombre": nombre,
                    "cnae": str(cnae),
                    "provincia": prov or (provincia or "España"),
                    "posicion": pos,
                    "evolucion": None,
                    "tendencia": "ND",
                    "facturacion_num": None,
                    "facturacion_raw": "— (fallback web)",
                    "url": url,
                })
                pos += 1
            except Exception:
                continue

        # Pausa suave para no disparar bloqueos en DDG.
        time.sleep(max(0.8, delay) + random.uniform(0.2, 0.7))

    leads = deduplicar(leads)
    # Nota: evitamos recursión sobre este mismo fallback para no entrar en bucles.
    meta = {
        "paginas_reales": 0,
        "agotado": False,
        "fuente": "fallback_ddg",
        "motivo": motivo or "bloqueo_portal",
    }
    if not leads:
        return [], [], (
            "No fue posible obtener resultados del portal principal ni del fallback web. "
            "Inténtalo de nuevo en unos minutos."
        ), meta
    return leads, leads, None, meta


def scrape_cnae_fallback_empresascif_nacional(cnae, paginas=None, delay=1.4, on_progress=None, motivo=""):
    """
    Rescate nacional (cuando provincia está vacía / Toda España).
    Recorre provincias en fases (rápida + profunda) y combina resultados.
    """
    exhaustive = (paginas is None) or (int(paginas or 0) <= 0)
    paginas_ref = None if exhaustive else 1

    prioridad = [
        "madrid", "barcelona", "valencia", "sevilla", "malaga", "bizkaia", "murcia",
        "alicante", "zaragoza", "cadiz", "asturias", "a coruna", "tarragona",
        "pontevedra", "girona", "castellon", "granada", "huelva", "valladolid",
        "toledo", "navarra", "las palmas", "tenerife", "almeria", "leon",
    ]
    todas = list(dict.fromkeys(prioridad + list(PROV_TO_EMPRESASCIF_SLUG.keys())))

    if exhaustive:
        # Balance cobertura/tiempo para no bloquear asignaciones nacionales.
        max_runtime_total = 260
        fase1_n = min(len(todas), 14)
        fase2_n = min(len(todas), 22)
        runtime_fase1 = 8
        runtime_fase2 = 12
        target = 110
    else:
        max_runtime_total = 140
        fase1_n = min(len(todas), 6)
        fase2_n = min(len(todas), 10)
        runtime_fase1 = 8
        runtime_fase2 = 12
        target = 20

    leads_all = []
    pool_all = []
    escaneadas = 0
    intentadas = set()
    errores = []
    started = time.time()
    planned_total = max(fase1_n, fase2_n)

    def _scan_phase(provs, fast_mode, runtime_each, label):
        nonlocal escaneadas, leads_all, pool_all
        for prov in provs:
            if prov in intentadas:
                continue
            if (time.time() - started) > max_runtime_total:
                break
            intentadas.add(prov)
            paso = escaneadas + 1
            if on_progress:
                pct = 30 + int(min(1.0, paso / max(1, planned_total)) * 58)
                on_progress(min(pct, 89), f"{label}: escaneando {prov.title()} ({paso}/{planned_total})…")

            leads_p, pool_p, err_p, _ = scrape_cnae_fallback_empresascif(
                cnae=cnae,
                provincia=prov,
                paginas=paginas_ref,
                delay=max(0.7, delay * (0.78 if fast_mode else 0.92)),
                on_progress=None,
                motivo=f"nacional_empresascif_{label.lower()}",
                fast_mode=fast_mode,
                max_runtime_override=runtime_each,
            )
            escaneadas += 1
            if not err_p and leads_p:
                leads_all = combinar_leads(leads_all, leads_p)
                pool_all = combinar_leads(pool_all, (pool_p or leads_p))
            elif err_p and len(errores) < 8:
                errores.append(str(err_p))

            if len(leads_all) >= target and escaneadas >= max(5, fase1_n // 3):
                return True
        return False

    _scan_phase(todas[:fase1_n], fast_mode=True, runtime_each=runtime_fase1, label="Rescate fase 1")

    if (time.time() - started) < max_runtime_total and (
        (len(leads_all) < int(target * 0.8))
    ):
        _scan_phase(todas[:fase2_n], fast_mode=False, runtime_each=runtime_fase2, label="Rescate fase 2")

    leads_all = deduplicar(leads_all)
    for idx, l in enumerate(leads_all, 1):
        if not l.get("posicion"):
            l["posicion"] = idx

    runtime_limited = (time.time() - started) > max_runtime_total
    meta = {
        "paginas_reales": escaneadas,
        "agotado": len(leads_all) < target,
        "fuente": "fallback_empresascif_nacional",
        "motivo": motivo or "bloqueo_portal_nacional",
        "runtime_limited": runtime_limited,
        "target_estimado": target,
        "provincias_planeadas": planned_total,
    }
    if not leads_all:
        if runtime_limited:
            return [], [], "Tiempo límite alcanzado en rescate nacional sin resultados.", meta
        if errores:
            return [], [], f"No se pudieron obtener resultados en el rescate nacional por provincias. ({errores[0][:120]})", meta
        return [], [], "No se pudieron obtener resultados en el rescate nacional por provincias.", meta
    return leads_all, (pool_all or leads_all), None, meta


def _empresascif_abs(href):
    h = (href or "").strip()
    if not h:
        return ""
    if h.startswith("http"):
        return h
    if h.startswith("//"):
        return "https:" + h
    return "https://www.empresascif.com" + h


def _empresascif_get(session, url, timeout=12):
    headers = {
        "User-Agent": random.choice(SCRAPE_USER_AGENTS),
        "Accept-Language": "es-ES,es;q=0.9",
        "Referer": "https://www.empresascif.com/",
    }
    # Respetar un ritmo global también en fuentes fallback para reducir 429/403.
    _throttle_request(0.12)
    try:
        r = session.get(url, headers=headers, timeout=timeout, allow_redirects=True)
    except Exception:
        return None
    if r.status_code == 200:
        _register_success()
        return r.text
    if r.status_code in (429, 403, 503):
        retry_after = None
        try:
            retry_after = int((r.headers or {}).get("Retry-After", "0") or 0)
        except Exception:
            retry_after = None
        _register_block(r.status_code, retry_after=retry_after)
    if r.status_code != 200:
        return None
    return None


def _empresascif_extract_company_links(html, provincia_slug=None):
    soup = BeautifulSoup(html or "", "lxml")
    out = []
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if "/empresa/" not in href:
            continue
        url = _empresascif_abs(href)
        if not url:
            continue
        p = (urlparse(url).path or "").lower()
        if not re.match(r"^/empresa/[^/]+/?$", p):
            continue
        out.append(url)
    # Quitar duplicados manteniendo orden
    return list(dict.fromkeys(out))


def _empresascif_extract_pagination_links(html, base_url):
    """
    Extrae enlaces de paginación relacionados con la misma vista de empresascif.
    """
    soup = BeautifulSoup(html or "", "lxml")
    parsed_base = urlparse(base_url or "")
    base_netloc = (parsed_base.netloc or "").lower()
    base_path = (parsed_base.path or "").rstrip("/")
    base_parts = [p for p in base_path.split("/") if p]
    # Clave de familia de ruta para no mezclar secciones ajenas.
    family = "/".join(base_parts[:3])

    out = []
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if not href:
            continue
        url = _empresascif_abs(href)
        if not url:
            continue
        pu = urlparse(url)
        if (pu.netloc or "").lower() != base_netloc:
            continue
        ppath = (pu.path or "").rstrip("/")
        pparts = [p for p in ppath.split("/") if p]
        fam2 = "/".join(pparts[:3])
        txt = (a.get_text(" ", strip=True) or "").lower()

        is_page_link = (
            "/pagina-" in ppath
            or "page=" in (pu.query or "").lower()
            or txt in {"siguiente", "anterior"}
            or txt.isdigit()
        )
        if not is_page_link:
            continue
        if family and fam2 and family != fam2:
            continue
        out.append(url)

    return list(dict.fromkeys(out))


def _empresascif_page_is_cnae_listing(url, cnae):
    """
    Heurística: detecta páginas de listado asociadas al CNAE objetivo.
    """
    try:
        code = re.sub(r"\D", "", str(cnae or ""))[-4:].zfill(4)
        p = (urlparse(url or "").path or "").lower()
        if not code:
            return False
        return (("/cnaes/" in p) or ("/actividad/" in p) or ("/actividades/" in p)) and (code in p)
    except Exception:
        return False


def _empresascif_extract_municipio_links(html, provincia_slug):
    soup = BeautifulSoup(html or "", "lxml")
    base = f"/empresas/{provincia_slug}/"
    out = []
    for a in soup.find_all("a", href=True):
        href = (a.get("href", "") or "").strip()
        if not href.startswith(base):
            continue
        # Ignorar root exacto y enlaces raros
        if href == base or "/empresa/" in href or "?" in href or "#" in href:
            continue
        url = _empresascif_abs(href)
        out.append(url)
    return list(dict.fromkeys(out))


def _empresascif_extract_cnae_stats(html):
    """
    Extrae estadísticas CNAE de la provincia desde empresascif.
    Devuelve dict: cnae -> {"count": int|None, "href": str, "desc": str}
    """
    stats = {}
    if not html:
        return stats
    pat = re.compile(
        r'Información CNAE\s*(\d{2,4})"\s+href="([^"]+)"[^>]*>([^<]+)</a>\s*</div>\s*'
        r'<div class="m25"[^>]*>\s*\d{2,4}\s*</div>\s*'
        r'<div class="m25"[^>]*>\s*([0-9\.,]+)\s*Empresas',
        re.I | re.S,
    )
    for m in pat.finditer(html):
        cnae = (m.group(1) or "").strip()
        href = _empresascif_abs(m.group(2) or "")
        desc = (m.group(3) or "").strip()
        raw_n = (m.group(4) or "").replace(".", "").replace(",", "").strip()
        try:
            n = int(raw_n) if raw_n else None
        except Exception:
            n = None
        if not cnae:
            continue
        stats[cnae] = {"count": n, "href": href, "desc": desc}
    return stats


def _empresascif_interleave_edges(links):
    """Diversifica muestras: alterna enlaces del inicio y del final."""
    items = list(links or [])
    out = []
    i, j = 0, len(items) - 1
    while i <= j:
        out.append(items[i])
        i += 1
        if i <= j:
            out.append(items[j])
            j -= 1
    return list(dict.fromkeys(out))


def _empresascif_search_slug(texto):
    """
    Slug para /busqueda/<slug>/ de empresascif.
    """
    t = normalizar(texto or "")
    t = re.sub(r"[^a-z0-9\s\-]", " ", t)
    t = re.sub(r"\s+", "-", t).strip("-")
    return t[:120]


def _empresascif_build_search_terms(cnae, provincia=None):
    """
    Construye términos de búsqueda internos usando CNAE + descripción.
    """
    code = str(cnae or "").strip()
    code4 = re.sub(r"\D", "", code)[-4:].zfill(4) if re.sub(r"\D", "", code) else code
    desc = (_CNAE_CATALOG.get(code4) or _CNAE_CATALOG.get(code) or "").strip()

    terms = [f"cnae {code4}", code4]
    if desc:
        terms.append(desc)

    dn = normalizar(desc)
    if dn:
        dn = re.sub(
            r"\b(comercio|por|al|de|del|la|el|los|las|y|otros|otras|actividad|actividades|"
            r"n c o p|cuenta|propia|especializado|intermediarios|servicios|venta|reparacion|"
            r"fabricacion|mantenimiento|alquiler)\b",
            " ",
            dn,
        )
        toks = [t for t in re.split(r"\s+", dn) if len(t) >= 4]
        seen_t = set()
        toks_u = []
        for t in toks:
            if t not in seen_t:
                seen_t.add(t)
                toks_u.append(t)
        if toks_u:
            terms.extend(toks_u[:5])
        if len(toks_u) >= 2:
            terms.append(" ".join(toks_u[:2]))
        if len(toks_u) >= 3:
            terms.append(" ".join(toks_u[:3]))

        # Sinónimos prácticos cuando es maquinaria/herramienta (caso frecuente 466x).
        if ("maquina" in dn or "maquinaria" in dn) and "herramienta" in dn:
            terms.extend([
                "maquinaria herramienta",
                "maquinas herramienta",
                "herramientas industriales",
                "maquinaria industrial",
                "maquinas cnc",
                "maquinaria cnc",
                "herramienta cnc",
                "herramientas de corte",
                "maquinaria precision",
                "machine tools",
                "suministros industriales",
            ])

    prov = normalizar(provincia or "")
    if prov:
        terms.extend([f"{code4} {prov}", f"{prov} {desc or code4}"])

    out = []
    seen = set()
    for t in terms:
        s = _empresascif_search_slug(t)
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _empresascif_query_company_urls(session, term_slug):
    """
    Consulta /busqueda/<slug>/ de empresascif y extrae fichas de empresa.
    """
    slug = _empresascif_search_slug(term_slug)
    if not slug:
        return []
    url = f"https://www.empresascif.com/busqueda/{slug}/"
    html = _empresascif_get(session, url, timeout=9)
    if not html:
        return []
    return _empresascif_extract_company_links(html)


def _empresascif_parse_facturacion(texto):
    """
    Intenta extraer facturación desde texto libre de empresascif.
    Prioriza 'Importe neto de la cifra de negocio' y alternativas cercanas.
    """
    t = re.sub(r"\s+", " ", texto or "").strip()
    if not t:
        return None, "— (fallback empresascif)"

    def _fmt(n):
        return f"{int(n):,}".replace(",", ".") + " €"

    # Rangos tipo "2-5 M€"
    m_rng = re.search(
        r"(\d+(?:[.,]\d+)?)\s*[-a]\s*(\d+(?:[.,]\d+)?)\s*(m|mm|millones?)\s*(?:€|eur|euros)?",
        t,
        re.I,
    )
    if m_rng:
        lo = float(m_rng.group(1).replace(",", "."))
        hi = float(m_rng.group(2).replace(",", "."))
        avg = int(((lo + hi) / 2.0) * 1_000_000)
        if avg >= 1000:
            return avg, _fmt(avg)

    # Valores con sufijo millones.
    m_mil = re.search(
        r"(?:facturaci[oó]n|ventas|ingresos|cifra\s+de\s+negocio|importe\s+neto\s+de\s+la\s+cifra\s+de\s+negocio)"
        r"[^0-9]{0,24}(\d+(?:[.,]\d+)?)\s*(m|mm|millones?)\s*(?:€|eur|euros)?",
        t,
        re.I,
    )
    if m_mil:
        n = int(float(m_mil.group(1).replace(",", ".")) * 1_000_000)
        if n >= 1000:
            return n, _fmt(n)

    pats = [
        r"importe\s+neto\s+de\s+la\s+cifra\s+de\s+negocio[^0-9]{0,24}([0-9][0-9\.,\s]{3,})",
        r"cifra\s+de\s+negocio[^0-9]{0,24}([0-9][0-9\.,\s]{3,})",
        r"ingresos\s+de\s+explotaci[oó]n[^0-9]{0,24}([0-9][0-9\.,\s]{3,})",
        r"facturaci[oó]n[^0-9]{0,24}([0-9][0-9\.,\s]{3,})",
        r"ventas[^0-9]{0,24}([0-9][0-9\.,\s]{3,})",
    ]
    for pat in pats:
        m = re.search(pat, t, re.I)
        if not m:
            continue
        raw = (m.group(1) or "").strip()
        n = _safe_int(raw)
        if n and n >= 1000:
            return n, _fmt(n)

    # Último recurso: cualquier cifra con símbolo euro suficientemente grande.
    m_eur = re.search(r"([0-9][0-9\.,\s]{4,})\s*(?:€|eur|euros)\b", t, re.I)
    if m_eur:
        n = _safe_int(m_eur.group(1))
        if n and n >= 1000:
            return n, _fmt(n)

    return None, "— (fallback empresascif)"


def _empresascif_parse_gerente(texto):
    t = re.sub(r"\s+", " ", texto or "").strip()
    if not t:
        return None
    pats = [
        r"(?:Administrador(?:a)?(?:\s+[Úu]nico)?|Gerente|Director(?:a)?\s+General|CEO|Presidente(?:a)?|Apoderado)"
        r"[:\s\-]+([A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ]+(?:\s+(?:de\s+|del\s+|la\s+)?[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ]+){1,3})",
    ]
    for pat in pats:
        m = re.search(pat, t, re.I)
        if not m:
            continue
        cand = re.sub(r"\s+", " ", (m.group(1) or "")).strip(" .,:;|-")
        toks = re.findall(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]+", cand)
        if 2 <= len(toks) <= 5 and cand != cand.lower():
            return cand[:180]
    return None


def _empresascif_parse_company_page(
    html,
    url,
    cnae_objetivo,
    provincia_display=None,
    assume_cnae_match=False,
    allow_missing_cnae=False,
):
    if not html:
        return None

    soup = BeautifulSoup(html, "lxml")
    meta_desc = ""
    mtag = soup.find("meta", attrs={"name": "description"})
    if mtag and mtag.get("content"):
        meta_desc = mtag["content"]
    if not meta_desc:
        og = soup.find("meta", attrs={"property": "og:description"})
        if og and og.get("content"):
            meta_desc = og["content"]

    text = " ".join([meta_desc, soup.get_text(" ", strip=True)])
    cnae_obj = re.sub(r"\D", "", str(cnae_objetivo or ""))[-4:].zfill(4)
    cnae_hits = set()

    for pat in (
        r"CNAE(?:\s+(?:de|del|principal|actividad|clase|codigo|c[oó]digo)){0,4}\s*[:\-]?\s*(\d{3,4})",
        r"\bCNAE\b[^0-9]{0,40}(\d{3,4})",
        r"/cnaes/(\d{3,4})_",
        r"\bG(\d{4})\b",
    ):
        for m in re.finditer(pat, (html or "") if "/cnaes/" in pat else text, re.I):
            raw = re.sub(r"\D", "", (m.group(1) or ""))
            if not raw:
                continue
            cnae_hits.add(raw[-4:].zfill(4))

    if assume_cnae_match:
        # Si la ficha viene de un listado CNAE confiable, solo descartamos contradicción explícita.
        if cnae_hits and cnae_obj not in cnae_hits:
            return None
    else:
        if not cnae_hits:
            if not allow_missing_cnae:
                return None
        elif cnae_obj not in cnae_hits:
            return None

    nombre = ""
    h1 = soup.find("h1")
    if h1:
        nombre = h1.get_text(" ", strip=True)
    if not nombre:
        t = soup.title.get_text(" ", strip=True) if soup.title else ""
        nombre = _titulo_a_nombre(t)
    nombre = re.sub(r"\s+", " ", nombre).strip(" -|")
    if not nombre:
        return None

    # Provincia: intentar extraer de texto/meta y validar contra filtro si existe.
    provincia_detectada = None
    m_prov = re.search(r"provincia de\s+([A-Za-zÁÉÍÓÚÑáéíóúñ\-\s]+)", text, re.I)
    if m_prov:
        provincia_detectada = m_prov.group(1).strip()
    else:
        m_tail = re.search(r",\s*([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑa-záéíóúñ\-\s]+)\s*,\s*CNAE\s*:\s*\d{4}", text, re.I)
        if m_tail:
            provincia_detectada = m_tail.group(1).strip()

    if provincia_display and provincia_detectada and not provincia_coincide(provincia_detectada, provincia_display):
        return None
    provincia = provincia_display or provincia_detectada or "España"
    fact_num, fact_raw = _empresascif_parse_facturacion(text)
    gerente = _empresascif_parse_gerente(text)

    return {
        "nombre": nombre,
        "cnae": str(cnae_objetivo),
        "provincia": provincia,
        "posicion": None,
        "evolucion": None,
        "tendencia": "ND",
        "facturacion_num": fact_num,
        "facturacion_raw": fact_raw,
        "gerente": gerente,
        "url": url,
    }


def scrape_cnae_fallback_empresascif(
    cnae,
    provincia=None,
    paginas=None,
    delay=1.5,
    on_progress=None,
    motivo="",
    fast_mode=False,
    max_runtime_override=None,
):
    """
    Fallback principal anti-bloqueo.
    Usa empresascif.com: lista provincial/municipal + validación CNAE por ficha.
    """
    exhaustive = (paginas is None) or (int(paginas or 0) <= 0)
    paginas_req = 0 if exhaustive else max(1, int(paginas or 1))
    started = time.time()
    if isinstance(max_runtime_override, (int, float)) and float(max_runtime_override) > 0:
        max_runtime = float(max_runtime_override)
    elif fast_mode:
        max_runtime = 40
    else:
        max_runtime = 220 if exhaustive else 95

    prov_norm = _normalizar_provincia(provincia) if provincia else ""
    prov_slug = PROV_TO_EMPRESASCIF_SLUG.get(prov_norm) if prov_norm else None
    if not prov_slug:
        return [], [], "No hay mapeo de provincia para fallback empresascif.", {
            "paginas_reales": 0,
            "agotado": False,
            "fuente": "fallback_empresascif",
            "motivo": "provincia_no_mapeada",
        }

    session = requests.Session()
    root_url = f"https://www.empresascif.com/empresas/{prov_slug}/"
    root_html = _empresascif_get(session, root_url, timeout=(8 if fast_mode else 12))
    if not root_html:
        return [], [], "No se pudo cargar la fuente fallback empresascif.", {
            "paginas_reales": 0,
            "agotado": False,
            "fuente": "fallback_empresascif",
            "motivo": "root_no_accesible",
        }

    cnae_stats = _empresascif_extract_cnae_stats(root_html)
    cnae_info = cnae_stats.get(str(cnae), {})
    actividad_count = cnae_info.get("count")

    municipio_links = _empresascif_extract_municipio_links(root_html, prov_slug)
    municipio_orden = _empresascif_interleave_edges(municipio_links)

    # Escaneo más amplio por provincia para evitar falsos 0 leads.
    if exhaustive:
        pages_budget = min(len(municipio_orden), 8) if fast_mode else len(municipio_orden)
    else:
        if fast_mode:
            pages_budget = min(len(municipio_orden), max(4, min(12, paginas_req * 4)))
        else:
            pages_budget = min(
                len(municipio_orden),
                max(18, min(90, paginas_req * 10))
            )
    pages_to_scan = [root_url] + municipio_orden[:max(0, pages_budget)]

    company_urls = []
    trusted_cnae_urls = set()
    extra_scan_urls = []
    extra_scanned = 0
    pages_scanned = 0
    # Semilla específica por CNAE de la provincia (si está disponible en el top de actividades).
    cnae_href = cnae_info.get("href")
    if cnae_href:
        html_cnae = _empresascif_get(session, cnae_href, timeout=(6 if fast_mode else 10))
        if html_cnae:
            pages_scanned += 1
            links_cnae = _empresascif_extract_company_links(html_cnae, prov_slug)
            company_urls.extend(links_cnae)
            trusted_cnae_urls.update(links_cnae)
            cnae_pag_links = _empresascif_extract_pagination_links(html_cnae, cnae_href)
            max_cnae_pag = 36 if (exhaustive and not fast_mode) else (12 if exhaustive else 4)
            extra_scan_urls.extend(cnae_pag_links[:max_cnae_pag])

    for i, purl in enumerate(pages_to_scan, 1):
        if (time.time() - started) > max_runtime:
            break
        if on_progress:
            pct = 28 + int(i / max(1, len(pages_to_scan)) * 22)
            on_progress(min(pct, 82), f"Fallback empresascif: escaneando {i}/{len(pages_to_scan)}…")

        html = root_html if purl == root_url else _empresascif_get(
            session, purl, timeout=(5 if fast_mode else 10)
        )
        pages_scanned += 1
        if html:
            company_urls.extend(_empresascif_extract_company_links(html, prov_slug))
            if exhaustive:
                max_pag_per_seed = 4 if not fast_mode else 2
                extra_scan_urls.extend(
                    _empresascif_extract_pagination_links(html, purl)[:max_pag_per_seed]
                )
        time.sleep(max(0.08, delay * 0.12) + random.uniform(0.01, 0.08))

    extra_scan_urls = list(dict.fromkeys(extra_scan_urls))
    if extra_scan_urls:
        extra_budget = min(len(extra_scan_urls), 220 if (exhaustive and not fast_mode) else 48)
        for j, eurl in enumerate(extra_scan_urls[:extra_budget], 1):
            if (time.time() - started) > max_runtime:
                break
            if on_progress and j % 20 == 1:
                on_progress(44, f"Fallback empresascif: ampliando paginación ({j}/{extra_budget})…")
            html_ex = _empresascif_get(session, eurl, timeout=(5 if fast_mode else 9))
            pages_scanned += 1
            extra_scanned += 1
            if html_ex:
                links_ex = _empresascif_extract_company_links(html_ex, prov_slug)
                company_urls.extend(links_ex)
                if _empresascif_page_is_cnae_listing(eurl, cnae):
                    trusted_cnae_urls.update(links_ex)
            time.sleep(max(0.06, delay * 0.1) + random.uniform(0.01, 0.06))

    seed_urls = []
    # Semillas internas por buscador de empresascif (suele funcionar mejor bajo bloqueo externo).
    try:
        term_slugs = _empresascif_build_search_terms(
            cnae=cnae,
            provincia=(provincia or prov_norm or None),
        )
        max_terms = 10 if fast_mode else (18 if exhaustive else 12)
        for ti, term in enumerate(term_slugs[:max_terms], 1):
            if (time.time() - started) > max_runtime:
                break
            if on_progress and ti <= 5:
                on_progress(46, f"Fallback empresascif: buscando fichas semilla ({ti}/{min(len(term_slugs), max_terms)})…")
            seed_urls.extend(_empresascif_query_company_urls(session, term))
            time.sleep(max(0.04, delay * 0.06) + random.uniform(0.01, 0.06))
    except Exception:
        pass

    # Semillas directas por buscador externo como complemento.
    try:
        q_seed = f"{cnae} {provincia or prov_norm or ''} sociedad limitada empresascif"
        ddg_items = _ddg_query(session, q_seed)
        for it in ddg_items:
            u = (it.get("url") or "").strip()
            if "/empresa/" in u and _dominio(u).endswith("empresascif.com"):
                seed_urls.append(u)
    except Exception:
        pass

    seed_urls = list(dict.fromkeys(seed_urls))
    if seed_urls:
        max_seed = 220 if fast_mode else (540 if exhaustive else 280)
        seed_urls = seed_urls[:max_seed]
        company_urls = seed_urls + company_urls

    company_urls = list(dict.fromkeys(company_urls))
    if not company_urls:
        return [], [], "No se encontraron fichas de empresa en fallback empresascif.", {
            "paginas_reales": pages_scanned,
            "agotado": False,
            "fuente": "fallback_empresascif",
            "motivo": "sin_fichas",
        }

    # Romper sesgos alfabéticos: mantener primero semilla y barajar el resto.
    rnd = random.Random(f"{cnae}-{prov_slug}")
    if seed_urls:
        seed_set = set(seed_urls)
        pref = [u for u in company_urls if u in seed_set]
        rest = [u for u in company_urls if u not in seed_set]
        rnd.shuffle(rest)
        company_urls = pref + rest
    else:
        rnd.shuffle(company_urls)

    target_leads = max(8, min(24, paginas_req * 4)) if not exhaustive else 999999
    if exhaustive:
        max_fichas = min(SCRAPE_EXHAUSTIVE_FALLBACK_MAX_FICHAS, len(company_urls))
        if isinstance(actividad_count, int) and actividad_count > 0:
            max_fichas = min(max_fichas, int(max(850, min(SCRAPE_EXHAUSTIVE_FALLBACK_MAX_FICHAS, actividad_count * 5.5))))
    else:
        max_fichas = min(2200, max(420, paginas_req * 220))
        if isinstance(actividad_count, int) and actividad_count > 0:
            extra_cap = min(2200, max_fichas + int(actividad_count * 0.6))
            hard_by_pages = min(2200, max(650, paginas_req * 280))
            max_fichas = min(extra_cap, hard_by_pages)
    if fast_mode:
        max_fichas = min(max_fichas, 700 if exhaustive else 260)
    max_fichas = min(max_fichas, len(company_urls))

    workers = max(3, min(6, 5 if exhaustive else (2 + paginas_req * 2))) if fast_mode \
        else max(5, min(9, 7 if exhaustive else (2 + paginas_req * 2)))
    leads = []
    inspected = 0
    lock = threading.Lock()
    tls = threading.local()

    def _parse_candidate(url):
        sess = getattr(tls, "sess", None)
        if sess is None:
            sess = requests.Session()
            tls.sess = sess
        html = _empresascif_get(sess, url, timeout=(4 if fast_mode else 7))
        lead = _empresascif_parse_company_page(
            html=html,
            url=url,
            cnae_objetivo=cnae,
            provincia_display=provincia,
            assume_cnae_match=(url in trusted_cnae_urls),
        )
        return lead

    candidate_urls = company_urls[:max_fichas]
    url_idx = 0
    stop_early = False
    with ThreadPoolExecutor(max_workers=workers) as ex:
        pending = {}
        while url_idx < len(candidate_urls) and len(pending) < (workers * 4):
            u = candidate_urls[url_idx]
            url_idx += 1
            pending[ex.submit(_parse_candidate, u)] = u

        while pending:
            if (time.time() - started) > max_runtime:
                stop_early = True
            done, _ = wait(pending.keys(), return_when=FIRST_COMPLETED)
            for f in done:
                pending.pop(f, None)
                lead = None
                try:
                    lead = f.result()
                except Exception:
                    lead = None
                with lock:
                    inspected += 1
                    if lead:
                        leads.append(lead)
                    if on_progress and (inspected % 40 == 0 or inspected == max_fichas):
                        pct = 52 + int(inspected / max(1, max_fichas) * 36)
                        on_progress(
                            min(pct, 89),
                            f"Fallback empresascif: validando CNAE {inspected}/{max_fichas}…",
                        )
                    # Cierre temprano solo fuera de modo exhaustivo.
                    if not exhaustive:
                        enough_target = len(leads) >= target_leads and inspected >= max(220, target_leads * 22)
                        enough_practical = (
                            len(leads) >= max(10, target_leads // 2)
                            and inspected >= int(max_fichas * 0.65)
                        )
                        if enough_target or enough_practical:
                            stop_early = True

                if not stop_early and url_idx < len(candidate_urls):
                    u = candidate_urls[url_idx]
                    url_idx += 1
                    pending[ex.submit(_parse_candidate, u)] = u

            if stop_early:
                for fut in list(pending.keys()):
                    fut.cancel()
                break

    leads = deduplicar(leads)
    for i, l in enumerate(leads, 1):
        l["posicion"] = i

    meta = {
        "paginas_reales": pages_scanned,
        "agotado": False,
        "fuente": "fallback_empresascif",
        "motivo": motivo or "bloqueo_portal",
        "actividad_count": actividad_count,
        "exhaustivo": exhaustive,
        "municipios_escaneados": len(pages_to_scan) - 1,
        "paginas_paginacion": extra_scanned,
        "fichas_validadas": inspected,
        "runtime_limited": (time.time() - started) > max_runtime,
    }
    if not leads:
        if meta.get("runtime_limited"):
            return [], [], "Tiempo límite alcanzado en fallback empresascif sin resultados.", meta
        if isinstance(actividad_count, int) and actividad_count > 0:
            return [], [], (
                f"Fallback empresascif no devolvió empresas válidas para CNAE {cnae} en {provincia}. "
                f"Referencia del portal: ~{actividad_count} empresas en provincia. "
                "Prueba de nuevo en unos minutos."
            ), meta
        return [], [], "Fallback empresascif no devolvió empresas para ese CNAE/provincia.", meta
    return leads, leads, None, meta

def make_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": random.choice(SCRAPE_USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9",
        "Connection": "keep-alive",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Referer": "https://ranking-empresas.eleconomista.es/",
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
    solo = re.sub(r"[^\d]", "", t)
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
    # Rangos típicos en fichas tipo "2-5 M€"
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*[-a]\s*(\d+(?:[.,]\d+)?)\s*m", t_low)
    if m:
        lo = float(m.group(1).replace(",", "."))
        hi = float(m.group(2).replace(",", "."))
        avg = int(((lo + hi) / 2) * 1_000_000)
        return avg, f"{int(lo)}-{int(hi)} M€"
    return None, t or "—"


def fetch_page(session, cnae, pagina, base_delay=1.5):
    def _has_rows(html):
        return bool(re.search(r"<tr[^>]*>.*?<td", html or "", flags=re.I | re.S))

    max_intentos = 3
    for intento in range(max_intentos):
        try:
            if intento > 0:
                time.sleep(min(14, 1.5 * (intento + 1)))
                
            if pagina == 1:
                params = {"qSectorNorm": cnae}
                _throttle_request(base_delay)
                r = session.get(BASE_URL, params=params, timeout=14)
                if r.status_code == 429:
                    # Fallback por AJAX para primera página
                    _throttle_request(base_delay)
                    r = session.post(AJAX_URL, data={
                        'tipoPagina': 'nacional',
                        'qProvNorm': '',
                        'qSectorNorm': str(cnae),
                        'qVentasNorm': '',
                        'qNombreNorm': '',
                        'qPagina': '1'
                    }, timeout=14)
            else:
                data = {
                    'tipoPagina': 'nacional',
                    'qProvNorm': '',
                    'qSectorNorm': str(cnae),
                    'qVentasNorm': '',
                    'qNombreNorm': '',
                    'qPagina': str(pagina)
                }
                _throttle_request(base_delay)
                r = session.post(AJAX_URL, data=data, timeout=14)
                # Fallback: a veces la respuesta AJAX llega vacía/bloqueada
                if r.status_code == 200 and not _has_rows(r.text):
                    params = {"qSectorNorm": cnae, "qPagina": str(pagina)}
                    _throttle_request(base_delay)
                    r = session.get(BASE_URL, params=params, timeout=14)
                
            r.raise_for_status()
            _register_success()
            return BeautifulSoup(r.text, "lxml"), None
        except requests.HTTPError as e:
            code = e.response.status_code
            retry_after = None
            try:
                retry_after = int((e.response.headers or {}).get("Retry-After", "0") or 0)
            except Exception:
                retry_after = None
            _register_block(code, retry_after=retry_after)
            if code in (403, 429, 503, 520, 522) and intento < (max_intentos - 1):
                # Renovar sesión ayuda a evitar fingerprint repetido tras bloqueo
                try:
                    session.close()
                except Exception:
                    pass
                session = make_session()
                time.sleep(min(10, 2.4 * (intento + 1)) + random.uniform(0.2, 0.8))
                continue
            return None, f"HTTP {code}"
        except Exception as e:
            _register_block(None)
            if intento < (max_intentos - 1):
                time.sleep(min(10, 1.8 * (intento + 1)) + random.uniform(0.2, 0.8))
                continue
            return None, str(e)
    return None, f"Sin conexión tras {max_intentos} intentos"


def parse_tabla(soup, provincia_filtro=None):
    """
    Parsea la tabla del ranking. 7 cols: pos|evol|nombre(link)|fact|cnae|prov|btn
    """
    rows = []
    table = None
    for t in soup.find_all("table"):
        headers = " ".join(th.get_text(" ", strip=True).lower() for th in t.find_all("th"))
        if any(k in headers for k in ("empresa", "cnae", "provincia")):
            table = t
            break
    if table is None:
        table = soup.find("table")
    if not table: return rows

    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 6:
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

        # URL ficha: priorizar el enlace de la celda nombre
        url = ""
        for a in tds[2].find_all("a", href=True):
            href = (a.get("href") or "").strip()
            if not href or href.startswith(("javascript:", "#", "mailto:")):
                continue
            url = href if href.startswith("http") else urljoin(FICHA_BASE, href)
            break
        if not url:
            for a in tr.find_all("a", href=True):
                href = (a.get("href") or "").strip()
                if not href or href.startswith(("javascript:", "#", "mailto:")):
                    continue
                url = href if href.startswith("http") else urljoin(FICHA_BASE, href)
                break
        # Si no encontramos URL, construir desde el nombre
        if not url and nombre:
            url = construir_url_ficha(nombre)

        posicion = _safe_int(pos_txt)

        evol_num, tendencia = None, "Igual"
        m = re.search(r"([\d\.]+)", evol_txt)
        if m:
            evol_num = _safe_int(m.group(1))
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
    vistas = {}  # clave (url o nombre_norm) → empresa
    for e in empresas:
        clave = (e.get("url") or "").strip().lower() or normalizar(e["nombre"])
        if clave not in vistas:
            vistas[clave] = e
        else:
            # Quedarse con la de mejor posición (posición numérica menor)
            actual_pos = vistas[clave].get("posicion") or 999999
            nueva_pos  = e.get("posicion") or 999999
            if nueva_pos < actual_pos:
                vistas[clave] = e
    return list(vistas.values())


def combinar_leads(principal, extra):
    """
    Combina dos fuentes de leads priorizando la principal y deduplicando.
    """
    base = list(principal or [])
    add = list(extra or [])
    if not add:
        return deduplicar(base)
    # Mantener prioridad de principal en caso de conflicto de clave.
    merged = base + add
    return deduplicar(merged)


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


def scrape_cnae(cnae, provincia=None, paginas=None, delay=1.5, on_progress=None, prefer_full_portal=False):
    """
    Scraping por CNAE en modo automático.
    - paginas=None o <=0 => modo exhaustivo (recorre todo lo posible).
    - paginas>0 => modo legacy por cantidad de páginas.
    """
    cnae = str(cnae or "").strip()
    if not cnae.isdigit():
        return [], [], "CNAE inválido. Debe ser numérico.", {"paginas_reales": 0, "agotado": False}

    exhaustive = (paginas is None) or (int(paginas or 0) <= 0)
    paginas_legacy = max(1, int(paginas or 1)) if not exhaustive else 0

    delay = max(0.4, float(delay or 0.4))
    provincia_norm = _normalizar_provincia(provincia) if provincia else ""
    provincia_arg = (provincia or "").strip() or None

    if exhaustive:
        paginas_totales = max(30, SCRAPE_EXHAUSTIVE_MAIN_MAX_PAGES)
        objetivo_min_leads_prov = None
    else:
        # Legacy: algo más de radio en provincia para no quedarnos cortos.
        extra_pages = min(12, max(4, paginas_legacy // 2)) if provincia_norm else 0
        paginas_totales = paginas_legacy + extra_pages
        objetivo_min_leads_prov = 12

    session = make_session()
    first_soup = None

    def _fallback_chain(tag):
        # 1) Búsqueda masiva en empresascif vía buscador (rápida y amplia).
        leads_acc, pool_acc = [], []
        err_last = None
        meta_search_nacional = None
        if provincia_arg:
            enough_target = 24 if exhaustive else 12
        else:
            enough_target = 200 if exhaustive else 60

        leads_s, pool_s, err_s, meta_s = scrape_cnae_fallback_search_empresascif(
            cnae=cnae,
            provincia=provincia_arg,
            paginas=(None if exhaustive else paginas_legacy),
            delay=delay,
            on_progress=on_progress,
            motivo=f"{tag}_search_empresascif",
            max_runtime_override=(150 if exhaustive and not provincia_arg else None),
            max_candidates_override=(1400 if exhaustive and not provincia_arg else None),
        )
        if not err_s and leads_s:
            leads_acc = combinar_leads(leads_acc, leads_s)
            pool_acc = combinar_leads(pool_acc, (pool_s or leads_s))
            if len(leads_acc) >= enough_target:
                return leads_acc, (pool_acc or leads_acc), None, meta_s
        else:
            err_last = err_s

        # 1b) Nacional por provincias con buscador validado por CNAE.
        if not provincia_arg:
            leads_sn, pool_sn, err_sn, meta_sn = scrape_cnae_fallback_search_empresascif_nacional(
                cnae=cnae,
                paginas=(None if exhaustive else paginas_legacy),
                delay=delay,
                on_progress=on_progress,
                motivo=f"{tag}_search_empresascif_nacional",
            )
            if not err_sn and leads_sn:
                leads_acc = combinar_leads(leads_acc, leads_sn)
                pool_acc = combinar_leads(pool_acc, (pool_sn or leads_sn))
                meta_search_nacional = meta_sn
                if len(leads_acc) >= enough_target:
                    return leads_acc, (pool_acc or leads_acc), None, meta_sn
            else:
                err_last = err_sn or err_last

        # Si ya hay una base nacional suficientemente amplia, evitar rescate profundo.
        if (not provincia_arg) and exhaustive and len(leads_acc) >= 80:
            return leads_acc, (pool_acc or leads_acc), None, (meta_search_nacional or meta_s)

        # 2) empresascif provincial o nacional por provincias (validación directa).
        if provincia_arg:
            leads_fb, pool_fb, err_fb, meta_fb = scrape_cnae_fallback_empresascif(
                cnae=cnae,
                provincia=provincia_arg,
                paginas=(None if exhaustive else paginas_legacy),
                delay=delay,
                on_progress=on_progress,
                motivo=f"{tag}_empresascif",
            )
        else:
            leads_fb, pool_fb, err_fb, meta_fb = scrape_cnae_fallback_empresascif_nacional(
                cnae=cnae,
                paginas=(None if exhaustive else paginas_legacy),
                delay=delay,
                on_progress=on_progress,
                motivo=f"{tag}_empresascif_nacional",
            )
        if not err_fb and leads_fb:
            leads_acc = combinar_leads(leads_acc, leads_fb)
            pool_acc = combinar_leads(pool_acc, (pool_fb or leads_fb))
            if len(leads_acc) >= enough_target or provincia_arg:
                return leads_acc, (pool_acc or leads_acc), None, meta_fb
        else:
            err_last = err_fb or err_last

        # Si ya tenemos una base suficiente validada por CNAE, evitamos depender del fallback web genérico.
        if leads_acc and (
            (not provincia_arg and len(leads_acc) >= (120 if exhaustive else 35))
            or (provincia_arg and len(leads_acc) >= (16 if exhaustive else 8))
        ):
            return leads_acc, (pool_acc or leads_acc), None, (meta_fb or meta_s)

        # 3) fallback web (DDG + Bing)
        leads_w, pool_w, err_w, meta_w = scrape_cnae_fallback(
            cnae=cnae,
            provincia=provincia_arg,
            paginas=(None if exhaustive else paginas_legacy),
            delay=delay,
            on_progress=on_progress,
            motivo=f"{tag}_ddg_bing",
        )
        if not err_w and leads_w:
            leads_acc = combinar_leads(leads_acc, leads_w)
            pool_acc = combinar_leads(pool_acc, (pool_w or leads_w))
            return leads_acc, (pool_acc or leads_acc), None, meta_w

        if leads_acc:
            return leads_acc, (pool_acc or leads_acc), None, (meta_w or meta_fb or meta_s)
        return [], [], (err_w or err_last or "Sin resultados en fallback."), (meta_w or meta_fb or meta_s)

    try:
        _throttle_request(delay)
        probe = session.get(BASE_URL, params={"qSectorNorm": cnae}, timeout=18)
        if probe.status_code == 429:
            if prefer_full_portal:
                return [], [], "HTTP 429", {"paginas_reales": 0, "agotado": False, "fuente": "portal_principal"}
            return _fallback_chain("precheck_429")
        if probe.status_code == 200:
            first_soup = BeautifulSoup(probe.text, "lxml")
    except Exception:
        pass

    # Descargar páginas nacionales para tener pool de competidores completo.
    todas_nacional = []
    todas_provincia = []
    paginas_vacias = 0
    paginas_con_datos = 0
    errores_consecutivos = 0
    agotado = False
    empty_streak_limit = max(2, SCRAPE_EXHAUSTIVE_MAIN_EMPTY_STREAK if exhaustive else 2)

    for p in range(1, paginas_totales + 1):
        if (not exhaustive) and provincia_norm and p > paginas_legacy and len(todas_provincia) >= objetivo_min_leads_prov:
            break

        if on_progress:
            if exhaustive:
                # Barra estable para escaneos largos: avanza fuerte al inicio y se estabiliza.
                pct = 10 + int(min(1.0, p / 70.0) * 72)
                msg = f"Escaneo exhaustivo CNAE {cnae}: página {p}…"
            elif p <= paginas_legacy:
                pct = int(p / paginas_legacy * 80)
                msg = f"Descargando página {p}/{paginas_legacy}…"
            else:
                tramo = max(1, paginas_totales - paginas_legacy)
                pct = 80 + int((p - paginas_legacy) / tramo * 10)
                msg = f"Ampliando búsqueda ({p}/{paginas_totales}) para provincia…"
            on_progress(min(pct, 90), msg)

        if p == 1 and first_soup is not None:
            soup, err = first_soup, None
        else:
            soup, err = fetch_page(session, cnae, p, base_delay=delay)

        if err:
            if err == "HTTP 429" and not todas_nacional:
                if prefer_full_portal:
                    return [], [], "HTTP 429", {"paginas_reales": paginas_con_datos, "agotado": False, "fuente": "portal_principal"}
                return _fallback_chain("ranking_429")

            if todas_nacional:
                errores_consecutivos += 1
                # En exhaustivo toleramos fallos intermitentes y seguimos a la siguiente página.
                if exhaustive and errores_consecutivos < 4:
                    time.sleep(min(6.0, delay + 0.5))
                    continue
                agotado = p < paginas_totales
                break
            return [], [], err, {"paginas_reales": paginas_con_datos, "agotado": False}

        errores_consecutivos = 0
        rows_nac = parse_tabla(soup, provincia_filtro=None)
        if not rows_nac:
            paginas_vacias += 1
            if paginas_vacias >= empty_streak_limit:
                agotado = True
                break
        else:
            paginas_vacias = 0
            paginas_con_datos += 1
            todas_nacional.extend(rows_nac)
            if provincia:
                todas_provincia.extend(parse_tabla(soup, provincia_filtro=provincia))

        time.sleep(delay)

    meta = {"paginas_reales": paginas_con_datos, "agotado": agotado, "exhaustivo": exhaustive}

    if not todas_nacional:
        return _fallback_chain("sin_datos_portal_principal")

    todas_nacional = deduplicar(todas_nacional)
    if provincia:
        todas_provincia = deduplicar(todas_provincia)

    leads_raw = todas_provincia if provincia else todas_nacional

    if not leads_raw and provincia:
        # Si portal principal no dio empresas de la provincia, intentamos fallback provincial exhaustivo.
        leads_fb, pool_fb, err_fb, meta_fb = scrape_cnae_fallback_empresascif(
            cnae=cnae,
            provincia=provincia,
            paginas=(None if exhaustive else paginas_legacy),
            delay=delay,
            on_progress=on_progress,
            motivo="provincia_vacia_en_portal",
        )
        if not err_fb and leads_fb:
            return leads_fb, pool_fb, None, meta_fb

        leads_ddg, pool_ddg, err_ddg, meta_ddg = scrape_cnae_fallback(
            cnae=cnae,
            provincia=provincia,
            paginas=(None if exhaustive else paginas_legacy),
            delay=delay,
            on_progress=on_progress,
            motivo="provincia_vacia_en_portal_ddg",
        )
        if not err_ddg and leads_ddg:
            return leads_ddg, pool_ddg, None, meta_ddg

        return [], [], (
            f"No hay empresas con CNAE {cnae} en {provincia} en el portal principal "
            f"(páginas con datos: {paginas_con_datos})."
        ), meta

    if on_progress:
        on_progress(90, f"{len(leads_raw)} empresas encontradas. Calculando competidores…")

    pool_competidores = todas_nacional
    return leads_raw, pool_competidores, None, meta
