"""Modelos Radar CRM v2 — incluye competidores, notificaciones y chat."""
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class Usuario(UserMixin, db.Model):
    __tablename__ = "usuarios"
    id             = db.Column(db.Integer, primary_key=True)
    nombre         = db.Column(db.String(120), nullable=False)
    email          = db.Column(db.String(160), unique=True, nullable=False)
    password_hash  = db.Column(db.String(255), nullable=False)
    rol            = db.Column(db.String(20), nullable=False)
    activo         = db.Column(db.Boolean, default=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    ultimo_acceso  = db.Column(db.DateTime, nullable=True)

    def set_password(self, p): self.password_hash = generate_password_hash(p)
    def check_password(self, p): return check_password_hash(self.password_hash, p)

    @property
    def es_admin(self):      return self.rol == "admin"
    @property
    def es_supervisor(self): return self.rol == "supervisor"
    @property
    def es_comercial(self):  return self.rol == "comercial"

    def puede_ver_lead(self, lead):
        return self.rol in ("admin", "supervisor") or lead.comercial_id == self.id


class Asignacion(db.Model):
    __tablename__ = "asignaciones"
    id               = db.Column(db.Integer, primary_key=True)
    comercial_id     = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    creado_por_id    = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    cnae             = db.Column(db.String(10), nullable=False)
    cnae_desc        = db.Column(db.String(200), nullable=True)
    provincia        = db.Column(db.String(60), nullable=True)
    paginas          = db.Column(db.Integer, default=3)
    estado           = db.Column(db.String(20), default="pendiente")
    progreso         = db.Column(db.Integer, default=0)
    mensaje          = db.Column(db.String(500), nullable=True)
    total_leads      = db.Column(db.Integer, default=0)
    fecha_creacion   = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_completada = db.Column(db.DateTime, nullable=True)

    comercial  = db.relationship("Usuario", foreign_keys=[comercial_id])
    creado_por = db.relationship("Usuario", foreign_keys=[creado_por_id])
    leads      = db.relationship("Lead", backref="asignacion", lazy="dynamic",
                                 cascade="all, delete-orphan")


class Lead(db.Model):
    __tablename__ = "leads"
    id                  = db.Column(db.Integer, primary_key=True)
    asignacion_id       = db.Column(db.Integer, db.ForeignKey("asignaciones.id"), nullable=False)
    comercial_id        = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)

    # Datos del ranking
    nombre              = db.Column(db.String(250), nullable=False)
    cnae                = db.Column(db.String(10), nullable=True)
    provincia           = db.Column(db.String(60), nullable=True)
    posicion_nacional   = db.Column(db.Integer, nullable=True)
    evolucion           = db.Column(db.Integer, nullable=True)
    tendencia           = db.Column(db.String(15), nullable=True)
    facturacion_num     = db.Column(db.BigInteger, nullable=True)
    facturacion_raw     = db.Column(db.String(60), nullable=True)
    url_ficha           = db.Column(db.String(400), nullable=True)

    # Datos enriquecidos
    telefono            = db.Column(db.String(30), nullable=True)
    email               = db.Column(db.String(160), nullable=True)
    web                 = db.Column(db.String(250), nullable=True)
    direccion           = db.Column(db.String(300), nullable=True)
    gerente             = db.Column(db.String(180), nullable=True)
    licita              = db.Column(db.String(10), default="?")
    enriquecido         = db.Column(db.Boolean, default=False)

    # CRM
    estado              = db.Column(db.String(30), default="nuevo", index=True)
    orden               = db.Column(db.Integer, default=0)
    fecha_creacion      = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_actualizacion = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    comercial    = db.relationship("Usuario", foreign_keys=[comercial_id])
    comentarios  = db.relationship("Comentario", backref="lead", lazy="dynamic",
                                   cascade="all, delete-orphan",
                                   order_by="Comentario.fecha.desc()")
    actividades  = db.relationship("Actividad", backref="lead", lazy="dynamic",
                                   cascade="all, delete-orphan",
                                   order_by="Actividad.fecha.desc()")
    competidores = db.relationship("Competidor", backref="lead", lazy="dynamic",
                                   cascade="all, delete-orphan",
                                   order_by="Competidor.orden")

    def to_dict(self):
        return {
            "id": self.id, "nombre": self.nombre, "cnae": self.cnae,
            "provincia": self.provincia, "posicion": self.posicion_nacional,
            "tendencia": self.tendencia, "facturacion_raw": self.facturacion_raw,
            "telefono": self.telefono, "email": self.email, "web": self.web,
            "direccion": self.direccion, "gerente": self.gerente,
            "licita": self.licita, "estado": self.estado,
            "enriquecido": self.enriquecido,
            "n_comentarios": self.comentarios.count(),
        }


class Competidor(db.Model):
    """Los 3 competidores calculados para cada lead."""
    __tablename__ = "competidores"
    id              = db.Column(db.Integer, primary_key=True)
    lead_id         = db.Column(db.Integer, db.ForeignKey("leads.id"), nullable=False)
    orden           = db.Column(db.Integer, default=0)   # 1, 2, 3
    nombre          = db.Column(db.String(250), nullable=False)
    cnae            = db.Column(db.String(20), nullable=True)   # CNAE del competidor
    provincia       = db.Column(db.String(60), nullable=True)
    facturacion_raw = db.Column(db.String(60), nullable=True)
    facturacion_num = db.Column(db.BigInteger, nullable=True)
    posicion        = db.Column(db.Integer, nullable=True)
    tendencia       = db.Column(db.String(15), nullable=True)
    ratio           = db.Column(db.Float, nullable=True)
    misma_provincia = db.Column(db.Boolean, default=False)
    url_ficha       = db.Column(db.String(400), nullable=True)


class Comentario(db.Model):
    __tablename__ = "comentarios"
    id         = db.Column(db.Integer, primary_key=True)
    lead_id    = db.Column(db.Integer, db.ForeignKey("leads.id"), nullable=False)
    autor_id   = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    texto      = db.Column(db.Text, nullable=False)
    fecha      = db.Column(db.DateTime, default=datetime.utcnow)
    autor      = db.relationship("Usuario")


class Actividad(db.Model):
    __tablename__ = "actividades"
    id         = db.Column(db.Integer, primary_key=True)
    lead_id    = db.Column(db.Integer, db.ForeignKey("leads.id"), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    tipo       = db.Column(db.String(30), nullable=False)
    detalle    = db.Column(db.String(300), nullable=True)
    fecha      = db.Column(db.DateTime, default=datetime.utcnow)
    usuario    = db.relationship("Usuario")


class Notificacion(db.Model):
    """Notificaciones en tiempo real para cada usuario."""
    __tablename__ = "notificaciones"
    id         = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    tipo       = db.Column(db.String(30), nullable=False)   # info/success/warning/lead
    titulo     = db.Column(db.String(120), nullable=False)
    texto      = db.Column(db.String(300), nullable=True)
    url        = db.Column(db.String(300), nullable=True)
    leida      = db.Column(db.Boolean, default=False)
    fecha      = db.Column(db.DateTime, default=datetime.utcnow)
    usuario    = db.relationship("Usuario")


class MensajeChat(db.Model):
    """Chat entre usuarios: comercial↔supervisor o supervisor↔admin."""
    __tablename__ = "mensajes_chat"
    id           = db.Column(db.Integer, primary_key=True)
    de_id        = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    para_id      = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    texto        = db.Column(db.Text, nullable=False)
    leido        = db.Column(db.Boolean, default=False)
    fecha        = db.Column(db.DateTime, default=datetime.utcnow)
    de           = db.relationship("Usuario", foreign_keys=[de_id])
    para         = db.relationship("Usuario", foreign_keys=[para_id])
