from flask import Flask, render_template, request, redirect, url_for, session, jsonify, make_response, send_from_directory
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_bcrypt import Bcrypt
from datetime import datetime, timedelta
import sqlite3
import uuid
import threading
import time
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = 'chat_general_secret_key_2025'
app.config['UPLOAD_FOLDER'] = 'uploads'
bcrypt = Bcrypt(app)
socketio = SocketIO(app, cors_allowed_origins=['http://localhost:10000'])  # Cambia a tu dominio en producción

# Configuración de la base de datos
DATABASE = 'chat.db'

def init_db():
    """Inicializar la base de datos con las tablas necesarias"""
    with sqlite3.connect(DATABASE) as conn:
        conn.execute('PRAGMA journal_mode=WAL;')  # Mejorar concurrencia en SQLite
        cursor = conn.cursor()
        
        # Tabla de usuarios
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_online BOOLEAN DEFAULT FALSE,
                last_seen TIMESTAMP
            )
        ''')
        
        # Tabla de mensajes con soporte para archivos
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                message TEXT,
                file_name TEXT,
                file_size INTEGER,
                file_type TEXT,
                file_url TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Tabla de tokens de recordatorio
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS remember_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token TEXT UNIQUE NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        ''')
        
        conn.commit()

def hash_password(password):
    """Hashear la contraseña usando bcrypt"""
    return bcrypt.generate_password_hash(password).decode('utf-8')

def check_password(stored_password, provided_password):
    """Verificar contraseña con bcrypt"""
    return bcrypt.check_password_hash(stored_password, provided_password)

def cleanup_expired_tokens():
    """Eliminar tokens de recordatorio expirados"""
    try:
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM remember_tokens WHERE expires_at <= datetime('now')")
            conn.commit()
            print(f"Tokens eliminados: {cursor.rowcount}")
    except Exception as e:
        print(f"Error limpiando tokens: {e}")

def token_cleanup_scheduler():
    """Programar limpieza de tokens cada hora"""
    while True:
        cleanup_expired_tokens()
        time.sleep(3600)  # 1 hora

def check_remember_token():
    """Verificar si existe un token de recordatorio válido"""
    remember_token = request.cookies.get('remember_token')
    if remember_token:
        try:
            with sqlite3.connect(DATABASE) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    '''SELECT user_id, username FROM remember_tokens 
                       JOIN users ON remember_tokens.user_id = users.id 
                       WHERE token = ? AND expires_at > datetime('now')''',
                    (remember_token,)
                )
                user = cursor.fetchone()
                
                if user:
                    session['user_id'] = user[0]
                    session['username'] = user[1]
                    
                    cursor.execute(
                        'UPDATE users SET is_online = TRUE, last_seen = CURRENT_TIMESTAMP WHERE id = ?',
                        (user[0],)
                    )
                    conn.commit()
                    
                    return True
        except Exception as e:
            print(f"Error verificando token: {e}")
    
    return False

# Crear carpeta de uploads si no existe
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

@app.route('/')
def index():
    """Redirigir a la página de autenticación"""
    return redirect(url_for('auth'))

@app.route('/auth')
def auth():
    """Página de autenticación"""
    if 'user_id' in session:
        return redirect(url_for('chat'))
    return render_template('auth.html')

@app.route('/chat')
def chat():
    """Página principal del chat"""
    if 'user_id' in session or check_remember_token():
        return render_template('chat.html', username=session['username'])
    return redirect(url_for('auth'))

@app.route('/terminos')
def terminos():
    """Página de términos y condiciones"""
    return render_template('terminos.html')

@app.route('/api/register', methods=['POST'])
def register():
    """API para registro de usuarios"""
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'success': False, 'message': 'Usuario y contraseña son requeridos'})
    
    if len(password) < 8:
        return jsonify({'success': False, 'message': 'La contraseña debe tener al menos 8 caracteres'})
    
    hashed_password = hash_password(password)
    
    try:
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO users (username, password) VALUES (?, ?)',
                (username, hashed_password)
            )
            conn.commit()
        
        return jsonify({'success': True, 'message': 'Registro exitoso'})
    
    except sqlite3.IntegrityError:
        return jsonify({'success': False, 'message': 'El nombre de usuario ya existe'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error en el registro: {str(e)}'})

@app.route('/api/login', methods=['POST'])
def login():
    """API para inicio de sesión"""
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    remember_me = data.get('remember_me', False)
    
    if not username or not password:
        return jsonify({'success': False, 'message': 'Usuario y contraseña son requeridos'})
    
    try:
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT id, username, password FROM users WHERE username = ?',
                (username,)
            )
            user = cursor.fetchone()
            
            if user and check_password(user[2], password):
                cursor.execute(
                    'UPDATE users SET is_online = TRUE, last_seen = CURRENT_TIMESTAMP WHERE id = ?',
                    (user[0],)
                )
                session['user_id'] = user[0]
                session['username'] = user[1]
                
                response_data = {'success': True, 'message': 'Inicio de sesión exitoso'}
                
                if remember_me:
                    token = str(uuid.uuid4())
                    expires_at = datetime.now() + timedelta(days=30)
                    cursor.execute(
                        'INSERT INTO remember_tokens (user_id, token, expires_at) VALUES (?, ?, ?)',
                        (user[0], token, expires_at)
                    )
                    conn.commit()
                    response = make_response(jsonify(response_data))
                    response.set_cookie(
                        'remember_token',
                        value=token,
                        expires=expires_at,
                        httponly=True,
                        secure=False,  # Cambia a True en producción con HTTPS
                        samesite='Lax'
                    )
                    return response
                
                return jsonify(response_data)
            else:
                return jsonify({'success': False, 'message': 'Credenciales incorrectas'})
    
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error en el inicio de sesión: {str(e)}'})

@app.route('/api/logout')
def logout():
    """Cerrar sesión"""
    if 'user_id' in session:
        user_id = session['user_id']
        
        try:
            with sqlite3.connect(DATABASE) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'UPDATE users SET is_online = FALSE, last_seen = CURRENT_TIMESTAMP WHERE id = ?',
                    (user_id,)
                )
                remember_token = request.cookies.get('remember_token')
                if remember_token:
                    cursor.execute(
                        'DELETE FROM remember_tokens WHERE token = ?',
                        (remember_token,)
                    )
                conn.commit()
        except Exception as e:
            print(f"Error al cerrar sesión: {e}")
        
        session.pop('user_id', None)
        session.pop('username', None)
    
    response = make_response(redirect(url_for('auth')))
    response.set_cookie('remember_token', '', expires=0)
    return response

@app.route('/api/users')
def get_users():
    """Obtener lista de usuarios"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'No autorizado'})
    
    try:
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT id, username, is_online FROM users ORDER BY is_online DESC, username'
            )
            users = cursor.fetchall()
            
            user_list = [
                {
                    'id': user[0],
                    'username': user[1],
                    'online': bool(user[2]),
                    'avatar': f'https://ui-avatars.com/api/?name={user[1]}&background=2563eb&color=fff'
                } for user in users
            ]
            
            return jsonify({'success': True, 'users': user_list})
    
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error al obtener usuarios: {str(e)}'})

@app.route('/api/messages')
def get_messages():
    """Obtener historial de mensajes"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'No autorizado'})
    
    try:
        limit = request.args.get('limit', 50, type=int)
        
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute(
                '''
                SELECT user_id, username, message, file_name, file_size, file_type, file_url, timestamp
                FROM messages
                ORDER BY timestamp DESC
                LIMIT ?
                ''',
                (limit,)
            )
            messages = cursor.fetchall()
            
            message_list = [
                {
                    'userId': msg[0],
                    'username': msg[1],
                    'text': msg[2],
                    'file': {
                        'name': msg[3],
                        'size': msg[4],
                        'type': msg[5],
                        'url': msg[6]
                    } if msg[3] else None,
                    'timestamp': msg[7]
                } for msg in reversed(messages)
            ]
            
            return jsonify({'success': True, 'messages': message_list})
    
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error al obtener mensajes: {str(e)}'})

@app.route('/api/upload', methods=['POST'])
def upload_file():
    """Subir archivos adjuntos"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'No autorizado'})
    
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'No se proporcionó archivo'})
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'Nombre de archivo vacío'})
    
    if file:
        max_size = 10 * 1024 * 1024  # 10MB
        if file.content_length > max_size:
            return jsonify({'success': False, 'message': 'El archivo excede el tamaño máximo de 10MB'})
        
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        return jsonify({
            'success': True,
            'file': {
                'name': filename,
                'size': file.content_length,
                'type': file.content_type,
                'url': f'/uploads/{filename}'
            }
        })

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    """Servir archivos subidos"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# Eventos de SocketIO
@socketio.on('connect')
def handle_connect():
    """Manejar conexión de socket"""
    if 'user_id' in session:
        try:
            with sqlite3.connect(DATABASE) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'UPDATE users SET is_online = TRUE, last_seen = CURRENT_TIMESTAMP WHERE id = ?',
                    (session['user_id'],)
                )
                conn.commit()
        except Exception as e:
            print(f"Error al actualizar estado: {e}")
        
        join_room('general_chat')
        emit('user_joined', {
            'username': session['username'],
            'message': f'{session["username"]} se ha unido al chat',
            'timestamp': datetime.now().isoformat()
        }, room='general_chat')
        handle_get_users()

@socketio.on('disconnect')
def handle_disconnect():
    """Manejar desconexión de socket"""
    if 'user_id' in session:
        try:
            with sqlite3.connect(DATABASE) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'UPDATE users SET is_online = FALSE, last_seen = CURRENT_TIMESTAMP WHERE id = ?',
                    (session['user_id'],)
                )
                conn.commit()
        except Exception as e:
            print(f"Error al actualizar estado: {e}")
        
        leave_room('general_chat')
        emit('user_left', {
            'username': session['username'],
            'message': f'{session["username"]} ha abandonado el chat',
            'timestamp': datetime.now().isoformat()
        }, room='general_chat')
        handle_get_users()

@socketio.on('chat message')
def handle_chat_message(data):
    """Manejar envío de mensajes"""
    if 'user_id' not in session:
        return
    
    message = data.get('text', '').strip()
    file_data = data.get('file')
    
    if not message and not file_data:
        return
    
    try:
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute(
                '''
                INSERT INTO messages (user_id, username, message, file_name, file_size, file_type, file_url)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    session['user_id'],
                    session['username'],
                    message,
                    file_data['name'] if file_data else None,
                    file_data['size'] if file_data else None,
                    file_data['type'] if file_data else None,
                    file_data['url'] if file_data else None
                )
            )
            conn.commit()
        
        emit_data = {
            'userId': session['user_id'],
            'username': session['username'],
            'text': message,
            'timestamp': datetime.now().isoformat()
        }
        if file_data:
            emit_data['file'] = {
                'name': file_data['name'],
                'size': file_data['size'],
                'type': file_data['type'],
                'url': file_data['url']
            }
        
        emit('chat message', emit_data, room='general_chat')
    
    except Exception as e:
        emit('error', {'message': f'Error al enviar mensaje: {str(e)}'})

@socketio.on('typing')
def handle_typing(data):
    """Manejar evento de usuario escribiendo"""
    if 'user_id' in session:
        is_typing = data.get('typing', False)
        emit('user typing', {
            'username': session['username'],
            'isTyping': is_typing
        }, room='general_chat', include_self=False)

@socketio.on('get messages')
def handle_get_messages():
    """Obtener historial de mensajes"""
    if 'user_id' not in session:
        return
    
    try:
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute(
                '''
                SELECT user_id, username, message, file_name, file_size, file_type, file_url, timestamp
                FROM messages
                ORDER BY timestamp DESC
                LIMIT 50
                '''
            )
            messages = cursor.fetchall()
            
            message_list = [
                {
                    'userId': msg[0],
                    'username': msg[1],
                    'text': msg[2],
                    'file': {
                        'name': msg[3],
                        'size': msg[4],
                        'type': msg[5],
                        'url': msg[6]
                    } if msg[3] else None,
                    'timestamp': msg[7]
                } for msg in reversed(messages)
            ]
            
            emit('message history', message_list)
    
    except Exception as e:
        emit('error', {'message': f'Error al obtener mensajes: {str(e)}'})

@socketio.on('get users')
def handle_get_users():
    """Obtener lista de usuarios"""
    if 'user_id' not in session:
        return
    
    try:
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT id, username, is_online FROM users ORDER BY is_online DESC, username'
            )
            users = cursor.fetchall()
            
            user_list = [
                {
                    'id': user[0],
                    'username': user[1],
                    'online': bool(user[2]),
                    'avatar': f'https://ui-avatars.com/api/?name={user[1]}&background=2563eb&color=fff'
                } for user in users
            ]
            
            emit('user list', user_list, room='general_chat')
    
    except Exception as e:
        emit('error', {'message': f'Error al obtener usuarios: {str(e)}'})

if __name__ == '__main__':
    init_db()
    cleanup_thread = threading.Thread(target=token_cleanup_scheduler, daemon=True)
    cleanup_thread.start()
    socketio.run(app, debug=True, host='0.0.0.0', port=10000)