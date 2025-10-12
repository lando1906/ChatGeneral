import os
import time
import imaplib
import email
import smtplib
from flask import Flask, jsonify
import threading
import logging
from datetime import datetime

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
# FUNCIONES DEL BOT YOUCHAT - VERSIÓN RAW MEJORADA
# =============================================================================

class YouChatBot:
    def __init__(self):
        self.is_running = False
        self.last_check = None
        self.processed_emails = set()
        self.total_processed = 0

    def extraer_headers_youchat(self, mensaje_email):
        """Extrae headers específicos de YouChat de manera más completa"""
        headers_youchat = {}
        
        # Headers específicos de YouChat a preservar
        headers_especificos = [
            'Message-ID', 'Msg_id', 'Chat-Version', 'Pd', 
            'Sender-Alias', 'From-Alias', 'Thread-ID', 'User-ID',
            'X-YouChat-Session', 'X-YouChat-Platform', 'X-YouChat-Device',
            'Chat-ID', 'Session-ID', 'X-Chat-Signature', 'X-YouChat-Version',
            'X-YouChat-Build', 'X-YouChat-Environment'
        ]
        
        for header, valor in mensaje_email.items():
            header_lower = header.lower()
            # Capturar headers que contengan palabras clave de YouChat
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

    def conectar_imap(self):
        """Conexión IMAP para Gmail"""
        try:
            mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
            mail.login(EMAIL_ACCOUNT, EMAIL_PASSWORD)
            logger.info("✅ Conexión IMAP establecida")
            return mail
        except Exception as e:
            logger.error(f"❌ Error conexión IMAP: {str(e)}")
            return None

    def construir_mensaje_raw_youchat(self, destinatario, msg_id_original=None, youchat_profile_headers=None, asunto_original=None):
        """Construye el mensaje en formato RAW optimizado para YouChat"""
        try:
            # 1. Headers de YouChat Generales (preservar la mayoría)
            headers_string = ""
            if youchat_profile_headers and isinstance(youchat_profile_headers, dict):
                for key, value in youchat_profile_headers.items():
                    if value and key not in ['Msg_id', 'Message-ID']:  # Solo excluir los que regeneramos
                        headers_string += f"{key}: {value}\r\n"

            # 2. Headers de Threading (mejorado)
            domain = SMTP_ACCOUNT.split('@')[1]
            nuevo_msg_id = f"<auto-reply-{int(time.time()*1000)}@{domain}>"
            headers_string += f"Message-ID: {nuevo_msg_id}\r\n"

            if msg_id_original:
                clean_message_id = msg_id_original
                if not (msg_id_original.startswith('<') and msg_id_original.endswith('>')):
                    clean_message_id = f"<{msg_id_original}>"
                
                headers_string += f"In-Reply-To: {clean_message_id}\r\n"
                headers_string += f"References: {clean_message_id}\r\n"

            # 3. Headers del Bot (actualizados)
            headers_string += f"Msg_id: auto-reply-{int(time.time()*1000)}\r\n"
            
            # Preservar Chat-Version del mensaje original o usar default
            chat_version = youchat_profile_headers.get('Chat-Version', '1.1') if youchat_profile_headers else '1.1'
            headers_string += f"Chat-Version: {chat_version}\r\n"
            
            # Preservar Pd si existe
            pd_value = youchat_profile_headers.get('Pd') if youchat_profile_headers else None
            if pd_value:
                headers_string += f"Pd: {str(pd_value).strip()}\r\n"
            
            # 4. Headers Estándar (mejorados)
            headers_string += "MIME-Version: 1.0\r\n"
            headers_string += 'Content-Type: text/plain; charset="UTF-8"\r\n'
            headers_string += 'Content-Transfer-Encoding: 8bit\r\n'
            
            # 5. Asunto inteligente
            asunto = "YouChat"
            if asunto_original:
                if not asunto_original.lower().startswith('re:'):
                    asunto = f"Re: {asunto_original}"
                else:
                    asunto = asunto_original

            # 6. Construcción FINAL del mensaje RAW
            mensaje_texto = "¡Hola! Soy un bot en desarrollo. Pronto podré descargar tus Reels de Instagram."

            mail_raw = (
                f"From: {SMTP_ACCOUNT}\r\n" +
                f"To: {destinatario}\r\n" +
                f"Subject: {asunto}\r\n" +
                headers_string +
                f"\r\n" +
                f"{mensaje_texto}"
            )

            logger.debug("📧 Mensaje RAW construido para: %s", destinatario)
            return mail_raw.encode('utf-8')

        except Exception as e:
            logger.error(f"❌ Error construyendo mensaje RAW: {str(e)}")
            return None

    def enviar_respuesta_raw(self, destinatario, msg_id_original=None, youchat_profile_headers=None, asunto_original=None):
        """Envía respuesta usando formato RAW mejorado"""
        try:
            # Construir mensaje RAW
            mensaje_raw = self.construir_mensaje_raw_youchat(
                destinatario, 
                msg_id_original, 
                youchat_profile_headers,
                asunto_original
            )

            if not mensaje_raw:
                logger.error("❌ No se pudo construir el mensaje RAW")
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
        """Función principal mejorada para procesar emails"""
        try:
            mail = self.conectar_imap()
            if not mail:
                return

            mail.select("inbox")

            estado, mensajes = mail.search(None, "UNSEEN")
            if estado != "OK":
                logger.info("📭 No hay emails nuevos")
                return

            ids_emails = mensajes[0].split()
            if not ids_emails:
                return

            logger.info("📥 %d nuevo(s) email(s) para procesar", len(ids_emails))

            for id_email in ids_emails:
                try:
                    email_id = id_email.decode()
                    if email_id in self.processed_emails:
                        logger.debug("⏭️ Email ya procesado: %s", email_id)
                        continue

                    estado, datos_msg = mail.fetch(id_email, "(RFC822)")
                    if estado != "OK":
                        logger.error("❌ Error obteniendo email: %s", email_id)
                        continue

                    email_crudo = datos_msg[0][1]
                    mensaje = email.message_from_bytes(email_crudo)

                    # Extraer información del remitente
                    remitente = mensaje["From"]
                    asunto_original = mensaje.get("Subject", "")
                    
                    email_remitente = self.extraer_email_remitente(remitente)
                    if not email_remitente:
                        logger.error("❌ No se pudo extraer email del remitente: %s", remitente)
                        continue

                    logger.info("👤 Procesando mensaje de: %s - Asunto: %s", email_remitente, asunto_original)

                    # Extraer headers de YouChat
                    headers_youchat = self.extraer_headers_youchat(mensaje)
                    msg_id_original = mensaje.get('Message-ID') or headers_youchat.get('Message-ID')

                    if msg_id_original:
                        logger.info("🔗 Message-ID del mensaje original: %s", msg_id_original)
                    else:
                        logger.warning("⚠️ No se encontró Message-ID en el mensaje original")

                    # Log de headers encontrados
                    if headers_youchat:
                        logger.info("📋 Headers de YouChat encontrados: %s", list(headers_youchat.keys()))

                    # Enviar respuesta usando el método RAW mejorado
                    exito = self.enviar_respuesta_raw(
                        email_remitente,
                        msg_id_original=msg_id_original,
                        youchat_profile_headers=headers_youchat,
                        asunto_original=asunto_original
                    )

                    if exito:
                        self.processed_emails.add(email_id)
                        self.total_processed += 1
                        logger.info("💬 Respuesta #%d enviada exitosamente a: %s", self.total_processed, email_remitente)
                    else:
                        logger.error("❌ Falló el envío de la respuesta a: %s", email_remitente)

                except Exception as e:
                    logger.error("❌ Error procesando email ID %s: %s", email_id, str(e))
                    continue

        except Exception as e:
            logger.error("❌ Error procesando emails: %s", str(e))
        finally:
            try:
                mail.close()
                mail.logout()
                logger.debug("🔒 Conexión IMAP cerrada")
            except Exception as e:
                logger.error("❌ Error cerrando conexión IMAP: %s", str(e))

    def run_bot(self):
        """Ejecuta el bot en un bucle continuo"""
        self.is_running = True
        logger.info("🚀 Bot YouChat INICIADO - VERSIÓN RAW MEJORADA")
        logger.info("⏰ Intervalo: %d segundos", CHECK_INTERVAL)
        logger.info("📧 Cuenta Gmail: %s", EMAIL_ACCOUNT)
        logger.info("🔧 Configuración de headers optimizada")

        while self.is_running:
            try:
                self.last_check = datetime.now()
                logger.info("🔍 Revisando nuevos emails - %s", self.last_check.strftime('%H:%M:%S'))

                self.procesar_emails_no_leidos()

                time.sleep(CHECK_INTERVAL)

            except Exception as e:
                logger.error("💥 Error en el bucle principal: %s", str(e))
                time.sleep(CHECK_INTERVAL)

        logger.info("🛑 Bot YouChat detenido")

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
        "service": "YouChat Bot - RAW Version Mejorada",
        "version": "2.0",
        "features": [
            "Headers YouChat optimizados",
            "Threading mejorado", 
            "Asuntos inteligentes",
            "Logging detallado"
        ],
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
        "bot_running": youchat_bot.is_running,
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
        "features": "Headers YouChat optimizados activados"
    })

@app.route('/stop')
def stop_bot():
    youchat_bot.is_running = False
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
        "processed_emails_count": len(youchat_bot.processed_emails)
    })

@app.route('/stats')
def stats():
    """Endpoint adicional para estadísticas detalladas"""
    return jsonify({
        "total_responses_sent": youchat_bot.total_processed,
        "current_session_emails": len(youchat_bot.processed_emails),
        "bot_uptime": youchat_bot.last_check.isoformat() if youchat_bot.last_check else "N/A",
        "system_status": "active" if youchat_bot.is_running else "inactive",
        "version": "2.0 - Headers Optimizados"
    })

# =============================================================================
# INICIALIZACIÓN AUTOMÁTICA
# =============================================================================

def inicializar_bot():
    """Inicializa el bot automáticamente al cargar la aplicación"""
    global bot_thread

    logger.info("🔧 Iniciando bot automáticamente...")
    logger.info("🆕 VERSIÓN 2.0 - HEADERS YOUCHAT OPTIMIZADOS")
    youchat_bot.is_running = True
    bot_thread = threading.Thread(target=youchat_bot.run_bot, daemon=True)
    bot_thread.start()
    logger.info("🎉 Bot iniciado y listo para recibir mensajes")
    logger.info("📋 Características activadas:")
    logger.info("   ✅ Headers YouChat completos")
    logger.info("   ✅ Threading mejorado")
    logger.info("   ✅ Asuntos inteligentes")
    logger.info("   ✅ Logging detallado")

# Iniciar el bot cuando se carga la aplicación
inicializar_bot()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    logger.info("🌐 Iniciando servidor web en puerto: %d", port)
    app.run(host='0.0.0.0', port=port, debug=False)