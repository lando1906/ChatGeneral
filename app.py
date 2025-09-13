from flask import Flask, render_template, request, redirect, url_for, session, jsonify, make_response
from flask_socketio import SocketIO, emit, join_room, leave_room
from datetime import datetime, timedelta
import sqlite3
import hashlib
import uuid
import threading
import time

app = Flask(__name__)
app.config['SECRET_KEY'] = 'chat_general_secret_key_2025'
socketio = SocketIO(app, cors_allowed_origins="*")

# Configuración de la base de datos
DATABASE = 'chat.db'

def init_db():
    """Inicializar la base de datos con las tablas necesarias"""
    with sqlite3.connect(DATABASE) as conn:
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
        
        # Tabla de mensajes
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                message TEXT NOT NULL,
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
    """Hashear la contraseña para almacenamiento seguro"""
    return hashlib.sha256(password.encode()).hexdigest()

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
                    # Iniciar sesión automáticamente
                    session['user_id'] = user[0]
                    session['username'] = user[1]
                    
                    # Actualizar estado a en línea
                    cursor.execute(
                        'UPDATE users SET is_online = TRUE, last_seen = CURRENT_TIMESTAMP WHERE id = ?',
                        (user[0],)
                    )
                    conn.commit()
                    
                    return True
        except Exception as e:
            print(f"Error verificando token: {e}")
    
    return False

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
    # Verificar si ya hay sesión activa
    if 'user_id' in session:
        return render_template('chat.html', username=session['username'])
    
    # Verificar token de recordatorio
    if check_remember_token():
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
    
    hashed_password = hash_password(password)
    
    try:
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT id, username FROM users WHERE username = ? AND password = ?',
                (username, hashed_password)
            )
            user = cursor.fetchone()
            
            if user:
                # Actualizar estado a en línea
                cursor.execute(
                    'UPDATE users SET is_online = TRUE, last_seen = CURRENT_TIMESTAMP WHERE id = ?',
                    (user[0],)
                )
                
                # Guardar en sesión
                session['user_id'] = user[0]
                session['username'] = user[1]
                
                response_data = {'success': True, 'message': 'Inicio de sesión exitoso'}
                
                # Generar token de recordatorio si se seleccionó "Recuérdame"
                if remember_me:
                    # Generar token único
                    token = str(uuid.uuid4())
                    expires_at = datetime.now() + timedelta(days=30)  # 30 días de validez
                    
                    # Guardar token en la base de datos
                    cursor.execute(
                        'INSERT INTO remember_tokens (user_id, token, expires_at) VALUES (?, ?, ?)',
                        (user[0], token, expires_at)
                    )
                    conn.commit()
                    
                    # Crear respuesta con cookie
                    response = make_response(jsonify(response_data))
                    response.set_cookie(
                        'remember_token', 
                        value=token, 
                        expires=expires_at,
                        httponly=True,
                        secure=False,
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
        
        # Eliminar tokens de recordatorio
        remember_token = request.cookies.get('remember_token')
        if remember_token:
            with sqlite3.connect(DATABASE) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'DELETE FROM remember_tokens WHERE token = ?',
                    (remember_token,)
                )
                conn.commit()
        
        # Actualizar estado a desconectado
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute(
                'UPDATE users SET is_online = FALSE, last_seen = CURRENT_TIMESTAMP WHERE id = ?',
                (user_id,)
            )
            conn.commit()
        
        # Limpiar sesión
        session.pop('user_id', None)
        session.pop('username', None)
    
    # Crear respuesta para eliminar cookie
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
                'SELECT id, username, is_online, last_seen FROM users ORDER BY is_online DESC, username'
            )
            users = cursor.fetchall()
            
            user_list = []
            for user in users:
                user_list.append({
                    'id': user[0],
                    'username': user[1],
                    'is_online': bool(user[2]),
                    'last_seen': user[3]
                })
            
            return jsonify({'success': True, 'users': user_list})
    
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error al obtener usuarios: {str(e)}'})

@app.route('/api/messages')
def get_messages():
    """Obtener historial de mensajes"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'No autorizado'})
    
    try:
        limit = request.args.get('limit', 50)
        
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT username, message, timestamp FROM messages ORDER BY timestamp DESC LIMIT ?',
                (limit,)
            )
            messages = cursor.fetchall()
            
            message_list = []
            for msg in reversed(messages):  # Invertir para orden cronológico
                message_list.append({
                    'username': msg[0],
                    'message': msg[1],
                    'timestamp': msg[2]
                })
            
            return jsonify({'success': True, 'messages': message_list})
    
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error al obtener mensajes: {str(e)}'})

# Eventos de SocketIO
@socketio.on('connect')
def handle_connect():
    """Manejar conexión de socket"""
    if 'user_id' in session:
        join_room('general_chat')
        emit('user_joined', {
            'username': session['username'],
            'message': f'{session["username"]} se ha unido al chat',
            'timestamp': datetime.now().isoformat()
        }, room='general_chat')

@socketio.on('disconnect')
def handle_disconnect():
    """Manejar desconexión de socket"""
    if 'user_id' in session:
        leave_room('general_chat')
        emit('user_left', {
            'username': session['username'],
            'message': f'{session["username"]} ha abandonado el chat',
            'timestamp': datetime.now().isoformat()
        }, room='general_chat')

@socketio.on('send_message')
def handle_send_message(data):
    """Manejar envío de mensajes"""
    if 'user_id' not in session:
        return
    
    message = data.get('message', '').strip()
    if not message:
        return
    
    # Guardar mensaje en base de datos
    try:
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO messages (user_id, username, message) VALUES (?, ?, ?)',
                (session['user_id'], session['username'], message)
            )
            conn.commit()
        
        # Emitir mensaje a todos los usuarios
        emit('new_message', {
            'username': session['username'],
            'message': message,
            'timestamp': datetime.now().isoformat()
        }, room='general_chat')
    
    except Exception as e:
        emit('error', {'message': f'Error al enviar mensaje: {str(e)}'})

@socketio.on('typing')
def handle_typing(data):
    """Manejar evento de usuario escribiendo"""
    if 'user_id' in session:
        is_typing = data.get('typing', False)
        emit('user_typing', {
            'username': session['username'],
            'typing': is_typing
        }, room='general_chat', include_self=False)

if __name__ == '__main__':
    init_db()
    # Iniciar hilo de limpieza de tokens
    cleanup_thread = threading.Thread(target=token_cleanup_scheduler, daemon=True)
    cleanup_thread.start()
    socketio.run(app, debug=True, host='0.0.0.0', port=10000)