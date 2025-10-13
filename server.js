const WebSocket = require('ws');
const http = require('http');
const express = require('express');
const path = require('path');

const app = express();
const server = http.createServer(app);
const wss = new WebSocket.Server({ server });

// Middleware para servir archivos estáticos
app.use(express.static(path.join(__dirname, 'public')));

// Ruta principal - sirve el chat
app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// Health check endpoint REQUERIDO para Render
app.get('/health', (req, res) => {
    res.status(200).json({ 
        status: 'OK', 
        timestamp: new Date().toISOString(),
        connections: clients.size
    });
});

// Almacenar clientes conectados
const clients = new Set();

wss.on('connection', function connection(ws) {
    console.log('✅ Nuevo cliente conectado');
    clients.add(ws);
    
    // Notificar al nuevo cliente que está conectado
    ws.send(JSON.stringify({
        type: 'system',
        text: 'Conectado al chat en tiempo real',
        timestamp: new Date().toLocaleTimeString()
    }));
    
    // Notificar a otros usuarios (opcional)
    broadcastToOthers(ws, {
        type: 'system', 
        text: 'Nuevo usuario se unió al chat',
        timestamp: new Date().toLocaleTimeString()
    });

    ws.on('message', function incoming(data) {
        try {
            const messageData = JSON.parse(data);
            console.log('📨 Mensaje recibido:', messageData);
            
            // **COMPATIBILIDAD TOTAL** con mensajes existentes
            const broadcastData = {
                text: messageData.text,
                timestamp: messageData.timestamp || new Date().toLocaleTimeString(),
                sender: messageData.sender || `Usuario${Array.from(clients).indexOf(ws) + 1}`,
                type: messageData.type || 'message'
            };
            
            // Reenviar mensaje a todos los clientes excepto al remitente
            broadcastToOthers(ws, broadcastData);
            
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
        clients.delete(ws);
        
        // Notificar a los demás usuarios
        broadcastToAll({
            type: 'system',
            text: 'Un usuario abandonó el chat',
            timestamp: new Date().toLocaleTimeString()
        });
    });

    ws.on('error', function(error) {
        console.error('💥 Error WebSocket:', error);
        clients.delete(ws);
    });
});

// Función para broadcast a todos excepto al remitente
function broadcastToOthers(senderWs, data) {
    const message = JSON.stringify(data);
    clients.forEach(function each(client) {
        if (client !== senderWs && client.readyState === WebSocket.OPEN) {
            client.send(message);
        }
    });
}

// Función para broadcast a todos los clientes
function broadcastToAll(data) {
    const message = JSON.stringify(data);
    clients.forEach(function each(client) {
        if (client.readyState === WebSocket.OPEN) {
            client.send(message);
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

// Configuración del puerto para Render
const PORT = process.env.PORT || 3000;

server.listen(PORT, function() {
    console.log(`🚀 Servidor ejecutándose en puerto ${PORT}`);
    console.log(`📍 Salud: http://localhost:${PORT}/health`);
    console.log(`💬 Chat: http://localhost:${PORT}/`);
});