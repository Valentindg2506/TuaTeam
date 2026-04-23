from app import app, db
from models import Lead
from enrichment import enrich_lead

with app.app_context():
    leads = Lead.query.filter(Lead.telefono.is_(None)).all()
    print(f"Re-enriqueciendo {len(leads)} leads...")
    import time
    for l in leads:
        print(f"-> {l.nombre}")
        d = enrich_lead({"nombre": l.nombre, "provincia": l.provincia, "url_ficha": l.url_ficha})
        l.telefono = d.get("telefono") or l.telefono
        l.email = d.get("email") or l.email
        l.web = d.get("web") or l.web
        l.direccion = d.get("direccion") or l.direccion
        l.gerente = d.get("gerente") or l.gerente
        if d.get("licita") and d["licita"] != "?":
            l.licita = d["licita"]
        db.session.commit()
        time.sleep(1)
    print("FIN")
