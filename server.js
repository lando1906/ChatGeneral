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

// Base de datos simple de usuarios
const USERS_FILE = path.join(__dirname, 'users.json');

function loadUsers() {
    try {
        if (fs.existsSync(USERS_FILE)) {
            return JSON.parse(fs.readFileSync(USERS_FILE, 'utf8'));
        }
    } catch (error) {
        console.error('Error loading users:', error);
    }
    return [];
}

function saveUsers(users) {
    try {
        fs.writeFileSync(USERS_FILE, JSON.stringify(users, null, 2));
        return true;
    } catch (error) {
        console.error('Error saving users:', error);
        return false;
    }
}

// Almacenar clientes conectados
const clients = new Map();

// Rutas de API - SOLO USERNAME/PASSWORD
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
    
    const users = loadUsers();
    
    // Verificar si el usuario ya existe
    if (users.find(user => user.username.toLowerCase() === username.toLowerCase())) {
        return res.json({ success: false, message: 'El usuario ya está registrado' });
    }
    
    const newUser = {
        id: Date.now().toString(),
        username: username.trim(),
        password: password, // En producción, esto debería estar hasheado
        name: username.trim(), // Usamos el username como nombre para mostrar
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
                username: newUser.username 
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
                username: user.username 
            }
        });
    } else {
        res.json({ success: false, message: 'Usuario o contraseña incorrectos' });
    }
});

// Rutas de páginas
app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

app.get('/auth.html', (req, res) => {
    res.sendFile(path.join(__dirname, 'public', 'auth.html'));
});

// Health check para Render
app.get('/health', (req, res) => {
    res.status(200).json({ 
        status: 'OK', 
        timestamp: new Date().toISOString(),
        connections: clients.size,
        usersRegistered: loadUsers().length
    });
});

// WebSocket connection
wss.on('connection', function connection(ws) {
    console.log('✅ Nuevo cliente conectado');
    
    let currentUser = null;

    ws.on('message', function incoming(data) {
        try {
            const messageData = JSON.parse(data);
            
            if (messageData.type === 'user_join') {
                // Almacenar información del usuario
                currentUser = messageData.user;
                clients.set(ws, {
                    user: currentUser,
                    isTyping: false
                });
                
                // Notificar a todos los usuarios
                broadcastToAll({
                    type: 'user_join',
                    user: currentUser,
                    timestamp: new Date().toLocaleTimeString()
                }, ws);
                
                // Enviar contador actualizado
                broadcastUserCount();
                
            } else if (messageData.type === 'typing') {
                // Actualizar estado de escritura
                const clientData = clients.get(ws);
                if (clientData) {
                    clientData.isTyping = messageData.typing;
                    broadcastTypingStatus(clientData, messageData.typing);
                }
                
            } else if (messageData.type === 'message' || messageData.type === 'image' || messageData.type === 'audio') {
                // Mensaje normal (texto, imagen o audio) - reenviar a todos EXCEPTO al remitente original
                broadcastToAll(messageData, ws);
            }
            
        } catch (error) {
            console.error('❌ Error procesando mensaje:', error);
            ws.send(JSON.stringify({
                type: 'error',
                text: 'Error procesando mensaje'
            }));
        }
    });

    ws.on('close', function() {
        console.log('❌ Cliente desconectado');
        const clientData = clients.get(ws);
        if (clientData) {
            // Notificar que el usuario se fue
            broadcastToAll({
                type: 'user_leave',
                user: clientData.user,
                timestamp: new Date().toLocaleTimeString()
            });
        }
        clients.delete(ws);
        broadcastUserCount();
    });

    ws.on('error', function(error) {
        console.error('💥 Error WebSocket:', error);
        clients.delete(ws);
        broadcastUserCount();
    });
});

// Función para broadcast a todos excepto al remitente especificado
function broadcastToAll(data, excludeWs = null) {
    const message = JSON.stringify(data);
    clients.forEach((clientData, client) => {
        if (client !== excludeWs && client.readyState === WebSocket.OPEN) {
            client.send(message);
        }
    });
}

function broadcastUserCount() {
    const userCount = clients.size;
    const message = {
        type: 'user_count',
        count: userCount
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

// Manejo graceful de shutdown
process.on('SIGTERM', function() {
    console.log('🔄 Recibió SIGTERM, cerrando servidor...');
    broadcastToAll({
        type: 'system',
        text: 'El servidor se está reiniciando...',
        timestamp: new Date().toLocaleTimeString()
    });
    
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
    console.log(`👥 Usuarios registrados: ${loadUsers().length}`);
    console.log(`📝 Sistema: Solo username/password (sin email)`);
});