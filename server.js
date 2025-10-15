const WebSocket = require('ws');
const http = require('http');
const express = require('express');
const path = require('path');
const fs = require('fs');
const bcrypt = require('bcrypt');
const jwt = require('jsonwebtoken');
const { v4: uuidv4 } = require('uuid');

const app = express();
const server = http.createServer(app);
const wss = new WebSocket.Server({ server });

// Middleware
app.use(express.json({ limit: '50mb' }));
app.use(express.static(path.join(__dirname, 'public')));

// Configuración
const JWT_SECRET = process.env.JWT_SECRET || 'your-secret-key';
const USERS_FILE = path.join(__dirname, 'data', 'users.json');
const MESSAGES_FILE = path.join(__dirname, 'data', 'messages.json');
const MAX_MESSAGES = 1000; // Límite de mensajes almacenados
const MAX_FILE_SIZE = 5 * 1024 * 1024; // 5MB

// Manejo de archivos con concurrencia
function loadJSON(file) {
    try {
        if (fs.existsSync(file)) {
            const data = fs.readFileSync(file, 'utf8');
            return JSON.parse(data);
        }
    } catch (error) {
        console.error(`❌ Error loading ${file}:`, error);
        saveJSON(file, []); // Crear archivo vacío si está corrupto
    }
    return [];
}

function saveJSON(file, data) {
    try {
        fs.writeFileSync(file, JSON.stringify(data, null, 2));
        return true;
    } catch (error) {
        console.error(`❌ Error saving ${file}:`, error);
        return false;
    }
}

function loadUsers() {
    return loadJSON(USERS_FILE);
}

function saveUsers(users) {
    return saveJSON(USERS_FILE, users);
}

function loadMessages() {
    const messages = loadJSON(MESSAGES_FILE);
    return messages.slice(-MAX_MESSAGES); // Limitar a los últimos 1000 mensajes
}

function saveMessages(messages) {
    return saveJSON(MESSAGES_FILE, messages.slice(-MAX_MESSAGES));
}

// Almacenar clientes conectados
const clients = new Map();
const onlineUsers = new Map();

// Middleware de autenticación para WebSocket
function authenticateWebSocket(token) {
    try {
        return jwt.verify(token, JWT_SECRET);
    } catch (error) {
        return null;
    }
}

// Rutas de API
app.post('/api/register', async (req, res) => {
    const { username, password, name } = req.body;

    if (!username || !password || !name) {
        return res.status(400).json({ success: false, message: 'Todos los campos son requeridos' });
    }

    if (password.length < 6) {
        return res.status(400).json({ success: false, message: 'La contraseña debe tener al menos 6 caracteres' });
    }

    if (username.length < 3) {
        return res.status(400).json({ success: false, message: 'El usuario debe tener al menos 3 caracteres' });
    }

    const users = loadUsers();
    if (users.find(user => user.username.toLowerCase() === username.toLowerCase())) {
        return res.status(400).json({ success: false, message: 'El usuario ya está registrado' });
    }

    const hashedPassword = await bcrypt.hash(password, 10);
    const newUser = {
        id: uuidv4(),
        username: username.trim(),
        password: hashedPassword,
        name: name.trim(),
        profilePicture: null,
        createdAt: new Date().toISOString()
    };

    users.push(newUser);
    if (saveUsers(users)) {
        const token = jwt.sign({ id: newUser.id, username: newUser.username }, JWT_SECRET, { expiresIn: '7d' });
        res.json({
            success: true,
            message: 'Usuario registrado exitosamente',
            user: { id: newUser.id, name: newUser.name, username: newUser.username, profilePicture: newUser.profilePicture },
            token
        });
    } else {
        res.status(500).json({ success: false, message: 'Error al guardar usuario' });
    }
});

app.post('/api/login', async (req, res) => {
    const { username, password } = req.body;

    if (!username || !password) {
        return res.status(400).json({ success: false, message: 'Usuario y contraseña requeridos' });
    }

    const users = loadUsers();
    const user = users.find(u => u.username.toLowerCase() === username.toLowerCase());

    if (user && await bcrypt.compare(password, user.password)) {
        const token = jwt.sign({ id: user.id, username: user.username }, JWT_SECRET, { expiresIn: '7d' });
        res.json({
            success: true,
            message: 'Login exitoso',
            user: { id: user.id, name: user.name, username: user.username, profilePicture: user.profilePicture },
            token
        });
    } else {
        res.status(401).json({ success: false, message: 'Usuario o contraseña incorrectos' });
    }
});

app.put('/api/update-profile', (req, res) => {
    const { userId, name, profilePicture } = req.body;

    if (!userId) {
        return res.status(400).json({ success: false, message: 'ID de usuario requerido' });
    }

    const users = loadUsers();
    const userIndex = users.findIndex(u => u.id === userId);

    if (userIndex === -1) {
        return res.status(404).json({ success: false, message: 'Usuario no encontrado' });
    }

    if (name && name.trim() !== '') users[userIndex].name = name.trim();
    if (profilePicture) users[userIndex].profilePicture = profilePicture;

    if (saveUsers(users)) {
        const onlineUser = onlineUsers.get(userId);
        if (onlineUser) {
            if (name && name.trim() !== '') onlineUser.name = users[userIndex].name;
            if (profilePicture) onlineUser.profilePicture = users[userIndex].profilePicture;
        }

        res.json({
            success: true,
            message: 'Perfil actualizado exitosamente',
            user: { id: users[userIndex].id, name: users[userIndex].name, username: users[userIndex].username, profilePicture: users[userIndex].profilePicture }
        });
    } else {
        res.status(500).json({ success: false, message: 'Error al actualizar perfil' });
    }
});

app.delete('/api/delete-account', (req, res) => {
    const { userId } = req.body;

    if (!userId) {
        return res.status(400).json({ success: false, message: 'ID de usuario requerido' });
    }

    const users = loadUsers();
    const userIndex = users.findIndex(u => u.id === userId);

    if (userIndex === -1) {
        return res.status(404).json({ success: false, message: 'Usuario no encontrado' });
    }

    users.splice(userIndex, 1);
    if (saveUsers(users)) {
        onlineUsers.delete(userId);
        clients.forEach((clientData, client) => {
            if (clientData.user && clientData.user.id === userId) {
                client.close();
                clients.delete(client);
            }
        });

        broadcastToAll({ type: 'user_leave', user: { id: userId }, timestamp: new Date().toLocaleTimeString() });
        res.json({ success: true, message: 'Cuenta eliminada exitosamente' });
    } else {
        res.status(500).json({ success: false, message: 'Error al eliminar cuenta' });
    }
});

app.get('/api/registered-users', (req, res) => {
    try {
        const users = loadUsers().map(user => ({
            id: user.id,
            name: user.name,
            username: user.username,
            profilePicture: user.profilePicture,
            isOnline: onlineUsers.has(user.id)
        }));
        res.json({ success: true, users });
    } catch (error) {
        console.error('❌ Error obteniendo usuarios registrados:', error);
        res.status(500).json({ success: false, message: 'Error al obtener usuarios', users: [] });
    }
});

app.get('/api/chat-history', (req, res) => {
    const { offset = 0, limit = 50, recipientId } = req.query;
    try {
        let messages = loadMessages();
        if (recipientId) {
            messages = messages.filter(m => (m.recipientId === recipientId && m.userId === req.query.userId) || 
                                           (m.recipientId === req.query.userId && m.userId === recipientId));
        }
        const paginatedMessages = messages.slice(Number(offset), Number(offset) + Number(limit));
        res.json({ success: true, messages: paginatedMessages, total: messages.length });
    } catch (error) {
        console.error('❌ Error obteniendo historial:', error);
        res.status(500).json({ success: false, message: 'Error al obtener historial', messages: [] });
    }
});

app.put('/api/message/:messageId/edit', (req, res) => {
    const { messageId } = req.params;
    const { userId, text } = req.body;

    if (!userId || !text) {
        return res.status(400).json({ success: false, message: 'Usuario y texto requeridos' });
    }

    const messages = loadMessages();
    const messageIndex = messages.findIndex(m => m.messageId === messageId && m.userId === userId);

    if (messageIndex === -1) {
        return res.status(404).json({ success: false, message: 'Mensaje no encontrado o no autorizado' });
    }

    messages[messageIndex].text = text;
    messages[messageIndex].edited = true;

    if (saveMessages(messages)) {
        broadcastToAll({
            type: 'message_edited',
            messageId,
            text,
            timestamp: new Date().toLocaleTimeString()
        });
        res.json({ success: true, message: 'Mensaje editado' });
    } else {
        res.status(500).json({ success: false, message: 'Error al editar mensaje' });
    }
});

app.delete('/api/message/:messageId', (req, res) => {
    const { messageId } = req.params;
    const { userId } = req.body;

    if (!userId) {
        return res.status(400).json({ success: false, message: 'Usuario no autenticado' });
    }

    const messages = loadMessages();
    const messageIndex = messages.findIndex(m => m.messageId === messageId && m.userId === userId);

    if (messageIndex === -1) {
        return res.status(404).json({ success: false, message: 'Mensaje no encontrado' });
    }

    messages.splice(messageIndex, 1);
    if (saveMessages(messages)) {
        broadcastToAll({
            type: 'message_deleted',
            messageId,
            timestamp: new Date().toLocaleTimeString()
        });
        res.json({ success: true, message: 'Mensaje eliminado' });
    } else {
        res.status(500).json({ success: false, message: 'Error al eliminar mensaje' });
    }
});

app.post('/api/mark-read', (req, res) => {
    const { userId, messageIds } = req.body;

    if (!userId || !messageIds || !Array.isArray(messageIds)) {
        return res.status(400).json({ success: false, message: 'Datos inválidos' });
    }

    const messages = loadMessages();
    messageIds.forEach(messageId => {
        const message = messages.find(m => m.messageId === messageId && m.recipientId === userId);
        if (message) {
            message.read = true;
        }
    });

    if (saveMessages(messages)) {
        broadcastToAll({
            type: 'messages_read',
            messageIds,
            userId,
            timestamp: new Date().toLocaleTimeString()
        });
        res.json({ success: true, message: 'Mensajes marcados como leídos' });
    } else {
        res.status(500).json({ success: false, message: 'Error al marcar mensajes' });
    }
});

// Rutas de páginas
app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

app.get('/auth.html', (req, res) => {
    res.sendFile(path.join(__dirname, 'public', 'auth.html'));
});

app.get('/health', (req, res) => {
    const users = loadUsers();
    const messages = loadMessages();
    res.status(200).json({
        status: 'OK',
        timestamp: new Date().toISOString(),
        connections: clients.size,
        usersRegistered: users.length,
        onlineUsers: onlineUsers.size,
        totalMessages: messages.length
    });
});

// WebSocket
wss.on('connection', function connection(ws) {
    console.log('✅ Nuevo cliente conectado');

    let currentUser = null;

    ws.on('message', async function incoming(data) {
        try {
            const messageData = JSON.parse(data.toString());

            if (messageData.type === 'user_join') {
                const decoded = authenticateWebSocket(messageData.token);
                if (!decoded) {
                    ws.send(JSON.stringify({ type: 'error', text: 'Autenticación fallida' }));
                    ws.close();
                    return;
                }

                const users = loadUsers();
                currentUser = users.find(u => u.id === decoded.id);
                if (!currentUser) {
                    ws.send(JSON.stringify({ type: 'error', text: 'Usuario no encontrado' }));
                    ws.close();
                    return;
                }

                clients.set(ws, {
                    user: currentUser,
                    isTyping: false,
                    lastActivity: Date.now()
                });

                onlineUsers.set(currentUser.id, currentUser);

                console.log(`👋 ${currentUser.name} se unió al chat`);

                const messages = loadMessages();
                ws.send(JSON.stringify({
                    type: 'chat_history',
                    messages
                }));

                broadcastToAll({
                    type: 'user_join',
                    user: currentUser,
                    timestamp: new Date().toLocaleTimeString()
                }, ws);

                broadcastUserCount();
                broadcastOnlineUsers();

            } else if (messageData.type === 'typing') {
                const clientData = clients.get(ws);
                if (clientData) {
                    clientData.isTyping = messageData.typing;
                    clientData.lastActivity = Date.now();
                    broadcastTypingStatus(clientData, messageData.typing, messageData.recipientId);
                }

            } else if (['message', 'image', 'video', 'file'].includes(messageData.type)) {
                const clientData = clients.get(ws);
                if (!clientData) return;

                clientData.lastActivity = Date.now();

                if (messageData.type !== 'message' && messageData.fileData && messageData.fileData.length > MAX_FILE_SIZE) {
                    ws.send(JSON.stringify({ type: 'error', text: 'Archivo demasiado grande' }));
                    return;
                }

                messageData.messageId = uuidv4();
                messageData.timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
                messageData.read = false;

                const messages = loadMessages();
                messages.push(messageData);
                saveMessages(messages);

                console.log(`💬 ${messageData.type} de ${messageData.user?.name || 'unknown'}`);

                broadcastToAll(messageData, ws, messageData.recipientId);
            }
        } catch (error) {
            console.error('❌ Error procesando mensaje:', error);
            ws.send(JSON.stringify({
                type: 'error',
                text: 'Error procesando mensaje',
                timestamp: new Date().toLocaleTimeString()
            }));
        }
    });

    ws.on('close', function () {
        const clientData = clients.get(ws);
        if (clientData && clientData.user) {
            onlineUsers.delete(clientData.user.id);
            broadcastToAll({
                type: 'user_leave',
                user: clientData.user,
                timestamp: new Date().toLocaleTimeString()
            });
        }
        clients.delete(ws);
        broadcastUserCount();
        broadcastOnlineUsers();
    });

    ws.on('error', function (error) {
        console.error('💥 Error WebSocket:', error);
        const clientData = clients.get(ws);
        if (clientData && clientData.user) {
            onlineUsers.delete(clientData.user.id);
        }
        clients.delete(ws);
        broadcastUserCount();
        broadcastOnlineUsers();
    });
});

// Broadcast functions
function broadcastToAll(data, excludeWs = null, recipientId = null) {
    const message = JSON.stringify(data);
    clients.forEach((clientData, client) => {
        if (client !== excludeWs && client.readyState === WebSocket.OPEN) {
            if (!recipientId || clientData.user.id === recipientId || clientData.user.id === data.userId) {
                client.send(message);
            }
        }
    });
}

function broadcastUserCount() {
    broadcastToAll({ type: 'user_count', count: clients.size });
}

function broadcastOnlineUsers() {
    const users = Array.from(onlineUsers.values()).map(user => ({
        id: user.id,
        name: user.name,
        username: user.username,
        profilePicture: user.profilePicture
    }));
    broadcastToAll({ type: 'online_users', users });
}

function broadcastTypingStatus(clientData, isTyping, recipientId = null) {
    const message = {
        type: 'typing',
        typing: isTyping,
        userId: clientData.user.id,
        user: clientData.user,
        recipientId
    };
    broadcastToAll(message, null, recipientId);
}

// Limpieza de conexiones inactivas
setInterval(() => {
    const now = Date.now();
    clients.forEach((clientData, client) => {
        if (now - clientData.lastActivity > 60000) {
            client.close();
            clients.delete(client);
            if (clientData.user) {
                onlineUsers.delete(clientData.user.id);
            }
        }
    });
    broadcastUserCount();
    broadcastOnlineUsers();
}, 10000);

// Iniciar servidor
const PORT = process.env.PORT || 3000;
server.listen(PORT, function () {
    console.log(`🚀 Servidor ejecutándose en puerto ${PORT}`);
    console.log(`📍 Salud: http://localhost:${PORT}/health`);
    console.log(`🔐 Auth: http://localhost:${PORT}/auth.html`);
    console.log(`💬 Chat: http://localhost:${PORT}/`);
});