"""
Enriquecimiento de datos de cada lead:
  - Ficha de eleconomista  → gerente, CIF, dirección
  - Google search          → teléfono, web, email
  - PLACSP                 → licita sí/no
"""
import re
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus


HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0.0.0 Safari/537.36"),
    "Accept-Language": "es-ES,es;q=0.9",
}


def _get(url, timeout=10):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        if r.status_code == 200:
            return r.text
    except Exception:
        pass
    return None


# ── 1) Scraping de la ficha eleconomista ──────────────────────────────────────

def enrich_from_ficha(url_ficha):
    """
    Extrae de la ficha individual de eleconomista:
      - direccion, telefono, web, gerente, cif
    """
    data = {}
    if not url_ficha:
        return data

    html = _get(url_ficha)
    if not html:
        return data

    soup = BeautifulSoup(html, "lxml")
    texto = soup.get_text(" ", strip=True)

    # Dirección: buscar patrón típico "Dirección: X"
    m = re.search(r"(?:Direcci[oó]n|Domicilio)[:\s]+([A-ZÁÉÍÓÚÑ][^\n|]{10,120})", texto)
    if m:
        data["direccion"] = m.group(1).strip().rstrip(".,")

    # CIF
    m = re.search(r"\b([A-HJ-NP-SUV-Z]\d{7}[\dA-J])\b", texto)
    if m:
        data["cif"] = m.group(1)

    # Teléfono español: +34 o 9 dígitos
    m = re.search(r"(?:\+34\s?)?(?:[679]\d{2}\s?\d{3}\s?\d{3}|[89]\d{8})", texto)
    if m:
        data["telefono"] = m.group(0).strip()

    # Web (busca links externos que no sean el propio sitio)
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("http") and "eleconomista" not in href \
           and "google" not in href and "facebook" not in href \
           and "linkedin" not in href and "einforma" not in href:
            data["web"] = href
            break

    # Gerente: buscar "Administrador", "Gerente", "CEO", "Presidente"
    m = re.search(
        r"(?:Administrador(?:\s+\w+)?|Gerente|Consejero Delegado|Presidente|CEO)"
        r"[:\s]+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){1,3})",
        texto
    )
    if m:
        data["gerente"] = m.group(1).strip()

    return data


# ── 2) Búsqueda en Google (vía scraping básico) ───────────────────────────────

def enrich_from_google(nombre_empresa, provincia=""):
    """
    Busca en Google "<empresa> <provincia> teléfono" y extrae:
      - telefono, web, email, direccion
    Limitado: Google puede bloquear, fallar graciosamente.
    """
    data = {}
    query = quote_plus(f"{nombre_empresa} {provincia}")
    url = f"https://www.google.com/search?q={query}"

    html = _get(url, timeout=8)
    if not html:
        return data

    # Regex sobre el HTML bruto (Google usa mucho JS, pero los meta datos están)
    # Teléfono
    m = re.search(r"(?:\+34\s?)?[679]\d{2}\s?\d{3}\s?\d{3}", html)
    if m:
        data["telefono"] = m.group(0)

    # Email
    m = re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", html)
    if m and not any(x in m.group(0) for x in ("google.com", "@2x.png", "schema.org")):
        data["email"] = m.group(0)

    # Web oficial (primer link no de Google)
    soup = BeautifulSoup(html, "lxml")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        m_url = re.search(r"/url\?q=(https?://[^&]+)", href)
        if m_url:
            web = m_url.group(1)
            if not any(x in web for x in (
                "google.com", "youtube.com", "facebook.com", "instagram.com",
                "linkedin.com", "twitter.com", "wikipedia.org", "einforma.com",
                "eleconomista", "empresite", "axesor", "infoempresa",
                "paginasamarillas")):
                data["web"] = web
                break

    return data


# ── 3) PLACSP: ¿la empresa licita? ────────────────────────────────────────────

def check_placsp(nombre_empresa, cif=None):
    """
    Comprueba si la empresa aparece como adjudicataria en la Plataforma
    de Contratación del Sector Público.
    Devuelve "sí" / "no" / "?"
    """
    try:
        query = quote_plus(nombre_empresa)
        url = (
            "https://contrataciondelestado.es/wps/portal/!ut/p/b1/"
            "04_Sj9CPykssy0xPLMnMz0vMAfGjzOItDT1NnA28DLz83V1DDDyNDSz9_b1DjAzc"
            f"DIAKIpEVeHgZh5uEuwR7BgR4Gfj7BLsbGjiaGkAU4LAjXD9KP8gQj3JHvAoisn"
            f"MyPfUjcxwVATnxAJQ!/?q={query}"
        )
        # Nota: PLACSP usa JavaScript, scraping directo no funciona bien.
        # Una alternativa más fiable es buscar el nombre en Google junto con "PLACSP"
        # o "adjudicación" / "licitación"
        google_q = quote_plus(f'"{nombre_empresa}" adjudicación licitación')
        gurl = f"https://www.google.com/search?q={google_q}"
        html = _get(gurl, timeout=8)
        if not html:
            return "?"
        html_low = html.lower()
        if "contrataciondelestado" in html_low or "boe.es" in html_low \
           or "adjudicatario" in html_low or "licitación adjudicada" in html_low:
            return "sí"
        # Si aparecen muchos resultados genéricos sin menciones específicas
        if f'"{nombre_empresa.lower()}"' in html_low:
            # la empresa existe pero no hay menciones claras de licitación
            return "no"
        return "?"
    except Exception:
        return "?"


# ── Enriquecimiento completo (combina todo) ───────────────────────────────────

def enrich_lead(lead_dict):
    """
    Recibe dict con al menos 'nombre', 'provincia' y opcionalmente 'url'.
    Devuelve dict enriquecido con telefono/email/web/direccion/gerente/licita.
    """
    resultado = {
        "telefono": None,
        "email":    None,
        "web":      None,
        "direccion":None,
        "gerente":  None,
        "licita":   "?",
    }

    # 1. Ficha eleconomista
    try:
        ficha = enrich_from_ficha(lead_dict.get("url") or lead_dict.get("url_ficha"))
        for k in ("direccion", "telefono", "web", "gerente"):
            if ficha.get(k):
                resultado[k] = ficha[k]
        time.sleep(0.5)
    except Exception as e:
        print(f"[enrich_from_ficha] {e}")

    # 2. Google (solo si faltan datos)
    if not resultado["telefono"] or not resultado["web"] or not resultado["email"]:
        try:
            google = enrich_from_google(
                lead_dict["nombre"],
                lead_dict.get("provincia", "")
            )
            for k in ("telefono", "email", "web"):
                if not resultado[k] and google.get(k):
                    resultado[k] = google[k]
            time.sleep(1)
        except Exception as e:
            print(f"[enrich_from_google] {e}")

    # 3. PLACSP
    try:
        resultado["licita"] = check_placsp(lead_dict["nombre"])
        time.sleep(0.5)
    except Exception as e:
        print(f"[check_placsp] {e}")
        resultado["licita"] = "?"

    return resultado
