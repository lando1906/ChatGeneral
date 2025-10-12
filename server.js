// server.js - Servidor Node.js mejorado para mensajería en tiempo real
const express = require('express');
const http = require('http');
const socketIo = require('socket.io');
const path = require('path');

const app = express();
const server = http.createServer(app);
const io = socketIo(server, {
  cors: {
    origin: "*",
    methods: ["GET", "POST"]
  }
});

// Middleware para servir archivos estáticos
app.use(express.static(path.join(__dirname, 'public')));

// Almacenamiento en memoria
const users = new Map(); // socket.id -> userData
const messages = new Map(); // roomId -> [messages]

// Generar ID de sala
function generateRoomId(user1, user2) {
  return [user1, user2].sort().join('_');
}

// Configuración de Socket.IO
io.on('connection', (socket) => {
  console.log('Usuario conectado:', socket.id);

  // Registrar usuario
  socket.on('register_user', (userData) => {
    const userInfo = {
      id: socket.id,
      username: userData.username,
      connectedAt: new Date()
    };
    
    users.set(socket.id, userInfo);
    
    // Notificar a todos los usuarios actualizados
    broadcastOnlineUsers();
    
    console.log(`Usuario registrado: ${userData.username} (${socket.id})`);
  });

  // Manejar envío de mensajes
  socket.on('send_message', (data) => {
    const fromUser = users.get(socket.id);
    if (!fromUser) return;

    const toUser = Array.from(users.values()).find(user => user.id === data.to);
    if (!toUser) return;

    const roomId = generateRoomId(socket.id, data.to);
    const message = {
      id: Date.now(),
      text: data.message,
      from: socket.id,
      to: data.to,
      sender: fromUser.username,
      timestamp: new Date()
    };

    // Almacenar mensaje
    if (!messages.has(roomId)) {
      messages.set(roomId, []);
    }
    messages.get(roomId).push(message);

    // Enviar mensaje al destinatario
    socket.to(data.to).emit('new_message', {
      from: socket.id,
      sender: fromUser.username,
      message: data.message,
      timestamp: message.timestamp
    });

    // Enviar confirmación al remitente
    socket.emit('new_message', {
      from: socket.id,
      sender: 'Tú',
      message: data.message,
      timestamp: message.timestamp
    });

    console.log(`Mensaje de ${fromUser.username} para ${toUser.username}: ${data.message}`);
  });

  // Manejar indicador de escritura
  socket.on('typing', (data) => {
    socket.to(data.to).emit('user_typing', {
      from: socket.id
    });
  });

  socket.on('stop_typing', (data) => {
    socket.to(data.to).emit('user_stop_typing', {
      from: socket.id
    });
  });

  // Obtener historial de mensajes
  socket.on('get_message_history', (data) => {
    const roomId = generateRoomId(socket.id, data.withUser);
    const history = messages.get(roomId) || [];
    socket.emit('message_history', history);
  });

  // Manejar desconexión
  socket.on('disconnect', () => {
    const user = users.get(socket.id);
    if (user) {
      console.log(`Usuario desconectado: ${user.username} (${socket.id})`);
      users.delete(socket.id);
      broadcastOnlineUsers();
    }
  });
});

// Función para broadcast de usuarios en línea
function broadcastOnlineUsers() {
  const onlineUsers = Array.from(users.values());
  io.emit('online_users', onlineUsers);
  
  // Notificar conexiones/desconexiones
  io.emit('user_connected', onlineUsers);
}

// Ruta de health check para Render
app.get('/health', (req, res) => {
  res.status(200).json({ 
    status: 'OK', 
    usersOnline: users.size,
    timestamp: new Date().toISOString()
  });
});

// Ruta principal - servir la aplicación
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// Iniciar servidor
const PORT = process.env.PORT || 10000;
server.listen(PORT, () => {
  console.log(`Servidor de mensajería ejecutándose en puerto ${PORT}`);
  console.log(`Usuarios conectados: 0`);
});