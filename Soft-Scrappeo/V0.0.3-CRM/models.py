"""
Modelos de base de datos para Radar CRM.
"""
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class Usuario(UserMixin, db.Model):
    __tablename__ = "usuarios"

    id              = db.Column(db.Integer, primary_key=True)
    nombre          = db.Column(db.String(120), nullable=False)
    email           = db.Column(db.String(160), unique=True, nullable=False)
    password_hash   = db.Column(db.String(255), nullable=False)
    rol             = db.Column(db.String(20),  nullable=False)   # admin/supervisor/comercial
    activo          = db.Column(db.Boolean, default=True)
    fecha_creacion  = db.Column(db.DateTime, default=datetime.utcnow)
    ultimo_acceso   = db.Column(db.DateTime, nullable=True)

    asignaciones    = db.relationship("Asignacion", backref="comercial", lazy="dynamic",
                                       foreign_keys="Asignacion.comercial_id")
    leads_asignados = db.relationship("Lead", backref="comercial", lazy="dynamic",
                                       foreign_keys="Lead.comercial_id")
    comentarios     = db.relationship("Comentario", backref="autor", lazy="dynamic")

    def set_password(self, pwd):
        self.password_hash = generate_password_hash(pwd)

    def check_password(self, pwd):
        return check_password_hash(self.password_hash, pwd)

    @property
    def es_admin(self):      return self.rol == "admin"
    @property
    def es_supervisor(self): return self.rol == "supervisor"
    @property
    def es_comercial(self):  return self.rol == "comercial"


class Asignacion(db.Model):
    """
    El admin asigna un CNAE + provincia a un comercial.
    Cuando se crea, se lanza el scraping y se generan Leads.
    """
    __tablename__ = "asignaciones"

    id              = db.Column(db.Integer, primary_key=True)
    comercial_id    = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    creado_por_id   = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    cnae            = db.Column(db.String(10),  nullable=False)
    cnae_desc       = db.Column(db.String(200), nullable=True)
    provincia       = db.Column(db.String(60),  nullable=True)      # vacío = nacional
    paginas         = db.Column(db.Integer, default=3)
    estado          = db.Column(db.String(20), default="pendiente")  # pendiente/scrapeando/completada/error
    progreso        = db.Column(db.Integer, default=0)
    mensaje         = db.Column(db.String(300), nullable=True)
    total_leads     = db.Column(db.Integer, default=0)
    fecha_creacion  = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_completada= db.Column(db.DateTime, nullable=True)

    creado_por = db.relationship("Usuario", foreign_keys=[creado_por_id])
    leads      = db.relationship("Lead", backref="asignacion", lazy="dynamic",
                                 cascade="all, delete-orphan")


class Lead(db.Model):
    """Una empresa del ranking asignada a un comercial."""
    __tablename__ = "leads"

    id              = db.Column(db.Integer, primary_key=True)
    asignacion_id   = db.Column(db.Integer, db.ForeignKey("asignaciones.id"), nullable=False)
    comercial_id    = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)

    # Datos básicos del scraping principal
    nombre          = db.Column(db.String(250), nullable=False)
    cnae            = db.Column(db.String(10),  nullable=True)
    provincia       = db.Column(db.String(60),  nullable=True)
    posicion_nacional = db.Column(db.Integer, nullable=True)
    evolucion       = db.Column(db.Integer, nullable=True)
    tendencia       = db.Column(db.String(15), nullable=True)  # Sube/Baja/Igual/ND
    facturacion_num  = db.Column(db.BigInteger, nullable=True)
    facturacion_raw  = db.Column(db.String(60), nullable=True)
    url_ficha       = db.Column(db.String(400), nullable=True)

    # Datos enriquecidos (scraping de ficha + Google)
    telefono        = db.Column(db.String(30),  nullable=True)
    email           = db.Column(db.String(160), nullable=True)
    web             = db.Column(db.String(250), nullable=True)
    direccion       = db.Column(db.String(300), nullable=True)
    gerente         = db.Column(db.String(180), nullable=True)
    licita          = db.Column(db.String(10),  default="?")   # "sí" / "no" / "?"

    # CRM / Kanban
    estado          = db.Column(db.String(30), default="nuevo",
                                index=True)  # ver config.KANBAN_ESTADOS
    orden           = db.Column(db.Integer, default=0)
    enriquecido     = db.Column(db.Boolean, default=False)
    fecha_creacion  = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_actualizacion = db.Column(db.DateTime, default=datetime.utcnow,
                                     onupdate=datetime.utcnow)

    comentarios = db.relationship("Comentario", backref="lead", lazy="dynamic",
                                  cascade="all, delete-orphan",
                                  order_by="Comentario.fecha.desc()")
    actividades = db.relationship("Actividad", backref="lead", lazy="dynamic",
                                  cascade="all, delete-orphan",
                                  order_by="Actividad.fecha.desc()")

    def to_dict(self):
        return {
            "id":              self.id,
            "nombre":          self.nombre,
            "cnae":            self.cnae,
            "provincia":       self.provincia,
            "posicion":        self.posicion_nacional,
            "evolucion":       self.evolucion,
            "tendencia":       self.tendencia,
            "facturacion_num": self.facturacion_num,
            "facturacion_raw": self.facturacion_raw,
            "telefono":        self.telefono,
            "email":           self.email,
            "web":             self.web,
            "direccion":       self.direccion,
            "gerente":         self.gerente,
            "licita":          self.licita,
            "url_ficha":       self.url_ficha,
            "estado":          self.estado,
            "orden":           self.orden,
            "enriquecido":     self.enriquecido,
            "comentarios_n":   self.comentarios.count(),
            "fecha_actualizacion": self.fecha_actualizacion.strftime("%d/%m/%Y %H:%M")
                                    if self.fecha_actualizacion else "",
        }


class Comentario(db.Model):
    """Notas/conversaciones que el comercial anota del lead."""
    __tablename__ = "comentarios"

    id          = db.Column(db.Integer, primary_key=True)
    lead_id     = db.Column(db.Integer, db.ForeignKey("leads.id"), nullable=False)
    autor_id    = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    texto       = db.Column(db.Text, nullable=False)
    fecha       = db.Column(db.DateTime, default=datetime.utcnow)


class Actividad(db.Model):
    """
    Registro automático de acciones (cambio de estado, llamada, reunión).
    Lo usa el supervisor para controlar el trabajo del comercial.
    """
    __tablename__ = "actividades"

    id          = db.Column(db.Integer, primary_key=True)
    lead_id     = db.Column(db.Integer, db.ForeignKey("leads.id"), nullable=False)
    usuario_id  = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    tipo        = db.Column(db.String(30), nullable=False)   # estado_cambio / comentario / llamada...
    detalle     = db.Column(db.String(300), nullable=True)
    fecha       = db.Column(db.DateTime, default=datetime.utcnow)

    usuario = db.relationship("Usuario")
