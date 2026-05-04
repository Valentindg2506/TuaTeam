"""
Enriquecimiento de leads v5 — estrategia probada y funcional.
Fuentes en cascada:
  1. Bing search → snippets + links a la web oficial
  2. Web oficial de la empresa → página de contacto
  3. DuckDuckGo HTML como fallback
  4. Bing para licitaciones

Nota: eleconomista ficha (429), einforma/infoempresa (JS-required),
axesor/infocif (timeout/bloqueo) no son accesibles sin navegador real.
La estrategia más efectiva es Bing → web propia.
"""
import re, time, requests, json
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urljoin, urlparse
import unicodedata

# Rotar User-Agents para evitar bloqueos
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]
_ua_idx = 0

def _next_ua():
    global _ua_idx
    ua = USER_AGENTS[_ua_idx % len(USER_AGENTS)]
    _ua_idx += 1
    return ua

def _session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": _next_ua(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",  # Removed 'br' because requests can't natively decode it, causing garbled text
        "DNT": "1",
        "Connection": "keep-alive",
    })
    return s

def _get(url, timeout=12, retries=2):
    for i in range(retries + 1):
        try:
            s = _session()
            r = s.get(url, timeout=timeout, allow_redirects=True)
            # Accept 404 and 403 because many corporate sites have valid footers on error pages
            if r.status_code in (200, 404, 403):
                return r.text
            if r.status_code in (429, 503, 202) and i < retries:
                time.sleep(4 * (i + 1)); continue
        except requests.Timeout:
            if i < retries: time.sleep(2)
        except Exception:
            if i < retries: time.sleep(2)
    return None


# ── Patrones de extracción ────────────────────────────────────────────────────
RE_TEL   = re.compile(r"(?<!\d)(?:\+34[\s.\-]?)?[6789]\d{2}[\s.\-]?\d{3}[\s.\-]?\d{3}(?!\d)")
RE_EMAIL = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
RE_WEB   = re.compile(r"https?://(?:www\.)?([a-zA-Z0-9\-\.]+\.[a-zA-Z]{2,})")

EXCLUIDOS_DOM = {
    "bing.com", "google.com", "google.es", "duckduckgo.com",
    "eleconomista.es", "ranking-empresas.eleconomista.es",
    "einforma.com", "infoempresa.com", "axesor.es", "infocif.es",
    "boe.es", "borme.net", "linkedin.com", "facebook.com",
    "instagram.com", "twitter.com", "x.com", "youtube.com",
    "wikipedia.org", "paginasamarillas.es", "maps.google.com",
    "amazon.es", "amazon.com", "ebay.es", "mercadolibre.es",
    "apple.com", "apps.apple.com", "play.google.com",
    "tiktok.com", "pinterest.com", "reddit.com",
    "tripadvisor.es", "tripadvisor.com", "yelp.com", "yelp.es",
    "trustpilot.com", "glassdoor.es", "glassdoor.com",
    "github.com", "stackoverflow.com", "medium.com",
    "empresascif.com", "empresia.es", "infocnae.com",
    "cnae.com.es", "camara.es",
}

EXCLUIDOS_EMAIL = {
    "example.com", "sentry.io", "duckduckgo.com", "w3.org",
    "schema.org", "apple.com", "microsoft.com", "google.com",
    "facebook.com", "twitter.com", "instagram.com",
}

def _limpiar_tel(t):
    """Limpia y valida teléfono español. Acepta fijos (8xx,9xx) y móviles (6xx,7xx)."""
    t = re.sub(r"[\s.\-()]", "", str(t))
    if t.startswith("+34"): t = t[3:]
    if t.startswith("0034"): t = t[4:]
    if t.startswith("34") and len(t) == 11: t = t[2:]
    # Valid Spanish phones: 6xx (mobile), 7xx (mobile), 8xx (fijo), 9xx (fijo)
    if len(t) == 9 and t[0] in "6789":
        # Reject known non-company numbers
        if t.startswith("900") or t.startswith("800") or t.startswith("700"):
            return None  # toll-free / premium, not useful as contact
        return t
    return None

def _dominio(url):
    try:
        return urlparse(url).netloc.replace("www.", "").lower()
    except Exception:
        return ""

def _dom_match(dom, patron):
    return dom == patron or dom.endswith("." + patron)

def _es_excluido(url_o_dom):
    dom = _dominio(url_o_dom) if url_o_dom.startswith("http") else url_o_dom.lower()
    return any(_dom_match(dom, exc) for exc in EXCLUIDOS_DOM)

def _email_excluido(email):
    dom = (email or "").split("@")[-1].lower()
    return any(_dom_match(dom, exc) for exc in (EXCLUIDOS_EMAIL | EXCLUIDOS_DOM))

def _primer_tel(texto):
    for m in RE_TEL.finditer(texto):
        t = _limpiar_tel(m.group(0))
        if t: return t
    return None

def _primer_email(texto):
    for m in RE_EMAIL.finditer(texto):
        e = m.group(0).lower()
        if not _email_excluido(e):
            return e
    return None

def _primer_web_externa(soup):
    """Extrae la primera URL que sea una web real (no de directorios/RRSS)."""
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.startswith("http"): continue
        if not _es_excluido(href):
            return href
    return None


def _validar_direccion(d):
    """Valida que una dirección extraída sea realmente una dirección española."""
    if not d or len(d) < 10:
        return None
    dl = d.lower()
    # Reject if contains URL-like text or English
    if any(x in dl for x in ("http", "www.", ".com", ".es", ".org", "faq",
                               "cookie", "privacy", "search", "the ", "for ",
                               "click", "button", "submit", "login", "page")):
        return None
    # Must have a Spanish street prefix or postal code
    has_prefix = bool(re.search(
        r"(?:C(?:alle|/|\.)|Av(?:da|enida)?|Plaza|Pol[íi]gono|Paseo|Carretera|Ronda|Camino)",
        d, re.I))
    has_cp = bool(re.search(r"\b\d{5}\b", d))
    if not has_prefix and not has_cp:
        return None
    return d.strip()[:250]


def _limpiar_gerente(cand):
    """Filtra falsos positivos de 'gerente' que no son nombres de persona."""
    g = re.sub(r"\s+", " ", str(cand or "")).strip(" .,:;|-")
    if not g:
        return None
    gl = g.lower()
    # Basura común de webs/plantillas y operadores de búsqueda.
    if any(x in gl for x in (
        "sitio web", "pagina web", "página web", "website", "home",
        "aviso legal", "politica de privacidad", "política de privacidad",
        "cookies", "contacto", "correo", "email", "telefono", "teléfono",
        " or ", " and ", "site:", "http", "www.", ".com", ".es",
        "search", "query", "result",
    )):
        return None

    tokens = re.findall(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]+", g)
    if len(tokens) < 2 or len(tokens) > 6:
        return None

    stop = {"de", "del", "la", "las", "los", "y"}
    basura = {
        "sitio", "web", "pagina", "página", "contacto", "legal",
        "privacidad", "cookies", "empresa", "inicio", "correo",
        "email", "telefono", "teléfono", "blog", "api", "ventas",
        "sl", "slu", "sa", "sau", "slp", "sociedad", "limitada", "anonima", "anónima",
        "gerente", "administrador", "director", "general", "presidente",
        "ceo", "apoderado", "fundador", "consejero", "delegado",
        "or", "and", "not", "site", "search",
    }
    meaningful = [t for t in tokens if t.lower() not in stop]
    if len(meaningful) < 2:
        return None
    if any(t.lower() in basura for t in meaningful):
        return None

    # Si viene todo en minúsculas, normalmente es ruido del texto.
    if g == g.lower():
        return None
    # Must have at least one uppercase letter starting a word (real name pattern)
    if not any(t[0].isupper() for t in meaningful):
        return None
    return g[:180]


def _gerente_desde_jsonld(soup):
    """
    Intenta extraer una persona de bloques JSON-LD.
    """
    def walk(node):
        if isinstance(node, dict):
            yield node
            for v in node.values():
                yield from walk(v)
        elif isinstance(node, list):
            for x in node:
                yield from walk(x)

    for sc in soup.find_all("script", attrs={"type": re.compile(r"ld\+json", re.I)}):
        raw = (sc.string or sc.get_text() or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue

        for node in walk(data):
            if not isinstance(node, dict):
                continue
            ntype = str(node.get("@type", "")).lower()
            name = (node.get("name") or "").strip()
            if "person" in ntype and name:
                cand = _limpiar_gerente(name)
                if cand:
                    return cand
            for k in ("founder", "employee", "employees", "member", "director", "ceo", "owner"):
                v = node.get(k)
                if isinstance(v, dict):
                    cand = _limpiar_gerente(v.get("name"))
                    if cand:
                        return cand
                elif isinstance(v, list):
                    for it in v:
                        if isinstance(it, dict):
                            cand = _limpiar_gerente(it.get("name"))
                            if cand:
                                return cand
                elif isinstance(v, str):
                    cand = _limpiar_gerente(v)
                    if cand:
                        return cand
    return None


# ── Helpers para validar web contra nombre empresa ─────────────────────────────
def _nombre_tokens(nombre):
    """Extrae tokens significativos del nombre de empresa para matching."""
    import unicodedata
    txt = unicodedata.normalize("NFKD", nombre)
    txt = "".join(c for c in txt if not unicodedata.combining(c)).lower()
    for suf in [" s.a.u.", " s.a.", " s.l.u.", " s.l.", " sau", " slu",
                " sa", " sl", " slp", " s.a", " s.l", " s.l.p"]:
        if txt.endswith(suf): txt = txt[:-len(suf)]
    toks = set(re.findall(r"[a-z0-9]{3,}", txt))
    toks -= {"sociedad", "limitada", "anonima", "empresa", "grupo", "group",
             "holding", "iberia", "espana", "spain", "the", "and", "del",
             "los", "las"}
    return toks

def _url_parece_oficial(url, nombre):
    """Verifica si una URL parece ser la web oficial de la empresa."""
    if not url or not url.startswith("http"):
        return False
    if _es_excluido(url):
        return False
    dom = _dominio(url)
    if not dom:
        return False
    # Extraer la parte principal del dominio (sin TLD)
    dom_parts = dom.split(".")
    dom_base = dom_parts[0] if dom_parts else ""
    # Tokens del nombre
    toks = _nombre_tokens(nombre)
    if not toks:
        return True  # Sin tokens para comparar, aceptar
    # Match si algún token del nombre aparece en el dominio
    for tok in toks:
        if len(tok) >= 3 and tok in dom_base:
            return True
    # Match inverso: dominio base está en el nombre
    if len(dom_base) >= 4 and dom_base in nombre.lower():
        return True
    return False


# ── 1. Bing Search ────────────────────────────────────────────────────────────
def enrich_from_bing(nombre, provincia=""):
    """
    Busca en Bing y extrae datos de los snippets de resultados.
    Estrategia mejorada: búsqueda principal + contacto + gerente.
    """
    data = {}

    def _bing_query(q):
        url = f"https://www.bing.com/search?q={quote_plus(q)}&setlang=es&count=15"
        return _get(url, timeout=10)

    def _bing_unwrap(href):
        """Decodifica URLs envueltas por tracking de Bing."""
        if not href:
            return ""
        if "bing.com/ck" in href and "&u=a1" in href:
            try:
                import base64
                b64 = href.split("&u=a1")[1].split("&")[0]
                pad = "=" * ((4 - len(b64) % 4) % 4)
                dec = base64.b64decode(b64 + pad).decode("utf-8", errors="ignore")
                if dec.startswith("http"):
                    return dec
            except Exception:
                pass
        return href

    # Paso 1: Buscar web oficial + contacto
    queries_web = [
        f'"{nombre}" {provincia} web oficial',
        f'"{nombre}" {provincia} contacto telefono',
    ]
    for qi, q in enumerate(queries_web):
        html = _bing_query(q)
        if not html:
            continue
        soup = BeautifulSoup(html, "lxml")
        texto = soup.get_text(" ", strip=True)

        # Teléfono en snippets
        if not data.get("telefono"):
            data["telefono"] = _primer_tel(texto)

        # Email en snippets
        if not data.get("email"):
            data["email"] = _primer_email(texto)

        # Web: buscar en resultados de Bing, validando contra nombre
        if not data.get("web"):
            for a in soup.select("li.b_algo h2 a"):
                href = _bing_unwrap(a.get("href", ""))
                if href.startswith("http") and _url_parece_oficial(href, nombre):
                    data["web"] = href
                    break
            # Fallback: cite elements
            if not data.get("web"):
                for cite_el in soup.select("li.b_algo cite"):
                    txt = cite_el.get_text(strip=True)
                    txt = re.sub(r'\s*›\s*', '/', txt)
                    if not txt.startswith("http"):
                        txt = "https://" + txt.split("/")[0]
                    if _url_parece_oficial(txt, nombre):
                        data["web"] = txt
                        break

        # Dirección en snippets (buscar patrones de calle + CP)
        if not data.get("direccion"):
            m = re.search(
                r"(?:C(?:alle|/|\.)\s*|Av(?:da|enida)?\.?\s+|Plaza\s+|"
                r"Pol[íi]gono\s+(?:Industrial\s+)?|Paseo\s+|Carretera\s+|Ronda\s+)"
                r"[A-ZÁÉÍÓÚÑa-záéíóúñ0-9\s,ºª\.nº]{5,80}"
                r"(?:,\s*\d{5}[^0-9])?",
                texto, re.I)
            if m:
                d = m.group(0).strip().rstrip(",. ")
                if len(d) > 10:
                    data["direccion"] = d[:250]

        # Knowledge Panel de Bing
        kp = soup.select_one(".b_entityTP, .b_rich, [data-tag='LocalBusiness']")
        if kp:
            kp_text = kp.get_text(" ", strip=True)
            if not data.get("telefono"):
                data["telefono"] = _primer_tel(kp_text)
            if not data.get("direccion"):
                m = re.search(
                    r"(?:C(?:alle|/)\s*|Av(?:da|enida)?\.?\s+|Plaza\s+|"
                    r"Pol[íi]gono\s+|Paseo\s+|Carretera\s+)"
                    r"[^,\n\r]{5,80}(?:,\s*\d{5})?",
                    kp_text, re.I)
                if m:
                    data["direccion"] = m.group(0).strip()[:250]

        # Si ya tenemos web+tel+email, no seguir con más queries
        if data.get("web") and data.get("telefono") and data.get("email"):
            break
        if qi < len(queries_web) - 1:
            time.sleep(1.5)

    time.sleep(1.0)

    # Paso 2: Buscar gerente/administrador
    if not data.get("gerente"):
        html2 = _bing_query(
            f'"{nombre}" administrador OR gerente OR "director general" OR CEO OR apoderado'
        )
        if html2:
            texto2 = BeautifulSoup(html2, "lxml").get_text(" ", strip=True)
            pats_gerente = [
                r"(?:Administrador[a]?(?:\s+[Úu]nico)?|Gerente|Director[a]?\s+General"
                r"|CEO|Presidente[a]?|Socio\s+Director|Apoderado|Fundador[a]?|Consejero\s+Delegado)"
                r"[:\s\-]+([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑa-záéíóúñ]+(?:\s+"
                r"(?:de\s+(?:la\s+|los\s+|las\s+|el\s+)?)?"
                r"[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑa-záéíóúñ]+){1,4})",
                # Pattern for "Nombre Apellido, Administrador"
                r"([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){1,3})"
                r",?\s+(?:es\s+)?(?:administrador|gerente|director|CEO|presidente)",
            ]
            for pat in pats_gerente:
                m = re.search(pat, texto2, re.I)
                if m:
                    cand = _limpiar_gerente(m.group(1))
                    if cand:
                        data["gerente"] = cand
                        break

    return data


# ── 2. Web oficial de la empresa (Deep Crawl) ─────────────────────────────────
def enrich_from_web_propia(web_url, nombre=""):
    """
    Raspa la web oficial y páginas internas clave (legal, contacto, about,
    equipo, quienes-somos) para buscar agresivamente datos de contacto.
    """
    data = {}
    if not web_url: return data

    base_dominio = _dominio(web_url)
    
    # Expresiones regulares mejoradas
    re_tel = re.compile(r"(?i)(?:tel[é]?[f]?[.:\s]*)?(?:\+34\s*)?([6789](?:[\s.-]*\d){8})")
    re_email = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
    re_dir = re.compile(r"(?i)(?:C/|Cl\.|Calle|Avda?\.|Avenida|Pol\.?\s*Ind\.?|Pol[íi]gono\s+(?:Industrial\s+)?|Paseo|Plaza|Ronda|Camino|Carretera|Sita en|Domiciliada en|Domicilio)[^|:<\n\r]{5,100}?(?:\b\d{5}\b)[^|:<\n\r]{0,50}")
    re_gerente = re.compile(r"(?i)(?:Administrador[a]?(?:\s+[Úu]nico)?|Gerente|Director[a]?\s+General|CEO|Presidente[a]?|Fundador[a]?|Socio\s+Director|Consejero\s+Delegado)[\s.:]+([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑa-záéíóúñ]+(?:\s+(?:de\s+(?:la\s+|los\s+)?)?[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑa-záéíóúñ]+){1,3})")

    # 1. Obtener la página principal
    html_home = _get(web_url, timeout=8)
    if not html_home: return data
    soup_home = BeautifulSoup(html_home, "lxml")
    
    # 2. Extraer enlaces internos interesantes (ampliado con equipo/team)
    # Palabras clave para páginas internas valiosas
    page_keywords = [
        "contacto", "contact", "about", "nosotros", "quienes-somos",
        "quien-somos", "equipo", "team", "legal", "aviso", "privacidad",
        "empresa", "compania", "company", "sobre", "datos",
        "impressum", "imprint",  # Empresas con web bilingüe
    ]
    links_to_check = [web_url]  # Home first (ordered list)
    seen_links = {web_url}
    for a in soup_home.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith("javascript:") or href.startswith("mailto:") or href.startswith("tel:"):
            continue
        txt = a.get_text().lower()
        href_low = href.lower()
        if any(x in href_low or x in txt for x in page_keywords):
            full_url = href if href.startswith("http") else urljoin(web_url, href)
            if _dominio(full_url) == base_dominio and full_url not in seen_links:
                seen_links.add(full_url)
                # Prioritize contacto/contact pages
                if "contact" in href_low or "contacto" in href_low:
                    links_to_check.insert(1, full_url)  # Right after home
                else:
                    links_to_check.append(full_url)
                
    # Limitar a máximo 7 páginas para cobertura amplia sin demorar
    links_to_check = links_to_check[:7]

    for link in links_to_check:
        html = _get(link, timeout=10)
        if not html: continue
        soup = BeautifulSoup(html, "lxml")
        texto = soup.get_text(" ", strip=True)

        if not data.get("gerente"):
            cand_jsonld = _gerente_desde_jsonld(soup)
            if cand_jsonld:
                data["gerente"] = cand_jsonld

        # -- Extracción de Teléfono --
        if not data.get("telefono"):
            for a in soup.find_all("a", href=re.compile(r"^tel:")):
                t = _limpiar_tel(a["href"].replace("tel:", "").strip())
                if t: data["telefono"] = t; break
        if not data.get("telefono"):
            tels = [re.sub(r"[\s.-]", "", m) for m in re_tel.findall(texto)]
            for t in tels:
                if len(t) == 9 and t[0] in "6789":
                    data["telefono"] = t; break

        # -- Extracción de Email --
        if not data.get("email"):
            # Priority 1: mailto links from company domain
            for a in soup.find_all("a", href=re.compile(r"^mailto:")):
                e = a["href"].replace("mailto:", "").split("?")[0].strip().lower()
                if "@" in e and base_dominio in e:
                    data["email"] = e; break
        if not data.get("email"):
            # Priority 2: any mailto link not excluded
            for a in soup.find_all("a", href=re.compile(r"^mailto:")):
                e = a["href"].replace("mailto:", "").split("?")[0].strip().lower()
                if "@" in e and not _email_excluido(e):
                    data["email"] = e; break
        if not data.get("email"):
            # Priority 3: emails in text, prefer company domain
            emails = re_email.findall(texto)
            domain_emails = [e.lower() for e in emails if base_dominio in e.lower() and not _email_excluido(e)]
            other_emails = [e.lower() for e in emails if base_dominio not in e.lower() and not _email_excluido(e)]
            if domain_emails:
                data["email"] = domain_emails[0]
            elif other_emails:
                data["email"] = other_emails[0]

        # -- Extracción de Dirección --
        if not data.get("direccion"):
            m = re_dir.search(texto)
            if m:
                # Limpiar texto de la dirección
                d = m.group(0).strip().replace("Sita en", "").replace("Domiciliada en", "").replace("Domicilio", "").strip(" :.,")
                if len(d) > 8: data["direccion"] = d[:250]

        # -- Extracción de Gerente --
        if not data.get("gerente"):
            m = re_gerente.search(texto)
            if m:
                cand = _limpiar_gerente(m.group(1))
                if cand:
                    data["gerente"] = cand

        # Si ya tenemos todo, parar
        if all(data.get(k) for k in ("telefono", "email", "direccion", "gerente")):
            break
        
        time.sleep(0.5)

    return data


# ── 2b. Empresascif.com para datos registrales (gerente, CIF, dirección) ──────
def enrich_from_empresascif(nombre, provincia=""):
    """
    Busca la empresa en empresascif.com para obtener datos registrales:
    administrador/gerente, CIF, domicilio social y teléfono.
    Muy útil para gerente que es difícil de obtener de otras fuentes.
    """
    data = {}
    try:
        # Usar Bing para encontrar la ficha en empresascif.com
        q = quote_plus(f'"{nombre}" {provincia} site:empresascif.com')
        url_search = f"https://www.bing.com/search?q={q}&setlang=es&count=5"
        html = _get(url_search, timeout=8)
        if not html:
            return data

        soup = BeautifulSoup(html, "lxml")
        best_link = None
        for a in soup.select("li.b_algo h2 a"):
            href = a.get("href", "")
            if "bing.com/ck" in href and "&u=a1" in href:
                try:
                    import base64
                    b64 = href.split("&u=a1")[1].split("&")[0]
                    pad = "=" * ((4 - len(b64) % 4) % 4)
                    href = base64.b64decode(b64 + pad).decode("utf-8", errors="ignore")
                except Exception:
                    pass
            if href.startswith("http") and "empresascif.com/empresa/" in href:
                best_link = href
                break
        
        if not best_link:
            return data

        time.sleep(0.5)
        html2 = _get(best_link, timeout=8)
        if not html2:
            return data

        soup2 = BeautifulSoup(html2, "lxml")
        text = soup2.get_text(" ", strip=True)

        # Extraer administrador/gerente
        if not data.get("gerente"):
            # Empresascif suele mostrar "Administrador: Nombre Apellido"
            pats = [
                r"Administrador[a]?(?:\s+[Úu]nico)?[:\s]+([A-ZÁÉÍÓÚÑ][a-záéíóúñA-ZÁÉÍÓÚÑ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñA-ZÁÉÍÓÚÑ]+){1,4})",
                r"(?:Gerente|Director[a]?\s+General|Apoderado|Consejero\s+Delegado)[:\s]+([A-ZÁÉÍÓÚÑ][a-záéíóúñA-ZÁÉÍÓÚÑ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñA-ZÁÉÍÓÚÑ]+){1,4})",
            ]
            for pat in pats:
                m = re.search(pat, text)
                if m:
                    cand = _limpiar_gerente(m.group(1))
                    if cand:
                        data["gerente"] = cand
                        break

        # Extraer dirección (domicilio social)
        if not data.get("direccion"):
            m = re.search(
                r"(?:Domicilio\s+(?:Social|social)|Dirección)[:\s]+"
                r"([A-ZÁÉÍÓÚÑ][^\n\r<]{10,120}?\d{5}[^\n\r<]{0,40})",
                text, re.I)
            if m:
                d = m.group(1).strip().rstrip(",. ")
                validated = _validar_direccion(d)
                if validated:
                    data["direccion"] = validated

        # Extraer teléfono
        if not data.get("telefono"):
            data["telefono"] = _primer_tel(text)

    except Exception as e:
        print(f"[empresascif_enrich] {nombre}: {e}")

    return data


# ── 3. Bing search para encontrar la web oficial ──────────────────────────────
def encontrar_web_oficial(nombre, provincia=""):
    """Usa Bing para encontrar la URL de la web oficial, validando contra nombre."""
    try:
        q = quote_plus(f'"{nombre}" {provincia} -site:linkedin.com -site:facebook.com')
        html = _get(f"https://www.bing.com/search?q={q}&setlang=es&count=8", timeout=8)
        if not html: return None
        soup = BeautifulSoup(html, "lxml")
        # Priorizar URLs que coincidan con el nombre
        for a in soup.select("li.b_algo h2 a"):
            href = a.get("href", "")
            if href.startswith("http") and _url_parece_oficial(href, nombre):
                return href
        # Fallback: primer resultado no excluido
        for a in soup.select("li.b_algo h2 a"):
            href = a.get("href", "")
            if href.startswith("http") and not _es_excluido(href):
                return href
    except Exception as e:
        print(f"[encontrar_web] {nombre}: {e}")
    return None


# ── 4. Licitaciones via Bing ──────────────────────────────────────────────────
def check_licita(nombre):
    try:
        q = quote_plus(
            f'"{nombre}" '
            f'(licitación OR adjudicación OR adjudicatario OR PLACSP OR "sector público")'
        )
        html = _get(f"https://www.bing.com/search?q={q}&setlang=es&count=5", timeout=8)
        if not html: return "?"
        html_low = html.lower()
        nombre_low = nombre.lower()[:25]
        indicadores = ["contrataciondelestado", "placsp", "adjudicatario",
                       "adjudicacion", "licitacion", "boe.es"]
        hits = sum(1 for t in indicadores if t in html_low)
        if hits >= 2: return "sí"
        if hits >= 1 and nombre_low in html_low: return "sí"
        return "no"
    except Exception:
        return "?"


# ── Domain Finder (Clearbit API + Heurística) ─────────────────────────────────
def _slugificar(nombre):
    """Convierte nombre de empresa a slug DNS-friendly."""
    txt = unicodedata.normalize("NFKD", nombre)
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    txt = txt.lower()
    for sufijo in [" s.a.u.", " s.a.", " s.l.u.", " s.l.", " sau", " slu",
                   " sa", " sl", " slp", " s.a", " s.l", " s.l.p"]:
        if txt.endswith(sufijo):
            txt = txt[:-len(sufijo)]
    for palabra in [" grupo", " group", " holding", " iberia", " españa", " spain"]:
        txt = txt.replace(palabra, "")
    txt = re.sub(r"[^a-z0-9\s\-]", "", txt)
    txt = re.sub(r"\s+", "-", txt.strip()).strip("-")
    return txt

def encontrar_web_clearbit(nombre):
    """
    Utiliza la API abierta de Clearbit Autocomplete para encontrar el dominio
    oficial de la empresa probando varias variaciones del nombre.
    """
    intentos = [nombre]
    # Nombre sin sufijos legales
    limpio = re.sub(r'(?i)\s+(S\.?A\.?U?|S\.?L\.?U?|S\.?L\.?P|GROUP|GRUPO|SA|SL)$', '', nombre).strip()
    if limpio != nombre: intentos.append(limpio)
    
    # Solo la primera palabra (muy útil para nombres largos como "FERROTALL MAQUINAS-HERRAMIENTA SL")
    p1 = limpio.split()[0].split('-')[0]
    if len(p1) > 4 and p1 != limpio: intentos.append(p1)

    base_tokens = set(re.findall(r"[a-z0-9]+", _slugificar(nombre)))
    base_tokens = {t for t in base_tokens if len(t) > 2}

    for query in intentos:
        try:
            url = f"https://autocomplete.clearbit.com/v1/companies/suggest?query={quote_plus(query)}"
            r = _session().get(url, timeout=4)
            if r.status_code == 200:
                data = r.json()
                if not data:
                    continue
                for item in data[:6]:
                    domain = (item.get("domain") or "").strip().lower()
                    if not domain or _es_excluido(domain):
                        continue
                    item_name = (item.get("name") or "").lower()
                    item_tokens = set(re.findall(r"[a-z0-9]+", item_name))
                    item_tokens -= {"sociedad", "limitada", "anonima", "the", "and"}
                    if not base_tokens or not item_tokens:
                        continue  # Skip if we can't validate
                    common = len(base_tokens & item_tokens)
                    ratio = common / max(1, len(base_tokens))
                    # Also check if domain contains key part of company name
                    dom_base = domain.split(".")[0]
                    name_in_domain = any(len(t) >= 4 and t in dom_base for t in base_tokens)
                    if ratio >= 0.5 or name_in_domain:
                        return f"https://www.{domain}"
        except Exception:
            pass
    return None

def enrich_from_domain_guess(nombre, deep_crawl=True):
    """
    Encuentra el dominio exacto vía Clearbit y opcionalmente lo raspa.
    """
    data = {}
    
    # 1. Intentar Clearbit
    web_url = encontrar_web_clearbit(nombre)
    
    # 2. Si falla, usar heurística de slug
    if not web_url:
        slug = _slugificar(nombre)
        if slug and len(slug) >= 3:
            for tld in [".es", ".com"]:
                url = f"https://www.{slug}{tld}"
                try:
                    r = _session().get(url, timeout=3, allow_redirects=True)
                    if r.status_code == 200:
                        final_url = r.url
                        # Validate that the resolved URL is still relevant
                        if not _es_excluido(final_url):
                            web_url = final_url
                            break
                except Exception:
                    pass

    if web_url:
        data["web"] = web_url
        if deep_crawl:
            merge_web = enrich_from_web_propia(web_url, nombre)
            for k in ("telefono", "email", "direccion", "gerente"):
                if merge_web.get(k):
                    data[k] = merge_web[k]
                
    return data


def enrich_from_google_places(nombre, provincia):
    import os
    api_key = os.environ.get("GOOGLE_PLACES_API_KEY")
    if not api_key: return {}
    
    data = {}
    try:
        # 1. Búsqueda de texto para obtener el Place ID
        query = f"{nombre} {provincia} España"
        url_search = f"https://maps.googleapis.com/maps/api/place/textsearch/json?query={quote_plus(query)}&key={api_key}"
        r1 = _session().get(url_search, timeout=8)
        if r1.status_code == 200:
            res1 = r1.json()
            if res1.get("results"):
                place_id = res1["results"][0]["place_id"]
                # 2. Detalles del lugar para teléfono, web y dirección
                url_details = f"https://maps.googleapis.com/maps/api/place/details/json?place_id={place_id}&fields=formatted_phone_number,website,formatted_address&key={api_key}"
                r2 = _session().get(url_details, timeout=8)
                if r2.status_code == 200:
                    res2 = r2.json()
                    if res2.get("result"):
                        det = res2["result"]
                        if det.get("formatted_phone_number"):
                            t = _limpiar_tel(det["formatted_phone_number"])
                            if t: data["telefono"] = t
                        if det.get("website"):
                            data["web"] = det["website"]
                        if det.get("formatted_address"):
                            data["direccion"] = det["formatted_address"]
    except Exception as e:
        print(f"[google_places] Error: {e}")
    return data

def enrich_from_social_and_directories(nombre, provincia):
    """
    Usa Bing para buscar en directorios empresariales y redes sociales.
    Extrae teléfono, email y dirección de los snippets sin visitar la página.
    """
    data = {}
    queries = [
        f'"{nombre}" {provincia} telefono email',
        f'"{nombre}" {provincia} contacto direccion CIF',
    ]
    for q_raw in queries:
        q = quote_plus(q_raw)
        url = f"https://www.bing.com/search?q={q}&setlang=es&count=15"
        html = _get(url, timeout=10)
        if html:
            soup = BeautifulSoup(html, "lxml")
            texto = soup.get_text(" ", strip=True)
            if not data.get("telefono"):
                data["telefono"] = _primer_tel(texto)
            if not data.get("email"):
                data["email"] = _primer_email(texto)
            if not data.get("direccion"):
                m = re.search(
                    r"(?:C(?:alle|/|\.)\s*|Av(?:da|enida)?\.?\s+|Plaza\s+|"
                    r"Pol[íi]gono\s+(?:Industrial\s+)?|Paseo\s+|Carretera\s+)"
                    r"[A-ZÁÉÍÓÚÑa-záéíóúñ0-9\s,ºª\.nº]{5,80}"
                    r"(?:,\s*\d{5})?",
                    texto, re.I)
                if m:
                    d = m.group(0).strip().rstrip(",. ")
                    if len(d) > 10:
                        data["direccion"] = d[:250]
        if data.get("telefono") and data.get("email"):
            break
        time.sleep(1.0)
    return data

# ── Función principal ─────────────────────────────────────────────────────────
def enrich_lead(lead_dict):
    """
    Enriquece un lead en cascada agresiva:
      1. Domain guessing → web oficial directa
      2. Bing search (siempre, para complementar)
      3. Web oficial deep crawl
      4. Directorios y redes sociales
      5. Google Places API (último recurso)
      6. Licitaciones
    """
    resultado = {"telefono": None, "email": None, "web": None,
                 "direccion": None, "gerente": None, "licita": "?"}

    nombre    = lead_dict.get("nombre", "")
    provincia = lead_dict.get("provincia", "")

    def merge(fuente):
        for k in ("telefono", "email", "web", "direccion", "gerente"):
            if not resultado[k] and fuente.get(k):
                # Validate addresses before saving
                if k == "direccion":
                    validated = _validar_direccion(fuente[k])
                    if validated:
                        resultado[k] = validated
                else:
                    resultado[k] = fuente[k]

    def faltan_datos():
        """Retorna True si falta teléfono, email o dirección."""
        return not resultado["telefono"] or not resultado["email"] or not resultado["direccion"]

    # 1. Domain guessing (funciona aunque Bing/Google bloqueen)
    try:
        merge(enrich_from_domain_guess(nombre))
        time.sleep(0.8)
    except Exception as e:
        print(f"[domain_guess] {nombre}: {e}")

    # 2. Bing search - SIEMPRE ejecutar para complementar datos faltantes
    if faltan_datos() or not resultado.get("gerente"):
        try:
            merge(enrich_from_bing(nombre, provincia))
            time.sleep(0.8)
        except Exception as e:
            print(f"[bing] {nombre}: {e}")

    # 3. Si tenemos web pero faltan datos, raspar la web oficial
    if resultado.get("web") and faltan_datos():
        try:
            merge(enrich_from_web_propia(resultado["web"], nombre))
            time.sleep(0.8)
        except Exception as e:
            print(f"[web_propia] {nombre}: {e}")

    # 4. Búsqueda en directorios y redes sociales
    if faltan_datos():
        try:
            merge(enrich_from_social_and_directories(nombre, provincia))
            time.sleep(0.8)
        except Exception as e:
            print(f"[social_directorios] {nombre}: {e}")

    # 5. Si aún no tenemos web, buscar específicamente
    if not resultado.get("web"):
        try:
            web_found = encontrar_web_oficial(nombre, provincia)
            if web_found:
                resultado["web"] = web_found
                # Raspar la web encontrada si faltan datos
                if faltan_datos():
                    merge(enrich_from_web_propia(web_found, nombre))
            time.sleep(0.5)
        except Exception as e:
            print(f"[encontrar_web] {nombre}: {e}")

    # 6. Empresascif: datos registrales (gerente, dirección, teléfono)
    #    Especialmente útil para gerente que es muy difícil de obtener de otras fuentes
    if not resultado.get("gerente") or faltan_datos():
        try:
            merge(enrich_from_empresascif(nombre, provincia))
            time.sleep(0.5)
        except Exception as e:
            print(f"[empresascif] {nombre}: {e}")

    # 7. Google Places API (último recurso pagado)
    if faltan_datos() or not resultado["direccion"] or not resultado["web"]:
        try:
            merge(enrich_from_google_places(nombre, provincia))
            time.sleep(0.5)
        except Exception as e:
            print(f"[google_places_fallback] {nombre}: {e}")

    # 8. Licitaciones
    try:
        resultado["licita"] = check_licita(nombre)
        time.sleep(0.3)
    except Exception as e:
        print(f"[licita] {nombre}: {e}")

    return resultado

