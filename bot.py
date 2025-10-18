import imaplib
import email
from email.header import decode_header
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

# Configuración - USA VARIABLES DE ENTORNO PARA SEGURIDAD
EMAIL = os.getenv('EMAIL', 'videodown797@gmail.com')
PASSWORD = os.getenv('eflpirtnopeilbjy')  # Obligatorio como variable de entorno
IMAP_SERVER = "imap.gmail.com"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

def check_and_reply():
    """
    Revisa la bandeja de entrada y responde automáticamente a nuevos correos
    """
    try:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Revisando bandeja de entrada...")
        
        # Conectar al servidor IMAP
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL, PASSWORD)
        mail.select("inbox")

        # Buscar correos no leídos
        status, messages = mail.search(None, 'UNSEEN')
        email_ids = messages[0].split()

        if not email_ids:
            print("No hay nuevos correos")
            mail.close()
            mail.logout()
            return

        print(f"Encontrados {len(email_ids)} nuevo(s) correo(s)")

        for e_id in email_ids:
            try:
                # Obtener el correo
                status, msg_data = mail.fetch(e_id, '(RFC822)')
                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)

                # Decodificar información del remitente y asunto
                subject = "Sin asunto"
                if msg["Subject"]:
                    subject, encoding = decode_header(msg["Subject"])[0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(encoding if encoding else "utf-8")
                
                from_ = "Desconocido"
                if msg.get("From"):
                    from_, encoding = decode_header(msg.get("From"))[0]
                    if isinstance(from_, bytes):
                        from_ = from_.decode(encoding if encoding else "utf-8")

                # Extraer la dirección de correo del remitente
                sender_email = from_
                if "<" in from_ and ">" in from_:
                    sender_email = from_.split("<")[1].split(">")[0]
                elif " " in from_:
                    sender_email = from_.split()[-1]

                sender_email = sender_email.strip("<>").strip()

                print(f"📨 Nuevo correo de: {sender_email}")
                print(f"   Asunto: {subject}")

                # Enviar respuesta automática
                send_auto_reply(sender_email, subject)

                # Marcar como leído (opcional)
                mail.store(e_id, '+FLAGS', '\\Seen')
                print(f"✅ Respuesta enviada a: {sender_email}")

            except Exception as e:
                print(f"❌ Error procesando correo {e_id}: {str(e)}")
                continue

        mail.close()
        mail.logout()

    except Exception as e:
        print(f"🚨 Error general: {str(e)}")

def send_auto_reply(to_email, original_subject):
    """
    Envía una respuesta automática
    """
    try:
        # Crear el mensaje de respuesta
        reply = MIMEMultipart()
        reply["From"] = EMAIL
        reply["To"] = to_email
        reply["Subject"] = "Re: " + original_subject

        # Cuerpo del mensaje
        body = """
        ¡Hola!

        Gracias por tu mensaje. Este es un saludo automático.

        He recibido tu correo y lo revisaré lo antes posible.

        ¡Que tengas un excelente día!

        Saludos cordiales,
        Bot Automático
        """
        
        reply.attach(MIMEText(body.strip(), "plain"))

        # Enviar el correo
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL, PASSWORD)
        server.sendmail(EMAIL, to_email, reply.as_string())
        server.quit()
        
        return True
        
    except Exception as e:
        print(f"❌ Error enviando respuesta: {str(e)}")
        return False

def main():
    """
    Función principal con bucle infinito
    """
    # Verificar credenciales
    if not PASSWORD:
        print("🚨 ERROR: La variable de entorno 'EMAIL_PASSWORD' no está configurada")
        print("Por favor, configura tu contraseña de aplicación en las variables de entorno de Render")
        return
    
    print("=" * 50)
    print("🤖 BOT DE CORREO INICIADO")
    print(f"📧 Cuenta: {EMAIL}")
    print("⏰ Revisando cada 3 segundos...")
    print("=" * 50)
    
    # Bucle principal
    while True:
        try:
            check_and_reply()
        except KeyboardInterrupt:
            print("\n🛑 Bot detenido por el usuario")
            break
        except Exception as e:
            print(f"🚨 Error en el bucle principal: {str(e)}")
        
        # Esperar 3 segundos antes de la siguiente revisión
        time.sleep(3)

if __name__ == "__main__":
    main()