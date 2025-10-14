const WebSocket = require('ws');
const http = require('http');
const express = require('express');
const path = require('path');
const fs = require('fs');

const app = express();
const server = http.createServer(app);
const wss = new WebSocket.Server({ server });

// Middleware
app.use(express.json({ limit: '50mb' }));
app.use(express.static(path.join(__dirname, 'public')));

// Base de datos simple de usuarios
const USERS_FILE = path.join(__dirname, 'users.json');

function loadUsers() {
    try {
        if (fs.existsSync(USERS_FILE)) {
            const data = fs.readFileSync(USERS_FILE, 'utf8');
            return JSON.parse(data);
        }
    } catch (error) {
        console.error('❌ Error loading users:', error);
    }
    return [];
}

function saveUsers(users) {
    try {
        fs.writeFileSync(USERS_FILE, JSON.stringify(users, null, 2));
        return true;
    } catch (error) {
        console.error('❌ Error saving users:', error);
        return false;
    }
}

// Almacenar clientes conectados
const clients = new Map();
const onlineUsers = new Map();

// Rutas de API
app.post('/api/register', (req, res) => {
    const { username, password, name } = req.body;

    if (!username || !password || !name) {
        return res.json({ success: false, message: 'Todos los campos son requeridos' });
    }

    if (password.length < 4) {
        return res.json({ success: false, message: 'La contraseña debe tener al menos 4 caracteres' });
    }

    if (username.length < 3) {
        return res.json({ success: false, message: 'El usuario debe tener al menos 3 caracteres' });
    }

    const users = loadUsers();

    if (users.find(user => user.username.toLowerCase() === username.toLowerCase())) {
        return res.json({ success: false, message: 'El usuario ya está registrado' });
    }

    const newUser = {
        id: Date.now().toString(),
        username: username.trim(),
        password: password,
        name: name.trim(),
        profilePicture: null,
        createdAt: new Date().toISOString()
    };

    users.push(newUser);

    if (saveUsers(users)) {
        res.json({ 
            success: true, 
            message: 'Usuario registrado exitosamente',
            user: { 
                id: newUser.id, 
                name: newUser.name, 
                username: newUser.username,
                profilePicture: newUser.profilePicture
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

    const users = loadUsers();
    const user = users.find(u => 
        u.username.toLowerCase() === username.toLowerCase() && 
        u.password === password
    );

    if (user) {
        res.json({ 
            success: true, 
            message: 'Login exitoso',
            user: { 
                id: user.id, 
                name: user.name, 
                username: user.username,
                profilePicture: user.profilePicture
            }
        });
    } else {
        res.json({ success: false, message: 'Usuario o contraseña incorrectos' });
    }
});

// Actualizar perfil de usuario - MEJORADO
app.put('/api/update-profile', (req, res) => {
    const { userId, name, profilePicture } = req.body;

    console.log('📝 Actualizando perfil para usuario:', userId);
    console.log('📝 Nuevo nombre:', name);
    console.log('📝 Nueva foto:', profilePicture ? 'Sí' : 'No');

    if (!userId) {
        return res.json({ success: false, message: 'ID de usuario requerido' });
    }

    const users = loadUsers();
    const userIndex = users.findIndex(u => u.id === userId);

    if (userIndex === -1) {
        return res.json({ success: false, message: 'Usuario no encontrado' });
    }

    // Actualizar datos
    if (name && name.trim() !== '') {
        users[userIndex].name = name.trim();
        console.log('✅ Nombre actualizado:', users[userIndex].name);
    }
    
    if (profilePicture) {
        users[userIndex].profilePicture = profilePicture;
        console.log('✅ Foto de perfil actualizada');
    }

    if (saveUsers(users)) {
        // Actualizar en usuarios en línea
        const onlineUser = onlineUsers.get(userId);
        if (onlineUser) {
            if (name && name.trim() !== '') onlineUser.name = users[userIndex].name;
            if (profilePicture) onlineUser.profilePicture = users[userIndex].profilePicture;
            
            // Broadcast la actualización a todos los clientes
            broadcastToAll({
                type: 'user_update',
                user: onlineUser,
                timestamp: new Date().toLocaleTimeString()
            });
        }

        console.log('✅ Perfil actualizado exitosamente');
        res.json({ 
            success: true, 
            message: 'Perfil actualizado exitosamente',
            user: { 
                id: users[userIndex].id, 
                name: users[userIndex].name, 
                username: users[userIndex].username,
                profilePicture: users[userIndex].profilePicture
            }
        });
    } else {
        console.log('❌ Error al guardar cambios');
        res.json({ success: false, message: 'Error al actualizar perfil' });
    }
});

// Eliminar cuenta de usuario - MEJORADO
app.delete('/api/delete-account', (req, res) => {
    const { userId } = req.body;

    console.log('🗑️ Eliminando cuenta para usuario:', userId);

    if (!userId) {
        return res.json({ success: false, message: 'ID de usuario requerido' });
    }

    const users = loadUsers();
    const userIndex = users.findIndex(u => u.id === userId);

    if (userIndex === -1) {
        return res.json({ success: false, message: 'Usuario no encontrado' });
    }

    const userToDelete = users[userIndex];

    // Eliminar usuario
    users.splice(userIndex, 1);

    if (saveUsers(users)) {
        // Eliminar de usuarios en línea
        onlineUsers.delete(userId);

        // Cerrar conexiones WebSocket del usuario
        clients.forEach((clientData, client) => {
            if (clientData.user && clientData.user.id === userId) {
                client.close();
                clients.delete(client);
            }
        });

        // Broadcast que el usuario fue eliminado
        broadcastToAll({
            type: 'user_leave',
            user: userToDelete,
            timestamp: new Date().toLocaleTimeString(),
            systemMessage: `${userToDelete.name} ha eliminado su cuenta`
        });

        broadcastUserCount();
        broadcastOnlineUsers();

        console.log('✅ Cuenta eliminada exitosamente');
        res.json({ 
            success: true, 
            message: 'Cuenta eliminada exitosamente'
        });
    } else {
        console.log('❌ Error al eliminar cuenta');
        res.json({ success: false, message: 'Error al eliminar cuenta' });
    }
});

// Obtener usuarios registrados - MEJORADO
app.get('/api/registered-users', (req, res) => {
    try {
        const users = loadUsers().map(user => ({
            id: user.id,
            name: user.name,
            username: user.username,
            profilePicture: user.profilePicture,
            isOnline: onlineUsers.has(user.id),
            lastSeen: user.lastSeen || null
        }));
        
        console.log('👥 Enviando lista de usuarios registrados:', users.length);
        res.json({ success: true, users });
    } catch (error) {
        console.error('❌ Error obteniendo usuarios registrados:', error);
        res.json({ success: false, message: 'Error al obtener usuarios', users: [] });
    }
});

// Obtener usuarios en línea
app.get('/api/online-users', (req, res) => {
    const users = Array.from(onlineUsers.values()).map(user => ({
        id: user.id,
        name: user.name,
        username: user.username,
        profilePicture: user.profilePicture
    }));
    
    console.log('🌐 Usuarios en línea:', users.length);
    res.json({ success: true, users });
});

// Obtener información de usuario específico
app.get('/api/user/:userId', (req, res) => {
    const { userId } = req.params;
    const users = loadUsers();
    const user = users.find(u => u.id === userId);
    
    if (user) {
        res.json({
            success: true,
            user: {
                id: user.id,
                name: user.name,
                username: user.username,
                profilePicture: user.profilePicture,
                isOnline: onlineUsers.has(user.id)
            }
        });
    } else {
        res.json({ success: false, message: 'Usuario no encontrado' });
    }
});

// Rutas de páginas
app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

app.get('/auth.html', (req, res) => {
    res.sendFile(path.join(__dirname, 'public', 'auth.html'));
});

// Health check mejorado
app.get('/health', (req, res) => {
    const users = loadUsers();
    res.status(200).json({ 
        status: 'OK', 
        timestamp: new Date().toISOString(),
        connections: clients.size,
        usersRegistered: users.length,
        onlineUsers: onlineUsers.size,
        memoryUsage: process.memoryUsage(),
        uptime: process.uptime()
    });
});

// WebSocket connection - MEJORADO
wss.on('connection', function connection(ws) {
    console.log('✅ Nuevo cliente conectado');
    
    let currentUser = null;
    let isAlive = true;

    // Heartbeat para detectar conexiones muertas
    const heartbeat = () => {
        isAlive = true;
    };

    ws.on('pong', heartbeat);

    const heartbeatInterval = setInterval(() => {
        if (!isAlive) {
            console.log('💔 Conexión muerta, cerrando...');
            return ws.terminate();
        }
        
        isAlive = false;
        ws.ping();
    }, 30000);

    ws.on('message', function incoming(data) {
        try {
            const messageData = JSON.parse(data);
            console.log('📨 Mensaje recibido:', messageData.type);

            if (messageData.type === 'user_join') {
                currentUser = messageData.user;
                clients.set(ws, {
                    user: currentUser,
                    isTyping: false,
                    lastActivity: Date.now()
                });
                
                onlineUsers.set(currentUser.id, currentUser);

                console.log(`👋 ${currentUser.name} se unió al chat`);

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
                    broadcastTypingStatus(clientData, messageData.typing);
                }

            } else if (messageData.type === 'message' || 
                       messageData.type === 'image' || 
                       messageData.type === 'audio' || 
                       messageData.type === 'file' || 
                       messageData.type === 'video') {
                
                const clientData = clients.get(ws);
                if (clientData) {
                    clientData.lastActivity = Date.now();
                }

                // Agregar ID único para cada mensaje
                messageData.messageId = Date.now().toString() + Math.random().toString(36).substr(2, 9);
                messageData.timestamp = new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
                
                console.log(`💬 Mensaje de ${messageData.user?.name || 'unknown'}:`, 
                    messageData.type === 'message' ? messageData.text : `[${messageData.type}]`);
                
                broadcastToAll(messageData, ws);
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

    ws.on('close', function() {
        console.log('❌ Cliente desconectado');
        clearInterval(heartbeatInterval);
        
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

    ws.on('error', function(error) {
        console.error('💥 Error WebSocket:', error);
        clearInterval(heartbeatInterval);
        
        const clientData = clients.get(ws);
        if (clientData && clientData.user) {
            onlineUsers.delete(clientData.user.id);
        }
        clients.delete(ws);
        broadcastUserCount();
        broadcastOnlineUsers();
    });
});

// Función para broadcast a todos excepto al remitente especificado
function broadcastToAll(data, excludeWs = null) {
    const message = JSON.stringify(data);
    let sentCount = 0;
    
    clients.forEach((clientData, client) => {
        if (client !== excludeWs && client.readyState === WebSocket.OPEN) {
            client.send(message);
            sentCount++;
        }
    });
    
    console.log(`📤 Broadcast enviado a ${sentCount} clientes:`, data.type);
}

function broadcastUserCount() {
    const userCount = clients.size;
    const message = {
        type: 'user_count',
        count: userCount
    };
    broadcastToAll(message);
}

function broadcastOnlineUsers() {
    const users = Array.from(onlineUsers.values()).map(user => ({
        id: user.id,
        name: user.name,
        username: user.username,
        profilePicture: user.profilePicture
    }));
    
    const message = {
        type: 'online_users',
        users: users
    };
    
    broadcastToAll(message);
}

function broadcastTypingStatus(clientData, isTyping) {
    const message = {
        type: 'typing',
        typing: isTyping,
        userId: clientData.user.id,
        user: clientData.user
    };

    clients.forEach((data, client) => {
        if (client.readyState === WebSocket.OPEN && client !== clients.keys().next().value) {
            client.send(JSON.stringify(message));
        }
    });
}

// Limpieza periódica de conexiones inactivas
setInterval(() => {
    const now = Date.now();
    const timeout = 5 * 60 * 1000; // 5 minutos
    
    clients.forEach((clientData, client) => {
        if (now - clientData.lastActivity > timeout) {
            console.log('🕐 Cerrando conexión inactiva:', clientData.user.name);
            client.close();
        }
    });
}, 60000); // Revisar cada minuto

// Manejo graceful de shutdown
process.on('SIGTERM', function() {
    console.log('🔄 Recibió SIGTERM, cerrando servidor...');
    broadcastToAll({
        type: 'system',
        text: 'El servidor se está reiniciando...',
        timestamp: new Date().toLocaleTimeString()
    });

    setTimeout(() => {
        server.close(function() {
            console.log('✅ Servidor cerrado exitosamente');
            process.exit(0);
        });
    }, 1000);
});

process.on('SIGINT', function() {
    console.log('🔄 Recibió SIGINT, cerrando servidor...');
    server.close(function() {
        console.log('✅ Servidor cerrado exitosamente');
        process.exit(0);
    });
});

// Iniciar servidor
const PORT = process.env.PORT || 3000;
server.listen(PORT, function() {
    console.log(`🚀 Servidor ejecutándose en puerto ${PORT}`);
    console.log(`📍 Salud: http://localhost:${PORT}/health`);
    console.log(`🔐 Auth: http://localhost:${PORT}/auth.html`);
    console.log(`💬 Chat: http://localhost:${PORT}/`);
    
    const users = loadUsers();
    console.log(`👥 Usuarios registrados: ${users.length}`);
    console.log(`🌐 Usuarios en línea: ${onlineUsers.size}`);
    console.log(`🔗 Conexiones activas: ${clients.size}`);
});