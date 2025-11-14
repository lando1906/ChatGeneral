# server.py
import os
from flask import Flask, render_template, request, session, redirect, url_for
from flask_socketio import SocketIO, emit, join_room, leave_room
import eventlet

eventlet.monkey_patch()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
socketio = SocketIO(app, cors_allowed_origins="*")

# Simulación de base de datos en memoria
users = {}
online_users = {}

@app.route('/')
def home():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('index.html', username=session['username'], online_users=online_users)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        action = request.form.get('action')

        if action == 'register':
            if username in users:
                return render_template('auth.html', error="Usuario ya existe")
            if len(username) < 3:
                return render_template('auth.html', error="Usuario muy corto")
            users[username] = password
            return render_template('auth.html', success="Registro exitoso, inicia sesión")

        elif action == 'login':
            if username in users and users[username] == password:
                session['username'] = username
                return redirect(url_for('home'))
            else:
                return render_template('auth.html', error="Credenciales inválidas")

    return render_template('auth.html')

@app.route('/logout')
def logout():
    username = session.pop('username', None)
    if username:
        online_users.pop(username, None)
        socketio.emit('user_offline', {'username': username})
    return redirect(url_for('login'))

# Socket.IO Events
@socketio.on('connect')
def handle_connect():
    username = session.get('username')
    if username:
        online_users[username] = request.sid
        emit('user_online', {'username': username}, broadcast=True)
        emit('online_users', {'users': list(online_users.keys())})

@socketio.on('disconnect')
def handle_disconnect():
    username = session.get('username')
    if username and online_users.get(username) == request.sid:
        online_users.pop(username)
        emit('user_offline', {'username': username}, broadcast=True)

@socketio.on('call_user')
def handle_call(data):
    caller = session.get('username')
    callee = data['callee']
    call_type = data['type']  # 'audio' or 'video'
    if callee in online_users:
        emit('incoming_call', {
            'caller': caller,
            'type': call_type
        }, room=online_users[callee])

@socketio.on('answer_call')
def handle_answer(data):
    callee = session.get('username')
    caller = data['caller']
    accepted = data['accepted']
    if caller in online_users:
        emit('call_responded', {
            'callee': callee,
            'accepted': accepted
        }, room=online_users[caller])

@socketio.on('webrtc_signal')
def handle_signal(data):
    target = data['target']
    if target in online_users:
        emit('webrtc_signal', data, room=online_users[target])

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    socketio.run(app, host='0.0.0.0', port=port)