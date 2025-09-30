import socketio
import eventlet
import eventlet.wsgi
import yt_dlp
import os
import threading
import time
import re
from datetime import datetime, timedelta

# Configuración para yt-dlp: prioriza 720p, luego 480p, luego 360p
ydl_opts = {
    'format': 'best[height<=720]/best[height<=480]/best[height<=360]/best',
    'outtmpl': 'downloads/%(title)s.%(ext)s',
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

def sanitize_filename(filename):
    """Limpia el nombre del archivo reemplazando espacios y caracteres especiales"""
    # Reemplazar espacios por guiones bajos
    filename = filename.replace(' ', '_')
    # Eliminar caracteres no permitidos en nombres de archivo
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    # Limitar longitud del nombre
    if len(filename) > 100:
        name, ext = os.path.splitext(filename)
        filename = name[:100-len(ext)] + ext
    return filename

@sio.event
def connect(sid, environ):
    print('✅ Cliente conectado:', sid)

@sio.event
def disconnect(sid):
    print('❌ Cliente desconectado:', sid)

@sio.event
def start_download(sid, data):
    url = data['url']
    download_id = data.get('download_id', 'default_id')

    try:
        sio.emit('progress_update', {
            'download_id': download_id, 
            'progress': 0, 
            'status': 'Obteniendo información del video...'
        })

        def progress_hook(d):
            if d['status'] == 'downloading':
                percent = d.get('_percent_str', '0%').strip().replace('%', '')
                try:
                    progress = float(percent)
                except ValueError:
                    progress = 0
                sio.emit('progress_update', {
                    'download_id': download_id, 
                    'progress': progress, 
                    'status': 'Descargando...'
                })
            elif d['status'] == 'finished':
                # Obtener y sanitizar el nombre del archivo
                original_filename = os.path.basename(d['filename'])
                sanitized_filename = sanitize_filename(original_filename)
                
                # Renombrar el archivo si es necesario
                original_path = d['filename']
                new_path = os.path.join('downloads', sanitized_filename)
                
                if original_path != new_path:
                    os.rename(original_path, new_path)
                
                # Registrar archivo para eliminación en 15 minutos
                expiry_time = datetime.now() + timedelta(minutes=15)
                file_expirations[sanitized_filename] = expiry_time

                # Emitir información de descarga completada con enlace
                download_url = f"/downloads/{sanitized_filename}"
                sio.emit('progress_update', {
                    'download_id': download_id, 
                    'progress': 100, 
                    'status': 'Descarga completada',
                    'filename': sanitized_filename,
                    'download_url': download_url,
                    'expires_at': expiry_time.isoformat()
                })
                print(f"✅ Descarga completada: {sanitized_filename}")

        ydl_opts_with_progress = {**ydl_opts, 'progress_hooks': [progress_hook]}

        with yt_dlp.YoutubeDL(ydl_opts_with_progress) as ydl:
            sio.emit('progress_update', {
                'download_id': download_id, 
                'progress': 0, 
                'status': 'Iniciando descarga...'
            })
            ydl.download([url])

    except Exception as e:
        error_message = f'Error: {str(e)}'
        print(f"❌ {error_message}")
        sio.emit('progress_update', {
            'download_id': download_id, 
            'progress': 0, 
            'status': error_message
        })

def serve_application(environ, start_response):
    """Middleware WSGI para manejar archivos estáticos y la aplicación Socket.IO"""
    path = environ['PATH_INFO']
    
    # Servir archivos de descarga
    if path.startswith('/downloads/'):
        filename = path[11:]  # Remover '/downloads/'
        file_path = os.path.join('downloads', filename)
        
        if os.path.exists(file_path) and os.path.isfile(file_path):
            # Verificar si el archivo no ha expirado
            if filename in file_expirations and datetime.now() < file_expirations[filename]:
                headers = [
                    ('Content-Type', 'application/octet-stream'),
                    ('Content-Disposition', f'attachment; filename="{filename}"'),
                    ('Cache-Control', 'no-cache, must-revalidate')
                ]
                start_response('200 OK', headers)
                
                # Enviar el archivo
                with open(file_path, 'rb') as f:
                    return [f.read()]
            else:
                start_response('410 Gone', [('Content-Type', 'text/plain')])
                return [b'Archivo expirado o no disponible']
        else:
            start_response('404 Not Found', [('Content-Type', 'text/plain')])
            return [b'Archivo no encontrado']
    
    # Servir el archivo HTML principal (PAGINA DE INICIO)
    if path == '/' or path == '':
        try:
            with open('static/index.html', 'rb') as f:
                html_content = f.read()
            start_response('200 OK', [('Content-Type', 'text/html')])
            return [html_content]
        except FileNotFoundError:
            start_response('404 Not Found', [('Content-Type', 'text/plain')])
            return [b'Archivo HTML no encontrado']
    
    # Para todas las demás rutas, pasar a la aplicación Socket.IO
    return app(environ, start_response)

if __name__ == '__main__':
    # ¡IMPORTANTE! Usar el puerto 10000 para Render
    port = int(os.environ.get('PORT', 10000))
    print(f"🚀 Servidor ejecutándose en 0.0.0.0:{port}")
    print(f"⏰ Los archivos se eliminarán automáticamente después de 15 minutos")
    
    # Usar el servidor WSGI de eventlet con nuestra aplicación combinada
    eventlet.wsgi.server(eventlet.listen(('0.0.0.0', port)), serve_application)