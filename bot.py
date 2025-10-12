import os
import time
import imaplib
import email
import smtplib
from flask import Flask, jsonify
import threading
import logging
from datetime import datetime
import traceback

# Configuración de logging mejorada
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('youchat_bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# =============================================================================
# CONFIGURACIÓN PARA GMAIL - VERIFICADA
# =============================================================================

EMAIL_ACCOUNT = "videodown797@gmail.com"
EMAIL_PASSWORD = "nlhoedrevnlihgdo"

IMAP_SERVER = "imap.gmail.com"
IMAP_PORT = 993
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

CHECK_INTERVAL = 3

# =============================================================================
# FUNCIONES DEL BOT YOUCHAT - VERSIÓN CORREGIDA
# =============================================================================

class YouChatBot:
    def __init__(self):
        self.is_running = False
        self.last_check = None
        self.processed_emails = set()
        self.total_processed = 0
        self.imap_connection = None
        self.last_reconnect = None

    def conectar_imap_robusto(self):
        """Conexión IMAP robusta con manejo de errores mejorado"""
        try:
            if self.imap_connection:
                try:
                    # Verificar si la conexión sigue activa
                    self.imap_connection.noop()
                    logger.debug("✅ Conexión IMAP aún activa")
                    return self.imap_connection
                except:
                    logger.warning("🔌 Conexión IMAP perdida, reconectando...")
                    self.imap_connection = None

            logger.info("🔗 Estableciendo nueva conexión IMAP...")
            mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
            mail.login(EMAIL_ACCOUNT, EMAIL_PASSWORD)
            mail.select("inbox")
            
            self.imap_connection = mail
            self.last_reconnect = datetime.now()
            logger.info("✅ Conexión IMAP establecida exitosamente")
            return mail
            
        except Exception as e:
            logger.error(f"❌ Error crítico en conexión IMAP: {str(e)}")
            logger.error(traceback.format_exc())
            self.imap_connection = None
            return None

    def verificar_conexion_imap(self):
        """Verifica y mantiene la conexión IMAP activa"""
        try:
            if not self.imap_connection:
                return self.conectar_imap_robusto()
            
            # Verificar conexión cada 10 minutos o si hay error
            if self.last_reconnect and (datetime.now() - self.last_reconnect).seconds > 600:
                logger.info("🔄 Reconexión programada IMAP")
                self.cerrar_conexion_imap()
                return self.conectar_imap_robusto()
                
            # Test de conexión
            self.imap_connection.noop()
            return self.imap_connection
            
        except Exception as e:
            logger.warning(f"🔌 Conexión IMAP necesita reconexión: {str(e)}")
            self.cerrar_conexion_imap()
            return self.conectar_imap_robusto()

    def cerrar_conexion_imap(self):
        """Cierra la conexión IMAP de forma segura"""
        try:
            if self.imap_connection:
                self.imap_connection.close()
                self.imap_connection.logout()
                self.imap_connection = None
                logger.debug("🔒 Conexión IMAP cerrada")
        except:
            self.imap_connection = None

    def extraer_headers_youchat(self, mensaje_email):
        """Extrae headers específicos de YouChat de manera más completa"""
        headers_youchat = {}
        
        headers_especificos = [
            'Message-ID', 'Msg_id', 'Chat-Version', 'Pd', 
            'Sender-Alias', 'From-Alias', 'Thread-ID', 'User-ID',
            'X-YouChat-Session', 'X-YouChat-Platform', 'X-YouChat-Device',
            'Chat-ID', 'Session-ID', 'X-Chat-Signature', 'X-YouChat-Version',
            'X-YouChat-Build', 'X-YouChat-Environment'
        ]
        
        for header, valor in mensaje_email.items():
            header_lower = header.lower()
            if any(keyword in header_lower for keyword in ['youchat', 'chat-', 'msg_', 'x-youchat', 'x-chat']):
                headers_youchat[header] = valor
            elif header in headers_especificos:
                headers_youchat[header] = valor
    
        logger.debug("📨 Headers de YouChat extraídos: %s", list(headers_youchat.keys()))
        return headers_youchat

    def extraer_email_remitente(self, remitente):
        """Extrae el email del remitente de forma robusta"""
        try:
            if "<" in remitente and ">" in remitente:
                return remitente.split("<")[1].split(">")[0].strip()
            else:
                return remitente.strip()
        except Exception as e:
            logger.error("❌ Error extrayendo email del remitente: %s", str(e))
            return None

    def construir_mensaje_raw_youchat(self, destinatario, msg_id_original=None, youchat_profile_headers=None, asunto_original=None):
        """Construye el mensaje en formato RAW optimizado para YouChat"""
        try:
            logger.info("🔨 Construyendo mensaje RAW...")
            
            headers_string = ""
            if youchat_profile_headers and isinstance(youchat_profile_headers, dict):
                for key, value in youchat_profile_headers.items():
                    if value and key not in ['Msg_id', 'Message-ID']:
                        headers_string += f"{key}: {value}\r\n"

            # ✅ CORREGIDO: Usar EMAIL_ACCOUNT en lugar de SMTP_ACCOUNT
            domain = EMAIL_ACCOUNT.split('@')[1]
            nuevo_msg_id = f"<auto-reply-{int(time.time()*1000)}@{domain}>"
            headers_string += f"Message-ID: {nuevo_msg_id}\r\n"

            if msg_id_original:
                clean_message_id = msg_id_original
                if not (msg_id_original.startswith('<') and msg_id_original.endswith('>')):
                    clean_message_id = f"<{msg_id_original}>"
                
                headers_string += f"In-Reply-To: {clean_message_id}\r\n"
                headers_string += f"References: {clean_message_id}\r\n"

            headers_string += f"Msg_id: auto-reply-{int(time.time()*1000)}\r\n"
            
            chat_version = youchat_profile_headers.get('Chat-Version', '1.1') if youchat_profile_headers else '1.1'
            headers_string += f"Chat-Version: {chat_version}\r\n"
            
            pd_value = youchat_profile_headers.get('Pd') if youchat_profile_headers else None
            if pd_value:
                headers_string += f"Pd: {str(pd_value).strip()}\r\n"
            
            headers_string += "MIME-Version: 1.0\r\n"
            headers_string += 'Content-Type: text/plain; charset="UTF-8"\r\n'
            headers_string += 'Content-Transfer-Encoding: 8bit\r\n'
            
            asunto = "YouChat"
            if asunto_original:
                if not asunto_original.lower().startswith('re:'):
                    asunto = f"Re: {asunto_original}"
                else:
                    asunto = asunto_original

            mensaje_texto = "¡Hola! Soy un bot en desarrollo. Pronto podré descargar tus Reels de Instagram."

            mail_raw = (
                f"From: {EMAIL_ACCOUNT}\r\n" +
                f"To: {destinatario}\r\n" +
                f"Subject: {asunto}\r\n" +
                headers_string +
                f"\r\n" +
                f"{mensaje_texto}"
            )

            logger.info("📧 Mensaje RAW construido exitosamente para: %s", destinatario)
            return mail_raw.encode('utf-8')

        except Exception as e:
            logger.error(f"❌ Error construyendo mensaje RAW: {str(e)}")
            logger.error(f"🔍 Traceback: {traceback.format_exc()}")
            return None

    def enviar_respuesta_raw(self, destinatario, msg_id_original=None, youchat_profile_headers=None, asunto_original=None):
        """Envía respuesta usando formato RAW mejorado"""
        try:
            logger.info("🔄 Iniciando envío de respuesta RAW...")
            
            mensaje_raw = self.construir_mensaje_raw_youchat(
                destinatario, 
                msg_id_original, 
                youchat_profile_headers,
                asunto_original
            )

            logger.info("📧 Mensaje RAW construido, procediendo a enviar...")

            if not mensaje_raw:
                logger.error("❌ No se pudo construir el mensaje RAW")
                return False

            logger.info("🔗 Conectando al servidor SMTP (timeout: 30s)...")
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30) as servidor:
                logger.info("🔐 Iniciando TLS...")
                servidor.starttls()
                
                logger.info("👤 Autenticando con Gmail...")
                servidor.login(EMAIL_ACCOUNT, EMAIL_PASSWORD)
                
                logger.info("📤 Enviando email...")
                servidor.sendmail(EMAIL_ACCOUNT, destinatario, mensaje_raw)

            logger.info("✅ Respuesta RAW enviada exitosamente a: %s", destinatario)
            return True

        except smtplib.SMTPException as e:
            logger.error("❌ Error SMTP específico: %s", str(e))
            return False
        except Exception as e:
            logger.error("❌ Error inesperado enviando respuesta: %s", str(e))
            logger.error("🔍 Traceback completo: %s", traceback.format_exc())
            return False

    def procesar_emails_no_leidos(self):
        """Función principal mejorada para procesar emails con manejo robusto de conexiones"""
        mail = None
        try:
            mail = self.verificar_conexion_imap()
            if not mail:
                logger.error("❌ No se pudo establecer conexión IMAP")
                return

            logger.debug("🔍 Buscando emails no leídos...")
            estado, mensajes = mail.search(None, "UNSEEN")
            if estado != "OK":
                logger.info("📭 No hay emails nuevos o error en búsqueda")
                return

            ids_emails = mensajes[0].split()
            if not ids_emails:
                logger.debug("📭 Cero emails no leídos encontrados")
                return

            logger.info("📥 %d nuevo(s) email(s) para procesar", len(ids_emails))

            for id_email in ids_emails:
                try:
                    email_id = id_email.decode()
                    if email_id in self.processed_emails:
                        logger.debug("⏭️ Email ya procesado: %s", email_id)
                        continue

                    logger.debug("📨 Procesando email ID: %s", email_id)
                    estado, datos_msg = mail.fetch(id_email, "(RFC822)")
                    
                    if estado != "OK":
                        logger.error("❌ Error obteniendo email: %s", email_id)
                        continue

                    if not datos_msg or not datos_msg[0]:
                        logger.error("❌ No hay datos en el email: %s", email_id)
                        continue

                    email_crudo = datos_msg[0][1]
                    mensaje = email.message_from_bytes(email_crudo)

                    remitente = mensaje["From"]
                    asunto_original = mensaje.get("Subject", "")
                    
                    email_remitente = self.extraer_email_remitente(remitente)
                    if not email_remitente:
                        logger.error("❌ No se pudo extraer email del remitente: %s", remitente)
                        continue

                    logger.info("👤 Procesando mensaje de: %s - Asunto: %s", email_remitente, asunto_original)

                    headers_youchat = self.extraer_headers_youchat(mensaje)
                    msg_id_original = mensaje.get('Message-ID') or headers_youchat.get('Message-ID')

                    if msg_id_original:
                        logger.debug("🔗 Message-ID del mensaje original: %s", msg_id_original)

                    logger.info("🚀 Iniciando proceso de respuesta...")
                    exito = self.enviar_respuesta_raw(
                        email_remitente,
                        msg_id_original=msg_id_original,
                        youchat_profile_headers=headers_youchat,
                        asunto_original=asunto_original
                    )

                    if exito:
                        self.processed_emails.add(email_id)
                        self.total_processed += 1
                        logger.info("🎉 Respuesta #%d enviada exitosamente a: %s", self.total_processed, email_remitente)
                    else:
                        logger.error("❌ Falló el envío de la respuesta a: %s", email_remitente)

                except Exception as e:
                    logger.error("❌ Error procesando email ID %s: %s", email_id, str(e))
                    logger.error("🔍 Traceback: %s", traceback.format_exc())
                    continue

        except Exception as e:
            logger.error("❌ Error general procesando emails: %s", str(e))
            logger.error("🔍 Traceback: %s", traceback.format_exc())
            # Forzar reconexión en el próximo ciclo
            self.cerrar_conexion_imap()

    def run_bot(self):
        """Ejecuta el bot en un bucle continuo con manejo mejorado de errores"""
        self.is_running = True
        logger.info("🚀 Bot YouChat INICIADO - VERSIÓN CON CONEXIÓN ROBUSTA")
        logger.info("⏰ Intervalo: %d segundos", CHECK_INTERVAL)
        logger.info("📧 Cuenta Gmail: %s", EMAIL_ACCOUNT)

        consecutive_errors = 0
        max_consecutive_errors = 5

        while self.is_running:
            try:
                self.last_check = datetime.now()
                logger.info("🔍 Revisando nuevos emails - %s", self.last_check.strftime('%H:%M:%S'))

                self.procesar_emails_no_leidos()
                
                # Reset error counter on successful iteration
                consecutive_errors = 0
                time.sleep(CHECK_INTERVAL)

            except Exception as e:
                consecutive_errors += 1
                logger.error("💥 Error #%d en el bucle principal: %s", consecutive_errors, str(e))
                logger.error("🔍 Traceback: %s", traceback.format_exc())
                
                if consecutive_errors >= max_consecutive_errors:
                    logger.error("🛑 Demasiados errores consecutivos, reiniciando conexiones...")
                    self.cerrar_conexion_imap()
                    consecutive_errors = 0
                    time.sleep(10)  # Esperar más antes de reintentar
                else:
                    time.sleep(CHECK_INTERVAL)

        logger.info("🛑 Bot YouChat detenido")
        self.cerrar_conexion_imap()

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
        "service": "YouChat Bot - Conexión Robusta",
        "version": "2.2",
        "features": [
            "Conexión IMAP persistente",
            "Reconexión automática", 
            "Manejo robusto de errores",
            "Logging detallado"
        ],
        "interval": f"{CHECK_INTERVAL} segundos",
        "email_account": EMAIL_ACCOUNT,
        "last_check": youchat_bot.last_check.isoformat() if youchat_bot.last_check else None,
        "total_processed": youchat_bot.total_processed,
        "is_running": youchat_bot.is_running,
        "imap_connected": youchat_bot.imap_connection is not None
    })

@app.route('/health')
def health():
    return jsonify({
        "status": "healthy", 
        "timestamp": datetime.now().isoformat(),
        "bot_running": youchat_bot.is_running,
        "imap_connected": youchat_bot.imap_connection is not None,
        "memory_usage": f"{len(youchat_bot.processed_emails)} emails procesados"
    })

@app.route('/start')
def start_bot():
    global bot_thread

    if youchat_bot.is_running:
        return jsonify({
            "status": "already_running", 
            "message": "El bot ya está en ejecución",
            "total_processed": youchat_bot.total_processed
        })

    youchat_bot.is_running = True
    bot_thread = threading.Thread(target=youchat_bot.run_bot, daemon=True)
    bot_thread.start()

    return jsonify({
        "status": "started", 
        "message": "Bot iniciado correctamente",
        "features": "Conexión robusta IMAP activada"
    })

@app.route('/stop')
def stop_bot():
    youchat_bot.is_running = False
    youchat_bot.cerrar_conexion_imap()
    return jsonify({
        "status": "stopped", 
        "message": "Bot detenido",
        "final_stats": {
            "total_processed": youchat_bot.total_processed,
            "last_check": youchat_bot.last_check.isoformat() if youchat_bot.last_check else None
        }
    })

@app.route('/status')
def status():
    return jsonify({
        "is_running": youchat_bot.is_running,
        "last_check": youchat_bot.last_check.isoformat() if youchat_bot.last_check else None,
        "total_processed": youchat_bot.total_processed,
        "check_interval": CHECK_INTERVAL,
        "processed_emails_count": len(youchat_bot.processed_emails),
        "imap_connected": youchat_bot.imap_connection is not None
    })

# =============================================================================
# INICIALIZACIÓN AUTOMÁTICA MEJORADA
# =============================================================================

def inicializar_bot():
    """Inicializa el bot automáticamente al cargar la aplicación"""
    global bot_thread

    logger.info("🔧 Iniciando bot automáticamente...")
    logger.info("🆕 VERSIÓN 2.2 - LOGGING DETALLADO Y CONEXIÓN ROBUSTA")
    youchat_bot.is_running = True
    bot_thread = threading.Thread(target=youchat_bot.run_bot, daemon=True)
    bot_thread.start()
    logger.info("🎉 Bot iniciado y listo para recibir mensajes")
    logger.info("📋 Características activadas:")
    logger.info("   ✅ Conexión IMAP persistente")
    logger.info("   ✅ Reconexión automática")
    logger.info("   ✅ Manejo robusto de errores")
    logger.info("   ✅ Logging detallado paso a paso")

# Iniciar el bot cuando se carga la aplicación
inicializar_bot()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    logger.info("🌐 Iniciando servidor web en puerto: %d", port)
    app.run(host='0.0.0.0', port=port, debug=False)