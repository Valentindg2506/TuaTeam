"""
Inicializa la base de datos y crea el usuario admin por defecto.
Uso:  python init_db.py
"""
from app import app, db
from models import Usuario

DEFAULT_ADMIN_EMAIL    = "admin@radar.local"
DEFAULT_ADMIN_PASSWORD = "Radar2024!"
DEFAULT_ADMIN_NOMBRE   = "Administrador"

with app.app_context():
    db.create_all()
    print("✅ Tablas creadas.")

    if not Usuario.query.filter_by(email=DEFAULT_ADMIN_EMAIL).first():
        admin = Usuario(
            nombre = DEFAULT_ADMIN_NOMBRE,
            email  = DEFAULT_ADMIN_EMAIL,
            rol    = "admin",
            activo = True,
        )
        admin.set_password(DEFAULT_ADMIN_PASSWORD)
        db.session.add(admin)
        db.session.commit()
        print(f"✅ Admin creado → {DEFAULT_ADMIN_EMAIL} / {DEFAULT_ADMIN_PASSWORD}")
    else:
        print("ℹ️  Admin ya existe.")

    print("\n🚀 Listo. Ejecuta:  python app.py")
