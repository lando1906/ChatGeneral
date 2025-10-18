import imaplib
import email
from email.header import decode_header
import time
import smtplib
from email.mime.text import MimeText
from email.mime.multipart import MimeMultipart

# Configuración - RELLENA ESTOS DATOS
EMAIL = "videodown797@gmail.com"
PASSWORD = "eflpirtnopeilbjy"
IMAP_SERVER = "imap.gmail.com"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

def check_and_reply():
    try:
        # Conectar y leer el correo
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL, PASSWORD)
        mail.select("inbox")

        status, messages = mail.search(None, 'UNSEEN')  # Buscar correos no leídos
        email_ids = messages[0].split()

        for e_id in email_ids:
            # Marcar como leído para no procesarlo otra vez
            status, msg_data = mail.fetch(e_id, '(RFC822)')
            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            # Obtener información del remitente y asunto
            subject, encoding = decode_header(msg["Subject"])[0]
            if isinstance(subject, bytes):
                subject = subject.decode(encoding if encoding else "utf-8")
            from_, encoding = decode_header(msg.get("From"))[0]
            if isinstance(from_, bytes):
                from_ = from_.decode(encoding if encoding else "utf-8")

            # Extraer la dirección de correo del remitente
            sender_email = from_.split()[-1] if " " in from_ else from_
            sender_email = sender_email.strip("<>")

            print(f"Procesando nuevo correo de: {sender_email} - Asunto: {subject}")

            # --- Enviar Respuesta ---
            reply = MimeMultipart()
            reply["From"] = EMAIL
            reply["To"] = sender_email
            reply["Subject"] = "Re: " + subject

            body = "Hola, gracias por tu mensaje. Este es un saludo automático."
            reply.attach(MimeText(body, "plain"))

            # Enviar el correo
            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
            server.starttls()
            server.login(EMAIL, PASSWORD)
            server.sendmail(EMAIL, sender_email, reply.as_string())
            server.quit()
            print(f"Respuesta enviada a: {sender_email}")

        mail.close()
        mail.logout()

    except Exception as e:
        print(f"Ocurrió un error: {e}")

# Bucle principal - Este es el que correrá en el Background Worker
if __name__ == "__main__":
    print("El bot de correo ha comenzado a ejecutarse...")
    while True:
        check_and_reply()
        time.sleep(3)  # Espera 3 segundos antes de la siguiente revisión