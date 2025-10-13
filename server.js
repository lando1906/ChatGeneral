const WebSocket = require('ws');
const http = require('http');
const express = require('express');
const path = require('path');
const fs = require('fs');

const app = express();
const server = http.createServer(app);
const wss = new WebSocket.Server({ server });

// Middleware
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// Base de datos en archivos JSON
const USERS_FILE = path.join(__dirname, 'data', 'users.json');
const CHATS_FILE = path.join(__dirname, 'data', 'chats.json');
const MESSAGES_FILE = path.join(__dirname, 'data', 'messages.json');

// Asegurar que existe la carpeta data
if (!fs.existsSync(path.join(__dirname, 'data'))) {
    fs.mkdirSync(path.join(__dirname, 'data'));
}

// Funciones de base de datos
function loadData(file) {
    try {
        if (fs.existsSync(file)) {
            return JSON.parse(fs.readFileSync(file, 'utf8'));
        }
    } catch (error) {
        console.error(`Error loading ${file}:`, error);
    }
    return {};
}

function saveData(file, data) {
    try {
        fs.writeFileSync(file, JSON.stringify(data, null, 2));
        return true;
    } catch (error) {
        console.error(`Error saving ${file}:`, error);
        return false;
    }
}

// Cargar datos
let users = loadData(USERS_FILE);
let chats = loadData(CHATS_FILE);
let messages = loadData(MESSAGES_FILE);

// Almacenar conexiones activas
const activeConnections = new Map();

// Generar IDs únicos
function generateId() {
    return Date.now().toString() + Math.random().toString(36).substr(2, 9);
}

// Rutas de API
app.post('/api/register', (req, res) => {
    const { username, password } = req.body;
    
    if (!username || !password) {
        return res.json({ success: false, message: 'Usuario y contraseña son requeridos' });
    }
    
    if (password.length < 4) {
        return res.json({ success: false, message: 'La contraseña debe tener al menos 4 caracteres' });
    }
    
    if (username.length < 3) {
        return res.json({ success: false, message: 'El usuario debe tener al menos 3 caracteres' });
    }
    
    // Verificar si el usuario ya existe
    if (Object.values(users).find(u => u.username.toLowerCase() === username.toLowerCase())) {
        return res.json({ success: false, message: 'El usuario ya está registrado' });
    }
    
    const userId = generateId();
    const newUser = {
        id: userId,
        username: username.trim(),
        password: password,
        name: username.trim(),
        avatar: username.trim().charAt(0).toUpperCase(),
        status: 'offline',
        lastSeen: new Date().toISOString(),
        createdAt: new Date().toISOString()
    };
    
    users[userId] = newUser;
    
    // Crear chat global automáticamente si no existe
    if (!chats.global) {
        chats.global = {
            id: 'global',
            name: 'Chat Global',
            type: 'group',
            avatar: 'G',
            participants: [],
            createdAt: new Date().toISOString(),
            createdBy: 'system'
        };
    }
    
    // Agregar usuario al chat global
    if (!chats.global.participants.includes(userId)) {
        chats.global.participants.push(userId);
    }
    
    if (saveData(USERS_FILE, users) && saveData(CHATS_FILE, chats)) {
        res.json({ 
            success: true, 
            message: 'Usuario registrado exitosamente',
            user: { 
                id: newUser.id, 
                name: newUser.name, 
                username: newUser.username,
                avatar: newUser.avatar
            }
        });
    } else {
        res.json({ success: false, message: 'Error al guardar usuario' });
    }
});

app.post('/api/login', (req, res) => {
    const { username, password } = req.body;
    
    if (!username || !password) {
        return res.json({ success: false, message: 'Usuario y contraseña requeridos' });
    }
    
    const user = Object.values(users).find(u => 
        u.username.toLowerCase() === username.toLowerCase() && 
        u.password === password
    );
    
    if (user) {
        // Actualizar estado
        user.status = 'online';
        user.lastSeen = new Date().toISOString();
        saveData(USERS_FILE, users);
        
        res.json({ 
            success: true, 
            message: 'Login exitoso',
            user: { 
                id: user.id, 
                name: user.name, 
                username: user.username,
                avatar: user.avatar
            }
        });
    } else {
        res.json({ success: false, message: 'Usuario o contraseña incorrectos' });
    }
});

// Obtener chats del usuario
app.get('/api/chats/:userId', (req, res) => {
    const { userId } = req.params;
    
    if (!users[userId]) {
        return res.json({ success: false, message: 'Usuario no encontrado' });
    }
    
    const userChats = Object.values(chats).filter(chat => 
        chat.participants.includes(userId) || chat.type === 'global'
    ).map(chat => {
        // Obtener último mensaje del chat
        const chatMessages = Object.values(messages).filter(m => m.chatId === chat.id);
        const lastMessage = chatMessages.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))[0];
        
        // Contar mensajes no leídos
        const unreadCount = chatMessages.filter(m => 
            m.userId !== userId && !m.readBy?.includes(userId)
        ).length;
        
        return {
            ...chat,
            lastMessage: lastMessage || null,
            unreadCount,
            participantsDetails: chat.participants.map(id => {
                const user = users[id];
                return user ? { id: user.id, name: user.name, avatar: user.avatar, status: user.status } : null;
            }).filter(Boolean)
        };
    });
    
    res.json({ success: true, chats: userChats });
});

// Obtener mensajes de un chat
app.get('/api/messages/:chatId', (req, res) => {
    const { chatId } = req.params;
    const { userId } = req.query;
    
    if (!chats[chatId]) {
        return res.json({ success: false, message: 'Chat no encontrado' });
    }
    
    const chatMessages = Object.values(messages)
        .filter(m => m.chatId === chatId)
        .sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
    
    // Marcar mensajes como leídos
    chatMessages.forEach(message => {
        if (message.userId !== userId && !message.readBy?.includes(userId)) {
            if (!message.readBy) message.readBy = [];
            message.readBy.push(userId);
        }
    });
    
    saveData(MESSAGES_FILE, messages);
    
    res.json({ 
        success: true, 
        messages: chatMessages.map(m => ({
            ...m,
            user: users[m.userId]
        }))
    });
});

// Crear nuevo chat
app.post('/api/chats', (req, res) => {
    const { name, type, participants, createdBy } = req.body;
    
    if (!type || !participants || !createdBy) {
        return res.json({ success: false, message: 'Datos incompletos' });
    }
    
    const chatId = generateId();
    const newChat = {
        id: chatId,
        name: name || `Chat ${type === 'private' ? 'Privado' : 'Grupal'}`,
        type: type,
        avatar: type === 'private' ? 'P' : 'G',
        participants: [...participants, createdBy],
        createdAt: new Date().toISOString(),
        createdBy: createdBy
    };
    
    chats[chatId] = newChat;
    
    if (saveData(CHATS_FILE, chats)) {
        res.json({ 
            success: true, 
            message: 'Chat creado exitosamente',
            chat: newChat
        });
    } else {
        res.json({ success: false, message: 'Error al crear chat' });
    }
});

// Buscar usuarios
app.get('/api/users/search', (req, res) => {
    const { query, excludeUserId } = req.query;
    
    if (!query) {
        return res.json({ success: false, message: 'Query requerida' });
    }
    
    const searchResults = Object.values(users)
        .filter(user => 
            user.id !== excludeUserId &&
            (user.name.toLowerCase().includes(query.toLowerCase()) || 
             user.username.toLowerCase().includes(query.toLowerCase()))
        )
        .map(user => ({
            id: user.id,
            name: user.name,
            username: user.username,
            avatar: user.avatar,
            status: user.status
        }));
    
    res.json({ success: true, users: searchResults });
});

// WebSocket Connection
wss.on('connection', function connection(ws) {
    console.log('✅ Nueva conexión WebSocket');
    
    let currentUser = null;
    let currentChat = null;

    ws.on('message', function incoming(data) {
        try {
            const messageData = JSON.parse(data);
            
            switch (messageData.type) {
                case 'user_join':
                    handleUserJoin(ws, messageData);
                    break;
                    
                case 'chat_join':
                    handleChatJoin(ws, messageData);
                    break;
                    
                case 'typing':
                    handleTyping(ws, messageData);
                    break;
                    
                case 'message':
                    handleNewMessage(ws, messageData);
                    break;
                    
                case 'message_read':
                    handleMessageRead(ws, messageData);
                    break;
                    
                case 'user_status':
                    handleUserStatus(ws, messageData);
                    break;
            }
            
        } catch (error) {
            console.error('❌ Error procesando mensaje:', error);
            sendToClient(ws, {
                type: 'error',
                message: 'Error procesando mensaje'
            });
        }
    });

    ws.on('close', function() {
        console.log('❌ Conexión cerrada');
        if (currentUser) {
            // Actualizar estado a offline
            users[currentUser.id].status = 'offline';
            users[currentUser.id].lastSeen = new Date().toISOString();
            saveData(USERS_FILE, users);
            
            // Notificar a contactos
            notifyUserStatusChange(currentUser.id, 'offline');
        }
        activeConnections.delete(ws);
    });

    ws.on('error', function(error) {
        console.error('💥 Error WebSocket:', error);
        activeConnections.delete(ws);
    });
});

// Manejo de eventos WebSocket
function handleUserJoin(ws, data) {
    const { user, chatId } = data;
    
    if (!users[user.id]) {
        sendToClient(ws, {
            type: 'error',
            message: 'Usuario no válido'
        });
        return;
    }
    
    currentUser = users[user.id];
    currentChat = chatId;
    
    // Actualizar estado a online
    users[user.id].status = 'online';
    saveData(USERS_FILE, users);
    
    activeConnections.set(ws, {
        user: currentUser,
        currentChat: currentChat
    });
    
    // Notificar a contactos del cambio de estado
    notifyUserStatusChange(user.id, 'online');
    
    sendToClient(ws, {
        type: 'user_joined',
        user: currentUser,
        chat: currentChat
    });
}

function handleChatJoin(ws, data) {
    const { chatId, userId } = data;
    
    const connection = activeConnections.get(ws);
    if (connection) {
        connection.currentChat = chatId;
        currentChat = chatId;
    }
    
    sendToClient(ws, {
        type: 'chat_joined',
        chatId: chatId
    });
}

function handleTyping(ws, data) {
    const { chatId, userId, typing } = data;
    const connection = activeConnections.get(ws);
    
    if (connection && chats[chatId]) {
        broadcastToChat(chatId, {
            type: 'typing',
            typing: typing,
            userId: userId,
            user: users[userId],
            timestamp: new Date().toISOString()
        }, ws);
    }
}

function handleNewMessage(ws, data) {
    const { chatId, userId, content, type, replyingTo } = data;
    
    if (!chats[chatId] || !users[userId]) {
        sendToClient(ws, {
            type: 'error',
            message: 'Chat o usuario no válido'
        });
        return;
    }
    
    const messageId = generateId();
    const newMessage = {
        id: messageId,
        chatId: chatId,
        userId: userId,
        content: content,
        type: type || 'text',
        replyingTo: replyingTo,
        timestamp: new Date().toISOString(),
        readBy: [userId] // El remitente ya lo leyó
    };
    
    messages[messageId] = newMessage;
    saveData(MESSAGES_FILE, messages);
    
    // Broadcast a todos en el chat
    broadcastToChat(chatId, {
        type: 'new_message',
        message: {
            ...newMessage,
            user: users[userId]
        }
    });
    
    // Actualizar último mensaje del chat
    chats[chatId].lastMessage = newMessage;
    saveData(CHATS_FILE, chats);
}

function handleMessageRead(ws, data) {
    const { messageId, userId, chatId } = data;
    
    if (messages[messageId]) {
        if (!messages[messageId].readBy) {
            messages[messageId].readBy = [];
        }
        
        if (!messages[messageId].readBy.includes(userId)) {
            messages[messageId].readBy.push(userId);
            saveData(MESSAGES_FILE, messages);
            
            // Notificar al remitente que su mensaje fue leído
            broadcastToChat(chatId, {
                type: 'message_read',
                messageId: messageId,
                readBy: userId,
                timestamp: new Date().toISOString()
            });
        }
    }
}

function handleUserStatus(ws, data) {
    const { userId, status } = data;
    
    if (users[userId]) {
        users[userId].status = status;
        users[userId].lastSeen = new Date().toISOString();
        saveData(USERS_FILE, users);
        
        notifyUserStatusChange(userId, status);
    }
}

// Funciones de utilidad
function sendToClient(ws, data) {
    if (ws.readyState === ws.OPEN) {
        ws.send(JSON.stringify(data));
    }
}

function broadcastToChat(chatId, data, excludeWs = null) {
    const message = JSON.stringify(data);
    const chat = chats[chatId];
    
    if (!chat) return;
    
    activeConnections.forEach((connection, client) => {
        if (chat.participants.includes(connection.user.id) &&
            client !== excludeWs && 
            client.readyState === WebSocket.OPEN) {
            client.send(message);
        }
    });
}

function notifyUserStatusChange(userId, status) {
    const userChats = Object.values(chats).filter(chat => 
        chat.participants.includes(userId)
    );
    
    userChats.forEach(chat => {
        broadcastToChat(chat.id, {
            type: 'user_status_changed',
            userId: userId,
            status: status,
            lastSeen: new Date().toISOString()
        });
    });
}

// Rutas estáticas
app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

app.get('/auth.html', (req, res) => {
    res.sendFile(path.join(__dirname, 'public', 'auth.html'));
});

// Health check
app.get('/health', (req, res) => {
    res.status(200).json({ 
        status: 'OK', 
        timestamp: new Date().toISOString(),
        connections: activeConnections.size,
        users: Object.keys(users).length,
        chats: Object.keys(chats).length,
        messages: Object.keys(messages).length
    });
});

// Iniciar servidor
const PORT = process.env.PORT || 3000;
server.listen(PORT, () => {
    console.log(`🚀 Seend Server ejecutándose en puerto ${PORT}`);
    console.log(`📍 Salud: http://localhost:${PORT}/health`);
    console.log(`🔐 Auth: http://localhost:${PORT}/auth.html`);
    console.log(`💬 App: http://localhost:${PORT}/`);
    console.log(`📊 Estadísticas:`);
    console.log(`   👥 Usuarios: ${Object.keys(users).length}`);
    console.log(`   💬 Chats: ${Object.keys(chats).length}`);
    console.log(`   📨 Mensajes: ${Object.keys(messages).length}`);
});