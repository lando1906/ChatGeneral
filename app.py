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
import json

# Configuraciones actualizadas para yt-dlp
ydl_opts_video = {
    'format': 'best[height<=720]/best[height<=480]/best/bestvideo+bestaudio',
    'outtmpl': 'downloads/%(title)s.%(ext)s',
    'cookies': 'cookies.txt',
    'merge_output_format': 'mp4',
    'ignoreerrors': True,
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
    'ignoreerrors': True,
}

sio = socketio.Server(cors_allowed_origins='*', async_mode='eventlet')
app = socketio.WSGIApp(sio)

# Asegurar que existe el directorio de descargas
os.makedirs('downloads', exist_ok=True)

# Diccionarios para gestión de descargas
file_expirations = {}
active_downloads = {}
download_progress = {}

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

        time.sleep(60)

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

def get_ydl_opts_for_url(url, download_type):
    """Obtiene configuración optimizada según la URL"""
    if download_type == 'audio':
        base_opts = ydl_opts_audio.copy()
    else:
        base_opts = ydl_opts_video.copy()
    
    # Configuración específica para Pinterest
    if any(domain in url.lower() for domain in ['pinterest.', 'pin.it']):
        base_opts.update({
            'format': 'best',
            'ignoreerrors': True,
        })
    
    return base_opts

@sio.event
def connect(sid, environ):
    print('✅ Cliente conectado:', sid)

@sio.event
def disconnect(sid):
    print('❌ Cliente desconectado:', sid)
    # Limpiar descargas activas del cliente desconectado
    for download_id in list(active_downloads.keys()):
        if active_downloads[download_id].get('sid') == sid:
            del active_downloads[download_id]

@sio.event
def start_download(sid, data):
    url = data['url']
    download_type = data.get('download_type', 'video')
    download_id = data.get('download_id', 'default_id')

    # Si ya existe una descarga con este ID, no hacer nada
    if download_id in active_downloads:
        return

    try:
        sio.emit('progress_update', {
            'download_id': download_id, 
            'status': 'Procesando',
            'type': download_type,
            'progress': 0
        }, room=sid)

        def progress_hook(d):
            if d['status'] == 'downloading':
                # Calcular progreso aproximado
                progress = 0
                if '_percent_str' in d and d['_percent_str']:
                    percent_str = d['_percent_str'].replace('%', '')
                    try:
                        progress = float(percent_str)
                    except:
                        progress = 50  # Valor por defecto si no se puede parsear
                
                download_progress[download_id] = progress
                
                sio.emit('progress_update', {
                    'download_id': download_id, 
                    'status': 'Descargando',
                    'type': download_type,
                    'progress': progress
                }, room=sid)
                
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

                # Registrar archivo para eliminación en 5 minutos (reducido)
                expiry_time = datetime.now() + timedelta(minutes=5)
                file_expirations[sanitized_filename] = expiry_time

                download_url = f"/downloads/{urllib.parse.quote(sanitized_filename)}"

                sio.emit('progress_update', {
                    'download_id': download_id, 
                    'status': 'Completado',
                    'filename': sanitized_filename,
                    'download_url': download_url,
                    'expires_at': expiry_time.isoformat(),
                    'type': download_type,
                    'progress': 100
                }, room=sid)
                
                # Limpiar de descargas activas
                if download_id in active_downloads:
                    del active_downloads[download_id]
                if download_id in download_progress:
                    del download_progress[download_id]
                    
                print(f"✅ Descarga completada: {sanitized_filename}")

        # Obtener configuración optimizada según la URL
        ydl_opts = get_ydl_opts_for_url(url, download_type)
        ydl_opts_with_progress = {**ydl_opts, 'progress_hooks': [progress_hook]}

        # Registrar descarga activa
        active_downloads[download_id] = {
            'sid': sid,
            'url': url,
            'type': download_type,
            'start_time': datetime.now()
        }

        with yt_dlp.YoutubeDL(ydl_opts_with_progress) as ydl:
            sio.emit('progress_update', {
                'download_id': download_id, 
                'status': 'Procesando',
                'type': download_type,
                'progress': 0
            }, room=sid)
            ydl.download([url])

    except Exception as e:
        error_str = str(e)
        
        # Manejar errores específicos de Pinterest
        if 'pinterest' in url.lower() and 'format' in error_str.lower():
            error_message = 'Pinterest: Formato no disponible. Intenta con otro video.'
        elif 'pinterest' in url.lower():
            error_message = 'Pinterest: No se pudo descargar el video.'
        else:
            error_message = f'Error: {error_str}'
        
        print(f"❌ {error_message}")
        sio.emit('progress_update', {
            'download_id': download_id, 
            'status': f'Error: {error_message}',
            'type': download_type,
            'progress': 0
        }, room=sid)
        
        # Limpiar en caso de error
        if download_id in active_downloads:
            del active_downloads[download_id]

@sio.event
def cancel_download(sid, data):
    """Cancelar una descarga en progreso"""
    download_id = data.get('download_id')
    if download_id in active_downloads:
        # En una implementación real, aquí se interrumpiría el proceso yt-dlp
        # Por ahora, solo limpiamos el registro
        del active_downloads[download_id]
        if download_id in download_progress:
            del download_progress[download_id]
        
        sio.emit('progress_update', {
            'download_id': download_id,
            'status': 'Cancelado',
            'progress': 0
        }, room=sid)

def mark_file_for_immediate_removal(filename):
    """Marca un archivo para eliminación inmediata después de la descarga"""
    # Reducir tiempo de expiración a 1 minuto después de descargado
    expiry_time = datetime.now() + timedelta(minutes=1)
    file_expirations[filename] = expiry_time
    print(f"⏰ Archivo marcado para eliminación: {filename}")

def serve_application(environ, start_response):
    """Middleware WSGI para manejar archivos estáticos y la aplicación Socket.IO"""
    path = environ['PATH_INFO']

    if path.startswith('/downloads/'):
        filename_encoded = path[11:]
        filename = urllib.parse.unquote(filename_encoded)

        file_path = os.path.join('downloads', filename)

        print(f"📥 Solicitud de descarga directa: {filename}")

        if os.path.exists(file_path) and os.path.isfile(file_path):
            if filename in file_expirations:
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

                # Marcar para eliminación inmediata después de servir
                mark_file_for_immediate_removal(filename)

                def file_iterator(file_path):
                    with open(file_path, 'rb') as f:
                        while True:
                            data = f.read(4096)
                            if not data:
                                break
                            yield data

                return file_iterator(file_path)
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
    print(f"⏰ Los archivos se eliminarán automáticamente 1 minuto después de descargarse")
    print(f"🎯 Sistema de estados: Procesando → Descargando → Completado")
    print(f"🔧 Funcionalidades: Descarga de video/audio + Soporte Pinterest")

    if os.path.exists('cookies.txt'):
        print(f"✅ Archivo de cookies encontrado")
    else:
        print(f"⚠️  Archivo de cookies no encontrado")

    eventlet.wsgi.server(eventlet.listen(('0.0.0.0', port)), serve_application)