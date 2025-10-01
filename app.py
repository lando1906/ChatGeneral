import socketio
import eventlet
import eventlet.wsgi
import yt_dlp
import os
import threading
import time
import re
import urllib.parse
import random
import string
from datetime import datetime, timedelta

# Configuraciones actualizadas para yt-dlp
ydl_opts_video = {
    'format': 'best[height<=720]/best[height<=480]/best/bestvideo+bestaudio',
    'outtmpl': 'downloads/%(title)s.%(ext)s',
    'cookies': 'cookies.txt',
    'merge_output_format': 'mp4',  # Forzar formato de salida
}

ydl_opts_audio = {
    'format': 'bestaudio/best',
    'outtmpl': 'downloads/%(title)s.%(ext)s',
    'cookies': 'cookies.txt',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
}

sio = socketio.Server(cors_allowed_origins='*')
app = socketio.WSGIApp(sio)

# Asegurar que existe el directorio de descargas
os.makedirs('downloads', exist_ok=True)

# Diccionario para trackear archivos y su tiempo de expiración
file_expirations = {}

def cleanup_expired_files():
    """Elimina archivos expirados cada minuto"""
    while True:
        try:
            current_time = datetime.now()
            expired_files = []

            for filename, expiry_time in list(file_expirations.items()):
                if current_time >= expiry_time:
                    expired_files.append(filename)

            for filename in expired_files:
                file_path = os.path.join('downloads', filename)
                if os.path.exists(file_path):
                    os.remove(file_path)
                    print(f"🗑️ Archivo eliminado: {filename}")
                del file_expirations[filename]

        except Exception as e:
            print(f"❌ Error en cleanup: {e}")

        time.sleep(60)  # Revisar cada minuto

# Iniciar hilo de limpieza en segundo plano
cleanup_thread = threading.Thread(target=cleanup_expired_files, daemon=True)
cleanup_thread.start()

def generar_nombre_aleatorio(longitud=12):
    """Genera un nombre de archivo aleatorio"""
    caracteres = string.ascii_letters + string.digits
    return ''.join(random.choice(caracteres) for _ in range(longitud))

def sanitize_filename(filename):
    """Reemplaza el nombre original por uno aleatorio manteniendo la extensión"""
    nombre_base, extension = os.path.splitext(filename)
    nuevo_nombre = generar_nombre_aleatorio(12) + extension.lower()
    
    downloads_path = 'downloads/'
    while os.path.exists(os.path.join(downloads_path, nuevo_nombre)):
        nuevo_nombre = generar_nombre_aleatorio(12) + extension.lower()
    
    return nuevo_nombre

@sio.event
def connect(sid, environ):
    print('✅ Cliente conectado:', sid)

@sio.event
def disconnect(sid):
    print('❌ Cliente desconectado:', sid)

@sio.event
def start_download(sid, data):
    url = data['url']
    download_type = data.get('download_type', 'video')  # 'video' o 'audio'
    download_id = data.get('download_id', 'default_id')

    try:
        sio.emit('progress_update', {
            'download_id': download_id, 
            'status': '🔄 Conectando...',
            'type': download_type
        })

        def progress_hook(d):
            if d['status'] == 'downloading':
                sio.emit('progress_update', {
                    'download_id': download_id, 
                    'status': '📥 Descargando...',
                    'type': download_type
                })
            elif d['status'] == 'finished':
                # Obtener y sanitizar el nombre del archivo
                original_filename = os.path.basename(d['filename'])
                sanitized_filename = sanitize_filename(original_filename)
                
                # Renombrar el archivo
                original_path = d['filename']
                new_path = os.path.join('downloads', sanitized_filename)
                
                if original_path != new_path and os.path.exists(original_path):
                    os.rename(original_path, new_path)
                    print(f"📝 Archivo renombrado: {original_filename} -> {sanitized_filename}")
                
                # Registrar archivo para eliminación en 15 minutos
                expiry_time = datetime.now() + timedelta(minutes=15)
                file_expirations[sanitized_filename] = expiry_time

                download_url = f"/downloads/{urllib.parse.quote(sanitized_filename)}"
                
                sio.emit('progress_update', {
                    'download_id': download_id, 
                    'status': '✅ Completo',
                    'filename': sanitized_filename,
                    'download_url': download_url,
                    'expires_at': expiry_time.isoformat(),
                    'type': download_type
                })
                print(f"✅ Descarga completada: {sanitized_filename}")
                print(f"🔗 Enlace de descarga: {download_url}")

        # Seleccionar configuración según el tipo de descarga
        if download_type == 'audio':
            ydl_opts = ydl_opts_audio.copy()
        else:
            ydl_opts = ydl_opts_video.copy()
            
        ydl_opts_with_progress = {**ydl_opts, 'progress_hooks': [progress_hook]}

        with yt_dlp.YoutubeDL(ydl_opts_with_progress) as ydl:
            sio.emit('progress_update', {
                'download_id': download_id, 
                'status': '🚀 Iniciando...',
                'type': download_type
            })
            ydl.download([url])

    except Exception as e:
        error_message = f'Error: {str(e)}'
        print(f"❌ {error_message}")
        sio.emit('progress_update', {
            'download_id': download_id, 
            'status': f'❌ {error_message}',
            'type': download_type
        })

def serve_application(environ, start_response):
    """Middleware WSGI para manejar archivos estáticos y la aplicación Socket.IO"""
    path = environ['PATH_INFO']
    
    if path.startswith('/downloads/'):
        filename_encoded = path[11:]
        filename = urllib.parse.unquote(filename_encoded)
        
        file_path = os.path.join('downloads', filename)
        
        print(f"📥 Solicitud de descarga directa: {filename}")
        
        if os.path.exists(file_path) and os.path.isfile(file_path):
            if filename in file_expirations and datetime.now() < file_expirations[filename]:
                headers = [
                    ('Content-Type', 'application/octet-stream'),
                    ('Content-Disposition', f'attachment; filename="{filename}"'),
                    ('Cache-Control', 'no-cache, must-revalidate'),
                    ('Pragma', 'no-cache'),
                    ('Expires', '0'),
                    ('Content-Length', str(os.path.getsize(file_path)))
                ]
                start_response('200 OK', headers)
                print(f"✅ Sirviendo archivo para descarga: {filename}")
                
                with open(file_path, 'rb') as f:
                    return [f.read()]
            else:
                print(f"⏰ Archivo expirado: {filename}")
                start_response('410 Gone', [('Content-Type', 'text/plain')])
                return [b'Archivo expirado o no disponible']
        else:
            print(f"❌ Archivo no encontrado: {filename}")
            start_response('404 Not Found', [('Content-Type', 'text/plain')])
            return [b'Archivo no encontrado']
    
    if path == '/' or path == '':
        try:
            with open('static/index.html', 'rb') as f:
                html_content = f.read()
            start_response('200 OK', [('Content-Type', 'text/html')])
            return [html_content]
        except FileNotFoundError:
            start_response('404 Not Found', [('Content-Type', 'text/plain')])
            return [b'Archivo HTML no encontrado']
    
    return app(environ, start_response)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    print(f"🚀 Servidor ejecutándose en 0.0.0.0:{port}")
    print(f"📁 Directorio actual: {os.getcwd()}")
    print(f"⏰ Los archivos se eliminarán automáticamente después de 15 minutos")
    print(f"🎯 Sistema de estados: Conectando → Iniciando → Descargando → Completo")
    print(f"🔧 Funcionalidades: Descarga de video/audio + cookies para YouTube")
    
    # Verificar si existe el archivo de cookies
    if os.path.exists('cookies.txt'):
        print(f"✅ Archivo de cookies encontrado")
    else:
        print(f"⚠️  Archivo de cookies no encontrado - algunas descargas pueden fallar")
    
    eventlet.wsgi.server(eventlet.listen(('0.0.0.0', port)), serve_application)