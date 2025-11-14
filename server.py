# server.py
import os
from flask import Flask, render_template, request, session, redirect, url_for
from flask_socketio import SocketIO, emit
import eventlet

eventlet.monkey_patch()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'cambia-esta-clave-en-produccion-123!'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# Base de datos en memoria
users = {}  # username: password
online_users = {}  # username: socket_id

@app.route('/')
def home():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('users.html', username=session['username'])

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        action = request.form.get('action')

        if len(username) < 3:
            return render_template('auth.html', error="Usuario debe tener al menos 3 caracteres")
        if len(password) < 6:
            return render_template('auth.html', error="Contraseña debe tener al menos 6 caracteres")

        if action == 'register':
            if username in users:
                return render_template('auth.html', error="Usuario ya existe")
            users[username] = password
            return render_template('auth.html', success="Registro exitoso, inicia sesión")
        elif action == 'login':
            if users.get(username) == password:
                session['username'] = username
                return redirect(url_for('home'))
            else:
                return render_template('auth.html', error="Credenciales inválidas")
    return render_template('auth.html')

@app.route('/logout')
def logout():
    username = session.pop('username', None)
    if username and username in online_users:
        sid = online_users.pop(username)
        emit('user_offline', {'username': username}, broadcast=True)
        emit('force_disconnect', room=sid)
    return redirect(url_for('login'))

# Socket.IO
@socketio.on('connect')
def handle_connect():
    username = session.get('username')
    if not username:
        return False
    if username in online_users:
        emit('force_disconnect', room=online_users[username])
    online_users[username] = request.sid
    emit('online_users', {'users': list(online_users.keys())}, broadcast=True)
    emit('user_online', {'username': username}, broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    username = session.get('username')
    if username and online_users.get(username) == request.sid:
        online_users.pop(username, None)
        emit('user_offline', {'username': username}, broadcast=True)

@socketio.on('call_user')
def handle_call(data):
    caller = session.get('username')
    callee = data.get('callee')
    if callee in online_users and callee != caller:
        emit('incoming_call', {'caller': caller, 'type': data['type']}, room=online_users[callee])

@socketio.on('answer_call')
def handle_answer(data):
    callee = session.get('username')
    caller = data.get('caller')
    if caller in online_users:
        emit('call_responded', {'callee': callee, 'accepted': data['accepted']}, room=online_users[caller])

@socketio.on('webrtc_signal')
def handle_signal(data):
    target = data.get('target')
    if target in online_users:
        data['sender'] = session.get('username')
        emit('webrtc_signal', data, room=online_users[target])

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    socketio.run(app, host='0.0.0.0', port=port, debug=True)