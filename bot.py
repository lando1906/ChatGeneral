import os
import time
import imaplib
import email
import smtplib
from flask import Flask, jsonify
import threading
import logging
from datetime import datetime

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# =============================================================================
# CONFIGURACIÓN PARA GMAIL
# =============================================================================

EMAIL_ACCOUNT = "videodown797@gmail.com"
EMAIL_PASSWORD = "nlhoedrevnlihgdo"

IMAP_SERVER = "imap.gmail.com"
IMAP_PORT = 993
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

SMTP_ACCOUNT = EMAIL_ACCOUNT
SMTP_PASSWORD = EMAIL_PASSWORD

CHECK_INTERVAL = 3

# =============================================================================
# FUNCIONES DEL BOT YOUCHAT - VERSIÓN RAW
# =============================================================================

class YouChatBot:
    def __init__(self):
        self.is_running = False
        self.last_check = None
        self.processed_emails = set()
        self.total_processed = 0
    
    def extraer_headers_youchat(self, mensaje_email):
        """Extrae headers específicos de YouChat"""
        headers_youchat = {}
        
        headers_especificos = [
            'Message-ID', 'Msg_id', 'Chat-Version', 'Pd', 
            'Sender-Alias', 'From-Alias', 'Thread-ID', 'User-ID',
            'X-YouChat-Session', 'X-YouChat-Platform'
        ]
        
        for header, valor in mensaje_email.items():
            if any(youchat_header in header for youchat_header in ['Msg_id', 'Chat-', 'Pd', 'YouChat']):
                headers_youchat[header] = valor
            elif header in headers_especificos:
                headers_youchat[header] = valor
        
        return headers_youchat

    def conectar_imap(self):
        """Conexión IMAP para Gmail"""
        try:
            mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
            mail.login(EMAIL_ACCOUNT, EMAIL_PASSWORD)
            return mail
        except Exception as e:
            logger.error(f"❌ Error conexión IMAP: {str(e)}")
            return None

    def construir_mensaje_raw_youchat(self, destinatario, msg_id_original=None, youchat_profile_headers=None):
        """Construye el mensaje en formato RAW exacto para YouChat"""
        try:
            # 1. Headers de YouChat Generales
            headers_string = ""
            if youchat_profile_headers and isinstance(youchat_profile_headers, dict):
                for key, value in youchat_profile_headers.items():
                    if value and key not in ['Msg_id', 'Chat-Version', 'Pd', 'Sender-Alias', 'From-Alias']:
                        headers_string += f"{key}: {value}\r\n"
            
            # 2. Headers de Threading
            domain = SMTP_ACCOUNT.split('@')[1]
            headers_string += f"Message-ID: <auto-reply-{int(time.time()*1000)}@{domain}>\r\n"
            
            if msg_id_original:
                clean_message_id = msg_id_original
                if not (msg_id_original.startswith('<') and msg_id_original.endswith('>')):
                    clean_message_id = f"<{msg_id_original}>"
                
                headers_string += f"In-Reply-To: {clean_message_id}\r\n"
                headers_string += f"References: {clean_message_id}\r\n"
            
            # 3. Headers del Bot
            headers_string += f"Msg_id: auto-reply-{int(time.time()*1000)}\r\n"
            
            chat_version = '1.1'
            if youchat_profile_headers and 'Chat-Version' in youchat_profile_headers:
                chat_version = youchat_profile_headers['Chat-Version']
            headers_string += f"Chat-Version: {chat_version}\r\n"
            
            pd_value = None
            if youchat_profile_headers and 'Pd' in youchat_profile_headers:
                pd_value = youchat_profile_headers['Pd']
            if pd_value:
                headers_string += f"Pd: {str(pd_value).strip()}\r\n"
            
            # 4. Headers Estándar
            headers_string += "MIME-Version: 1.0\r\n"
            headers_string += 'Content-Type: text/plain; charset="UTF-8"\r\n'
            
            # 5. Construcción FINAL del mensaje RAW
            mensaje_texto = "¡Hola! Soy un bot en desarrollo. Pronto podré descargar tus Reels de Instagram."
            
            mail_raw = (
                f"From: {SMTP_ACCOUNT}\r\n" +
                f"To: {destinatario}\r\n" +
                f"Subject: YouChat\r\n" +
                headers_string +
                f"\r\n" +
                f"{mensaje_texto}"
            )
            
            return mail_raw.encode('utf-8')
            
        except Exception as e:
            logger.error(f"❌ Error construyendo mensaje RAW: {str(e)}")
            return None

    def enviar_respuesta_raw(self, destinatario, msg_id_original=None, youchat_profile_headers=None):
        """Envía respuesta usando formato RAW"""
        try:
            # Construir mensaje RAW
            mensaje_raw = self.construir_mensaje_raw_youchat(
                destinatario, 
                msg_id_original, 
                youchat_profile_headers
            )
            
            if not mensaje_raw:
                return False
            
            # Enviar usando SMTP
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as servidor:
                servidor.starttls()
                servidor.login(SMTP_ACCOUNT, SMTP_PASSWORD)
                # Enviar mensaje RAW
                servidor.sendmail(SMTP_ACCOUNT, destinatario, mensaje_raw)
            
            logger.info("✅ Respuesta RAW enviada a: %s", destinatario)
            return True
            
        except Exception as e:
            logger.error("❌ Error enviando respuesta RAW: %s", str(e))
            return False

    def procesar_emails_no_leidos(self):
        """Función principal que revisa emails no leídos"""
        try:
            mail = self.conectar_imap()
            if not mail:
                return
                
            mail.select("inbox")
            
            estado, mensajes = mail.search(None, "UNSEEN")
            if estado != "OK":
                return
            
            ids_emails = mensajes[0].split()
            if not ids_emails:
                return
            
            logger.info("📥 %d nuevo(s) email(s) para procesar", len(ids_emails))
            
            for id_email in ids_emails:
                try:
                    email_id = id_email.decode()
                    if email_id in self.processed_emails:
                        continue
                    
                    estado, datos_msg = mail.fetch(id_email, "(RFC822)")
                    if estado != "OK":
                        continue
                    
                    email_crudo = datos_msg[0][1]
                    mensaje = email.message_from_bytes(email_crudo)
                    
                    remitente = mensaje["From"]
                    email_remitente = ""
                    if "<" in remitente and ">" in remitente:
                        email_remitente = remitente.split("<")[1].split(">")[0]
                    else:
                        email_remitente = remitente
                    
                    logger.info("👤 Procesando mensaje de: %s", email_remitente)
                    
                    headers_youchat = self.extraer_headers_youchat(mensaje)
                    msg_id_original = headers_youchat.get('Message-ID')
                    
                    if msg_id_original:
                        logger.info("🔗 Message-ID del mensaje original: %s", msg_id_original)
                    
                    # Usar el nuevo método RAW
                    exito = self.enviar_respuesta_raw(
                        email_remitente,
                        msg_id_original=msg_id_original,
                        youchat_profile_headers=headers_youchat
                    )
                    
                    if exito:
                        self.processed_emails.add(email_id)
                        self.total_processed += 1
                        logger.info("💬 Respuesta #%d enviada exitosamente", self.total_processed)
                    else:
                        logger.error("❌ Falló el envío de la respuesta")
                    
                except Exception as e:
                    logger.error("❌ Error procesando email: %s", str(e))
                    continue
                    
        except Exception as e:
            logger.error("❌ Error procesando emails: %s", str(e))
        finally:
            try:
                mail.close()
                mail.logout()
            except:
                pass

    def run_bot(self):
        """Ejecuta el bot en un bucle continuo"""
        self.is_running = True
        logger.info("🚀 Bot YouChat INICIADO - VERSIÓN RAW")
        logger.info("⏰ Intervalo: %d segundos", CHECK_INTERVAL)
        logger.info("📧 Cuenta Gmail: %s", EMAIL_ACCOUNT)
        
        while self.is_running:
            try:
                self.last_check = datetime.now()
                logger.info("🔍 Revisando nuevos emails - %s", self.last_check.strftime('%H:%M:%S'))
                
                self.procesar_emails_no_leidos()
                
                time.sleep(CHECK_INTERVAL)
                
            except Exception as e:
                logger.error("💥 Error en el bucle principal: %s", str(e))
                time.sleep(CHECK_INTERVAL)

# =============================================================================
# INSTANCIA GLOBAL DEL BOT
# =============================================================================

youchat_bot = YouChatBot()
bot_thread = None

# =============================================================================
# RUTAS DEL SERVICIO WEB
# =============================================================================

@app.route('/')
def home():
    return jsonify({
        "status": "online",
        "service": "YouChat Bot - RAW Version",
        "version": "1.0",
        "interval": f"{CHECK_INTERVAL} segundos",
        "email_account": EMAIL_ACCOUNT,
        "last_check": youchat_bot.last_check.isoformat() if youchat_bot.last_check else None,
        "total_processed": youchat_bot.total_processed,
        "is_running": youchat_bot.is_running
    })

@app.route('/health')
def health():
    return jsonify({
        "status": "healthy", 
        "timestamp": datetime.now().isoformat(),
        "bot_running": youchat_bot.is_running
    })

@app.route('/start')
def start_bot():
    global bot_thread
    
    if youchat_bot.is_running:
        return jsonify({"status": "already_running", "message": "El bot ya está en ejecución"})
    
    bot_thread = threading.Thread(target=youchat_bot.run_bot, daemon=True)
    bot_thread.start()
    
    return jsonify({"status": "started", "message": "Bot iniciado correctamente"})

@app.route('/stop')
def stop_bot():
    youchat_bot.is_running = False
    return jsonify({"status": "stopped", "message": "Bot detenido"})

@app.route('/status')
def status():
    return jsonify({
        "is_running": youchat_bot.is_running,
        "last_check": youchat_bot.last_check.isoformat() if youchat_bot.last_check else None,
        "total_processed": youchat_bot.total_processed,
        "check_interval": CHECK_INTERVAL
    })

# =============================================================================
# INICIALIZACIÓN AUTOMÁTICA
# =============================================================================

def inicializar_bot():
    """Inicializa el bot automáticamente al cargar la aplicación"""
    global bot_thread
    
    logger.info("🔧 Iniciando bot automáticamente...")
    bot_thread = threading.Thread(target=youchat_bot.run_bot, daemon=True)
    bot_thread.start()
    logger.info("🎉 Bot iniciado y listo para recibir mensajes")

# Iniciar el bot cuando se carga la aplicación
inicializar_bot()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)