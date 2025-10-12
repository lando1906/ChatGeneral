import os
import time
import imaplib
import email
from email.message import EmailMessage
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
# CONFIGURACIÓN PARA GMAIL (ACCESIBLE DESDE RENDER)
# =============================================================================

# 🔐 CONFIGURA TUS CREDENCIALES DE GMAIL AQUÍ
EMAIL_ACCOUNT = "videodown797@gmail.com"  # 📧 Tu correo Gmail
EMAIL_PASSWORD = "nlhoedrevnlihgdo"    # 🔑 Tu contraseña de aplicación

# Configuración servidores Gmail
IMAP_SERVER = "imap.gmail.com"
IMAP_PORT = 993
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

# Usar el mismo correo para SMTP
SMTP_ACCOUNT = EMAIL_ACCOUNT
SMTP_PASSWORD = EMAIL_PASSWORD

# ⚙️ Configuración del bot
CHECK_INTERVAL = 3

# =============================================================================
# FUNCIONES DEL BOT YOUCHAT
# =============================================================================

class YouChatBot:
    def __init__(self):
        self.is_running = False
        self.last_check = None
        self.processed_emails = set()
        self.total_processed = 0
    
    def extraer_headers_youchat(self, mensaje_email):
        """Extrae TODOS los headers específicos de YouChat del mensaje entrante"""
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
            logger.info(f"✅ Conexión IMAP exitosa a {IMAP_SERVER}")
            return mail
        except Exception as e:
            logger.error(f"❌ Error conexión IMAP: {str(e)}")
            return None

    def enviar_respuesta_youchat(self, destinatario, msg_id_original=None, youchat_profile_headers=None):
        """Envía una respuesta con los headers EXACTOS que requiere YouChat"""
        try:
            msg = EmailMessage()
            
            # 1. HEADERS BÁSICOS
            msg["From"] = SMTP_ACCOUNT
            msg["To"] = destinatario
            msg["Subject"] = "YouChat"
            
            # 2. HEADERS DE YOUCHAT GENERALES
            if youchat_profile_headers and isinstance(youchat_profile_headers, dict):
                for key, value in youchat_profile_headers.items():
                    if value and key not in ['Msg_id', 'Chat-Version', 'Pd', 'Sender-Alias', 'From-Alias', 'Message-ID']:
                        msg[key] = str(value)
            
            # 3. HEADERS DE THREADING (CRÍTICOS)
            # NO agregar Message-ID manualmente - Python lo genera automáticamente
            
            if msg_id_original:
                clean_message_id = msg_id_original
                if not (msg_id_original.startswith('<') and msg_id_original.endswith('>')):
                    clean_message_id = f"<{msg_id_original}>"
                
                msg['In-Reply-To'] = clean_message_id
                msg['References'] = clean_message_id
            
            # 4. HEADERS ESPECÍFICOS DEL BOT YOUCHAT
            msg['Msg_id'] = f"auto-reply-{int(time.time()*1000)}"
            
            chat_version = '1.1'
            if youchat_profile_headers and 'Chat-Version' in youchat_profile_headers:
                chat_version = youchat_profile_headers['Chat-Version']
            msg['Chat-Version'] = chat_version
            
            pd_value = None
            if youchat_profile_headers and 'Pd' in youchat_profile_headers:
                pd_value = youchat_profile_headers['Pd']
            if pd_value:
                msg['Pd'] = str(pd_value).strip()
            
            # 5. HEADERS ESTÁNDAR
            msg['MIME-Version'] = '1.0'
            
            # 6. CONTENIDO DEL MENSAJE
            mensaje_respuesta = "¡Hola! Soy un bot en desarrollo. Pronto podré descargar tus Reels de Instagram."
            msg.set_content(mensaje_respuesta)
            
            # ENVÍO CON SMTP GMAIL
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as servidor:
                servidor.starttls()
                servidor.login(SMTP_ACCOUNT, SMTP_PASSWORD)
                servidor.send_message(msg)
            
            logger.info("✅ Respuesta enviada a: %s", destinatario)
            return True
            
        except Exception as e:
            logger.error("❌ Error enviando respuesta: %s", str(e))
            return False

    def procesar_emails_no_leidos(self):
        """Función principal que revisa emails no leídos y responde automáticamente"""
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
                    
                    exito = self.enviar_respuesta_youchat(
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
        logger.info("🚀 Bot YouChat INICIADO")
        logger.info("⏰ Intervalo: %d segundos", CHECK_INTERVAL)
        logger.info("📧 Cuenta Gmail: %s", EMAIL_ACCOUNT)
        logger.info("🌐 Servidor IMAP: %s:%d", IMAP_SERVER, IMAP_PORT)
        logger.info("🌐 Servidor SMTP: %s:%d", SMTP_SERVER, SMTP_PORT)
        
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
        "service": "YouChat Bot - Gmail",
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

@app.route('/test')
def test_bot():
    """Endpoint para probar el bot manualmente"""
    try:
        # Simular procesamiento de un email
        test_email = "miguelorlandos@nauta.cu"
        logger.info("🧪 Probando envío a: %s", test_email)
        
        exito = youchat_bot.enviar_respuesta_youchat(test_email)
        
        return jsonify({
            "status": "test_completed",
            "success": exito,
            "test_email": test_email
        })
    except Exception as e:
        return jsonify({"status": "test_failed", "error": str(e)})

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