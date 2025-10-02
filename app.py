import socketio
import eventlet
import eventlet.wsgi
import yt_dlp
import os
import threading
import time
import urllib.parse
import random
import string
from datetime import datetime, timedelta

# Configuraciones base sin cookies
ydl_opts_base = {
    'format': 'best[height<=720]/best[height<=480]/best/bestvideo+bestaudio',
    'outtmpl': 'downloads/%(title)s.%(ext)s',
    'merge_output_format': 'mp4',
    'ignoreerrors': True,
    'quiet': True,
}

ydl_opts_video = ydl_opts_base.copy()
ydl_opts_audio = {
    'format': 'bestaudio/best',
    'outtmpl': 'downloads/%(title)s.%(ext)s',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
    'ignoreerrors': True,
    'quiet': True,
}

sio = socketio.Server(cors_allowed_origins='*', async_mode='eventlet')
app = socketio.WSGIApp(sio)

# Asegurar que existe el directorio de descargas
os.makedirs('downloads', exist_ok=True)

# Diccionarios para gestión de descargas
file_expirations = {}
active_downloads = {}
download_progress = {}

def check_cookies_validity():
    """Verifica si el archivo de cookies existe y es válido"""
    if not os.path.exists('cookies.txt'):
        print("❌ Archivo de cookies no encontrado")
        return False
    
    try:
        with open('cookies.txt', 'r', encoding='utf-8') as f:
            content = f.read().strip()
        
        # Verificar que no esté vacío
        if not content:
            print("⚠️  Archivo de cookies está vacío")
            return False
        
        # Verificar que tenga cookies válidas (no placeholders)
        if 'your_secure_3psid_here' in content or 'AFmmF2swRQIgYourLoginInfoHere' in content:
            print("⚠️  Archivo de cookies contiene placeholders (valores de ejemplo)")
            return False
        
        # Contar cookies válidas
        valid_cookies = 0
        for line in content.split('\n'):
            line = line.strip()
            if line and not line.startswith('#') and '\t' in line:
                parts = line.split('\t')
                if len(parts) >= 7:
                    # Verificar que el valor de la cookie no sea un placeholder
                    cookie_value = parts[6]
                    if cookie_value and not any(placeholder in cookie_value for placeholder in ['placeholder', 'your_', 'example']):
                        valid_cookies += 1
        
        print(f"✅ Cookies válidas detectadas: {valid_cookies}")
        return valid_cookies >= 3  # Mínimo 3 cookies válidas
        
    except Exception as e:
        print(f"❌ Error leyendo cookies: {e}")
        return False

def get_ydl_opts_with_cookies(base_opts, url):
    """Añade cookies a la configuración si están disponibles y son válidas"""
    opts = base_opts.copy()
    
    if check_cookies_validity():
        opts['cookiefile'] = 'cookies.txt'
        print(f"🔐 Usando cookies para: {url}")
    else:
        print(f"🔓 Modo sin cookies para: {url}")
        # Añadir opciones para contenido restringido sin cookies
        opts.update({
            'age_limit': 18,  # Intentar descargar contenido para adultos
        })
    
    # Configuración específica para Pinterest
    if any(domain in url.lower() for domain in ['pinterest.', 'pin.it']):
        opts.update({
            'format': 'best',
        })
    
    return opts

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

def sanitize_filename(filename):
    """Limpia el nombre de archivo de caracteres inválidos pero mantiene el nombre original"""
    # Remover caracteres inválidos para sistemas de archivos
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    
    # Limitar longitud del nombre (máximo 200 caracteres)
    if len(filename) > 200:
        name, ext = os.path.splitext(filename)
        filename = name[:200-len(ext)] + ext
    
    return filename

def get_unique_filename(original_filename):
    """Genera un nombre único si el archivo ya existe"""
    base_name, ext = os.path.splitext(original_filename)
    counter = 1
    new_filename = original_filename
    
    while os.path.exists(os.path.join('downloads', new_filename)):
        new_filename = f"{base_name}_{counter}{ext}"
        counter += 1
    
    return new_filename

@sio.event
def connect(sid, environ):
    print('✅ Cliente conectado:', sid)

@sio.event
def disconnect(sid):
    print('❌ Cliente desconectado:', sid)
    for download_id in list(active_downloads.keys()):
        if active_downloads[download_id].get('sid') == sid:
            del active_downloads[download_id]

@sio.event
def start_download(sid, data):
    url = data['url']
    download_type = data.get('download_type', 'video')
    download_id = data.get('download_id', 'default_id')

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
                progress = 0
                if '_percent_str' in d and d['_percent_str']:
                    percent_str = d['_percent_str'].replace('%', '')
                    try:
                        progress = float(percent_str)
                    except:
                        progress = 50
                
                download_progress[download_id] = progress
                
                sio.emit('progress_update', {
                    'download_id': download_id, 
                    'status': 'Descargando',
                    'type': download_type,
                    'progress': progress
                }, room=sid)
                
            elif d['status'] == 'finished':
                # Obtener el nombre original del archivo descargado
                original_filename = os.path.basename(d['filename'])
                
                # Sanitizar el nombre (remover caracteres inválidos)
                sanitized_filename = sanitize_filename(original_filename)
                
                # Verificar si el nombre ya existe y generar uno único si es necesario
                final_filename = get_unique_filename(sanitized_filename)
                
                # Renombrar el archivo si es necesario (por unicidad)
                original_path = d['filename']
                new_path = os.path.join('downloads', final_filename)

                if original_path != new_path:
                    os.rename(original_path, new_path)
                    if final_filename != original_filename:
                        print(f"📝 Archivo renombrado: {original_filename} -> {final_filename}")
                    else:
                        print(f"📁 Archivo guardado: {final_filename}")

                # Registrar archivo para eliminación en 5 minutos
                expiry_time = datetime.now() + timedelta(minutes=5)
                file_expirations[final_filename] = expiry_time

                download_url = f"/downloads/{urllib.parse.quote(final_filename)}"

                sio.emit('progress_update', {
                    'download_id': download_id, 
                    'status': 'Completado',
                    'filename': final_filename,
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
                    
                print(f"✅ Descarga completada: {final_filename}")

        # Obtener configuración con manejo inteligente de cookies
        base_opts = ydl_opts_audio if download_type == 'audio' else ydl_opts_video
        ydl_opts = get_ydl_opts_with_cookies(base_opts, url)
        ydl_opts_with_progress = {**ydl_opts, 'progress_hooks': [progress_hook]}

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
        
        if 'pinterest' in url.lower():
            error_message = 'Pinterest: No se pudo descargar el video.'
        elif 'Sign in to confirm you' in error_str:
            error_message = 'YouTube: Contenido restringido. Se necesitan cookies válidas.'
        else:
            error_message = f'Error: {error_str}'
        
        print(f"❌ {error_message}")
        sio.emit('progress_update', {
            'download_id': download_id, 
            'status': f'Error: {error_message}',
            'type': download_type,
            'progress': 0
        }, room=sid)
        
        if download_id in active_downloads:
            del active_downloads[download_id]

def mark_file_for_immediate_removal(filename):
    """Marca un archivo para eliminación inmediata"""
    expiry_time = datetime.now() + timedelta(minutes=1)
    file_expirations[filename] = expiry_time

def serve_application(environ, start_response):
    path = environ['PATH_INFO']

    if path.startswith('/downloads/'):
        filename_encoded = path[11:]
        filename = urllib.parse.unquote(filename_encoded)
        file_path = os.path.join('downloads', filename)

        print(f"📥 Solicitud de descarga: {filename}")

        if os.path.exists(file_path) and os.path.isfile(file_path):
            if filename in file_expirations:
                # Usar el nombre original para la descarga
                headers = [
                    ('Content-Type', 'application/octet-stream'),
                    ('Content-Disposition', f'attachment; filename="{filename}"'),
                    ('Cache-Control', 'no-cache, must-revalidate'),
                    ('Pragma', 'no-cache'),
                    ('Expires', '0'),
                    ('Content-Length', str(os.path.getsize(file_path)))
                ]
                start_response('200 OK', headers)
                print(f"✅ Sirviendo archivo: {filename}")

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
                start_response('410 Gone', [('Content-Type', 'text/plain')])
                return [b'Archivo expirado']
        else:
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
    print(f"⏰ Los archivos se eliminan 1 minuto después de descargarse")
    print(f"📝 Los videos conservan su nombre original")
    
    # Verificar estado de las cookies
    if check_cookies_validity():
        print(f"🔐 Cookies: VÁLIDAS - Descargas con autenticación")
    else:
        print(f"🔓 Cookies: NO VÁLIDAS - Solo contenido público")
        print(f"💡 Consejo: Exporta cookies reales de YouTube usando una extensión del navegador")

    eventlet.wsgi.server(eventlet.listen(('0.0.0.0', port)), serve_application)