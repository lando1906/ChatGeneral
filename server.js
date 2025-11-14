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

// Servir archivos estáticos
app.use(express.static(path.join(__dirname, 'public')));

// Almacenamiento de usuarios y llamadas
const users = new Map();
const calls = new Map();

io.on('connection', (socket) => {
  console.log('Usuario conectado:', socket.id);

  // Registrar usuario
  socket.on('register', (userData) => {
    users.set(socket.id, {
      id: socket.id,
      name: userData.name,
      avatar: userData.avatar,
      online: true
    });
    
    // Notificar a todos los usuarios actualizados
    broadcastUsers();
  });

  // Iniciar llamada
  socket.on('call-user', (data) => {
    const caller = users.get(socket.id);
    const targetUser = Array.from(users.values()).find(u => u.id === data.targetId);
    
    if (targetUser) {
      // Crear sala de llamada
      const callId = `${socket.id}-${Date.now()}`;
      calls.set(callId, {
        id: callId,
        caller: socket.id,
        target: data.targetId,
        status: 'ringing'
      });

      // Notificar al usuario objetivo
      socket.to(data.targetId).emit('incoming-call', {
        callId,
        caller: caller,
        offer: data.offer
      });

      socket.emit('call-started', { callId });
    }
  });

  // Aceptar llamada
  socket.on('accept-call', (data) => {
    const call = calls.get(data.callId);
    if (call && call.target === socket.id) {
      calls.set(data.callId, { ...call, status: 'active' });
      
      socket.to(call.caller).emit('call-accepted', {
        callId: data.callId,
        answer: data.answer
      });
    }
  });

  // Rechazar llamada
  socket.on('reject-call', (data) => {
    const call = calls.get(data.callId);
    if (call) {
      socket.to(call.caller).emit('call-rejected', {
        callId: data.callId,
        reason: data.reason
      });
      calls.delete(data.callId);
    }
  });

  // ICE Candidates
  socket.on('ice-candidate', (data) => {
    socket.to(data.target).emit('ice-candidate', {
      candidate: data.candidate,
      from: socket.id
    });
  });

  // Colgar llamada
  socket.on('end-call', (data) => {
    const call = calls.get(data.callId);
    if (call) {
      socket.to(call.caller).emit('call-ended');
      socket.to(call.target).emit('call-ended');
      calls.delete(data.callId);
    }
  });

  // Obtener usuarios en línea
  socket.on('get-users', () => {
    broadcastUsers();
  });

  function broadcastUsers() {
    const onlineUsers = Array.from(users.values())
      .filter(user => user.online && user.id !== socket.id);
    
    socket.emit('users-update', onlineUsers);
    socket.broadcast.emit('users-update', 
      Array.from(users.values())
        .filter(user => user.online && user.id !== socket.id)
    );
  }

  socket.on('disconnect', () => {
    const user = users.get(socket.id);
    if (user) {
      users.set(socket.id, { ...user, online: false });
    }
    
    // Notificar que el usuario se desconectó
    socket.broadcast.emit('user-disconnected', socket.id);
    users.delete(socket.id);
    console.log('Usuario desconectado:', socket.id);
  });
});

const PORT = process.env.PORT || 10000;
server.listen(PORT, () => {
  console.log(`Servidor ejecutándose en puerto ${PORT}`);
});