const WebSocket = require('ws');
const http = require('http');
const express = require('express');
const path = require('path');

const app = express();
const server = http.createServer(app);
const wss = new WebSocket.Server({ server });

// Servir archivos estáticos
app.use(express.static(path.join(__dirname)));

app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'index.html'));
});

// Almacenar clientes conectados
const clients = new Set();

wss.on('connection', (ws) => {
    console.log('Nuevo cliente conectado');
    clients.add(ws);

    ws.on('message', (message) => {
        try {
            const messageData = JSON.parse(message);
            
            // Retransmitir el mensaje a todos los clientes excepto al remitente
            clients.forEach((client) => {
                if (client !== ws && client.readyState === WebSocket.OPEN) {
                    client.send(JSON.stringify({
                        text: messageData.text,
                        timestamp: messageData.timestamp,
                        sender: `Usuario${Array.from(clients).indexOf(client) + 1}`
                    }));
                }
            });
        } catch (error) {
            console.error('Error procesando mensaje:', error);
        }
    });

    ws.on('close', () => {
        console.log('Cliente desconectado');
        clients.delete(ws);
    });

    ws.on('error', (error) => {
        console.error('Error WebSocket:', error);
        clients.delete(ws);
    });
});

const PORT = process.env.PORT || 3000;
server.listen(PORT, () => {
    console.log(`Servidor ejecutándose en puerto ${PORT}`);
});