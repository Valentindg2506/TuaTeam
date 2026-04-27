'''
Programa: OmniCheck Ultra - Verificador de Emails 360
Versión: 6.0 (DNSBL + Catch-all Detection)
Autor: Estudiante DAM
'''

from flask import Flask, render_template, request
from email_validator import validate_email, EmailNotValidError
import dns.resolver
import dns.exception
import smtplib
import socket

app = Flask(__name__)

class VerificadorSupremo:
    def __init__(self):
        ## LISTAS DE CONTROL DE CALIDAD ##
        self.dominios_basura = ['yopmail.com', 'tempmail.com', '10minutemail.com', 'guerrillamail.com']
        self.cuentas_genericas = ['info', 'admin', 'ventas', 'contacto', 'soporte', 'webmaster']
        # Servidores de listas negras conocidos #
        self.blacklists = ['zen.spamhaus.org', 'bl.spamcop.net']

    def verificarBuzonSMTP(self, email, mx_host):
        ## REALIZAMOS EL HANDSHAKE SMTP ##
        try:
            remitente = "audit@omnicheck.pro"
            server = smtplib.SMTP(timeout=7)
            server.connect(mx_host, 25)
            server.helo(socket.gethostname())
            server.mail(remitente)
            codigo, mensaje = server.rcpt(str(email))
            server.quit()
            return codigo == 250
        except:
            return False

    def detectarCatchAll(self, dominio, mx_host):
        ## VERIFICAMOS SI EL SERVIDOR ACEPTA CUALQUER COSA (FALSOS POSITIVOS) ##
        correo_falso = f"check_catchall_{socket.gethostname()}@{dominio}"
        return self.verificarBuzonSMTP(correo_falso, mx_host)

    def consultarBlacklists(self, dominio):
        ## BUSCAMOS EL DOMINIO EN LISTAS NEGRAS DE SPAM ##
        try:
            for bl in self.blacklists:
                query = f"{dominio}.{bl}"
                dns.resolver.resolve(query, 'A')
                return True # Si resuelve, está en la lista #
        except:
            return False
        return False

    def auditarSeguridad(self, dominio):
        ## ANALISIS DE SPF Y DMARC (EVITAR SPAM) ##
        seguridad = {"spf": False, "dmarc": False}
        try:
            txt_records = dns.resolver.resolve(dominio, 'TXT')
            seguridad["spf"] = any("v=spf1" in str(r) for r in txt_records)
            dns.resolver.resolve(f"_dmarc.{dominio}", 'TXT')
            seguridad["dmarc"] = True
        except:
            pass
        return seguridad

    def ejecutarAnalisisCompleto(self, email_input):
        score = 0
        detalles = []
        status = "Falso / Inseguro"
        
        try:
            ## 1. SINTAXIS ##
            v = validate_email(email_input, check_deliverability=False)
            correo_limpio = v.normalized
            usuario, dominio = correo_limpio.split('@')
            score += 20
            detalles.append("Estructura de email válida.")

            ## 2. DNS Y SEGURIDAD ##
            mx_records = dns.resolver.resolve(dominio, 'MX')
            mx_host = str(mx_records[0].exchange)
            score += 20
            
            seg = self.auditarSeguridad(dominio)
            if seg["spf"] and seg["dmarc"]:
                score += 20
                detalles.append("Seguridad DNS (SPF/DMARC) completa. Baja probabilidad de Spam.")
            else:
                detalles.append("Faltan registros SPF/DMARC. Alta probabilidad de Spam.")

            ## 3. REPUTACION ##
            en_lista_negra = self.consultarBlacklists(dominio)
            if en_lista_negra:
                score -= 40
                detalles.append("ALERTA: Dominio detectado en listas negras de Spam.")
            else:
                detalles.append("Reputación: Dominio limpio de listas negras conocidas.")

            ## 4. EXISTENCIA REAL ##
            existe = self.verificarBuzonSMTP(correo_limpio, mx_host)
            catch_all = self.detectarCatchAll(dominio, mx_host)

            if existe:
                if catch_all:
                    score += 10
                    detalles.append("Buzón: El servidor acepta todo (Catch-all). No se puede asegurar que sea una persona.")
                    status = "Válido (Incierto)"
                else:
                    score += 40
                    detalles.append("Buzón: Usuario verificado y real.")
                    status = "Real / Persona"
            else:
                score = 0
                detalles.append("Buzón: El usuario no existe en este servidor.")
                status = "Falso"

            return score, detalles, status

        except Exception as e:
            return 0, [f"Error técnico: {str(e)}"], "Inválido"

@app.route('/', methods=['GET', 'POST'])
def index():
    resultado = None
    if request.method == 'POST':
        print("--------------------")
        email_peticion = request.form.get('email')
        motor = VerificadorSupremo()
        
        puntos, info, estado = motor.ejecutarAnalisisCompleto(email_peticion)
        
        resultado = {
            "email": email_peticion,
            "score": puntos,
            "detalles": info,
            "status": estado
        }
        print(f"AUDITORIA FINALIZADA: {email_peticion} | SCORE: {puntos}")
        print("--------------------")

    return render_template('index.html', res=resultado)

if __name__ == '__main__':
    ## INICIAMOS EN PUERTO 8080 ##
    app.run(debug=True, port=8080)
