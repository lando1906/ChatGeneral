const express = require('express');
const Imap = require('imap');
const nodemailer = require('nodemailer');
const { simpleParser } = require('mailparser');
const app = express();
const port = 10000;

// =============================================================================
// CONFIGURACIÓN DIRECTA
// =============================================================================
const CONFIG = {
    EMAIL_ACCOUNT: "videodown797@gmail.com",
    EMAIL_PASSWORD: "nlhoedrevnlihgdo",
    IMAP_SERVER: "imap.gmail.com",
    IMAP_PORT: 993,
    SMTP_SERVER: "smtp.gmail.com",
    SMTP_PORT: 587,
    CHECK_INTERVAL: 3000  // 3 segundos
};

// =============================================================================
// CLASE YOUCHAT BOT
// =============================================================================
class YouChatBot {
    constructor() {
        this.isRunning = false;
        this.processedEmails = new Set();
        this.totalProcessed = 0;
        console.log('🤖 Bot YouChat inicializado');
    }

    extractYouChatHeaders(emailHeaders) {
        const headersYouchat = {};
        const specificHeaders = [
            'message-id', 'msg_id', 'chat-version', 'pd',
            'sender-alias', 'from-alias', 'thread-id', 'user-id',
            'x-youchat-session', 'x-youchat-platform', 'x-youchat-device',
            'chat-id', 'session-id', 'x-chat-signature', 'x-youchat-version',
            'x-youchat-build', 'x-youchat-environment'
        ];

        for (const [key, value] of Object.entries(emailHeaders)) {
            const keyLower = key.toLowerCase();
            if (keyLower.includes('youchat') || keyLower.includes('chat-') || 
                keyLower.includes('msg_') || keyLower.includes('x-youchat') || 
                keyLower.includes('x-chat')) {
                headersYouchat[key] = value;
            } else if (specificHeaders.includes(keyLower)) {
                headersYouchat[key] = value;
            }
        }
        console.log("📨 Headers de YouChat extraídos:", Object.keys(headersYouchat));
        return headersYouchat;
    }

    extractSenderEmail(fromHeader) {
        try {
            if (fromHeader.includes('<') && fromHeader.includes('>')) {
                return fromHeader.split('<')[1].split('>')[0].trim();
            }
            return fromHeader.trim();
        } catch (error) {
            console.error("❌ Error extrayendo email del remitente:", error);
            return null;
        }
    }

    buildRawYouChatMessage(destinatario, messageId = null, youchatHeaders = {}, asuntoOriginal = null) {
        try {
            console.log("🔨 Construyendo mensaje RAW...");
            let headersString = "";

            // 1. Headers de YouChat Generales
            if (youchatHeaders && typeof youchatHeaders === 'object') {
                for (const key in youchatHeaders) {
                    if (youchatHeaders[key] && !['Msg_id', 'Chat-Version', 'Pd', 'Sender-Alias', 'From-Alias'].includes(key)) {
                        headersString += `${key}: ${youchatHeaders[key]}\r\n`;
                    }
                }
            }

            // 2. Headers de Threading
            const domain = CONFIG.EMAIL_ACCOUNT.split('@')[1];
            headersString += `Message-ID: <auto-reply-${Date.now()}@${domain}>\r\n`;

            if (messageId) {
                const cleanMessageId = messageId.startsWith('<') && messageId.endsWith('>') 
                    ? messageId 
                    : `<${messageId}>`;
                headersString += `In-Reply-To: ${cleanMessageId}\r\n`;
                headersString += `References: ${cleanMessageId}\r\n`;
            }

            // 3. Headers del Bot
            headersString += `Msg_id: auto-reply-${Date.now()}\r\n`;
            const chatVersion = youchatHeaders?.['Chat-Version'] || '1.1';
            headersString += `Chat-Version: ${chatVersion}\r\n`;
            
            const pdValue = youchatHeaders?.['Pd'];
            if (pdValue) {
                headersString += `Pd: ${String(pdValue).trim()}\r\n`;
            }

            // 4. Headers Estándar
            headersString += `MIME-Version: 1.0\r\n`;
            headersString += `Content-Type: text/plain; charset="UTF-8"\r\n`;
            headersString += `Content-Transfer-Encoding: 8bit\r\n`;

            // 5. Asunto inteligente
            let asunto = "YouChat";
            if (asuntoOriginal) {
                if (!asuntoOriginal.toLowerCase().startsWith('re:')) {
                    asunto = `Re: ${asuntoOriginal}`;
                } else {
                    asunto = asuntoOriginal;
                }
            }

            // 6. Construcción FINAL del mensaje RAW
            const mensajeTexto = "¡Hola! Soy un bot en desarrollo. Pronto podré descargar tus Reels de Instagram.";

            const mailRaw = 
                `From: ${CONFIG.EMAIL_ACCOUNT}\r\n` +
                `To: ${destinatario}\r\n` +
                `Subject: ${asunto}\r\n` +
                headersString +
                `\r\n` +
                `${mensajeTexto}`;

            console.log("📧 Mensaje RAW construido exitosamente para:", destinatario);
            return mailRaw;

        } catch (error) {
            console.error("❌ Error construyendo mensaje RAW:", error);
            return null;
        }
    }

    async sendRawResponse(destinatario, messageId = null, youchatHeaders = {}, asuntoOriginal = null) {
        try {
            console.log("🔄 Iniciando envío de respuesta RAW...");

            const rawMessage = this.buildRawYouChatMessage(destinatario, messageId, youchatHeaders, asuntoOriginal);
            if (!rawMessage) {
                console.error("❌ No se pudo construir el mensaje RAW");
                return false;
            }

            console.log("📧 Mensaje RAW construido, procediendo a enviar...");

            // ✅ CONEXIÓN SMTP PARA ENVÍO
            const transporter = nodemailer.createTransport({
                host: CONFIG.SMTP_SERVER,
                port: CONFIG.SMTP_PORT,
                secure: false,
                auth: {
                    user: CONFIG.EMAIL_ACCOUNT,
                    pass: CONFIG.EMAIL_PASSWORD
                },
                timeout: 30000
            });

            console.log("🔗 Conectando al servidor SMTP...");
            
            // Enviar usando el mensaje RAW construido
            await transporter.sendMail({
                from: CONFIG.EMAIL_ACCOUNT,
                to: destinatario,
                subject: asuntoOriginal ? `Re: ${asuntoOriginal}` : 'YouChat',
                text: "¡Hola! Soy un bot en desarrollo. Pronto podré descargar tus Reels de Instagram.",
                headers: this.buildCustomHeaders(messageId, youchatHeaders)
            });

            console.log("✅ Respuesta RAW enviada exitosamente a:", destinatario);
            return true;

        } catch (error) {
            console.error("❌ Error enviando respuesta RAW:", error);
            return false;
        }
    }

    buildCustomHeaders(messageId, youchatHeaders) {
        const domain = CONFIG.EMAIL_ACCOUNT.split('@')[1];
        const headers = {};

        if (youchatHeaders && typeof youchatHeaders === 'object') {
            for (const key in youchatHeaders) {
                if (youchatHeaders[key] && !['Msg_id', 'Chat-Version', 'Pd', 'Sender-Alias', 'From-Alias'].includes(key)) {
                    headers[key] = youchatHeaders[key];
                }
            }
        }

        headers['Message-ID'] = `<auto-reply-${Date.now()}@${domain}>`;
        if (messageId) {
            const cleanMessageId = messageId.startsWith('<') && messageId.endsWith('>') 
                ? messageId 
                : `<${messageId}>`;
            headers['In-Reply-To'] = cleanMessageId;
            headers['References'] = cleanMessageId;
        }
        headers['Msg_id'] = `auto-reply-${Date.now()}`;
        headers['Chat-Version'] = youchatHeaders?.['Chat-Version'] || '1.1';
        
        const pdValue = youchatHeaders?.['Pd'];
        if (pdValue) headers['Pd'] = String(pdValue).trim();

        return headers;
    }

    processUnreadEmails() {
        return new Promise((resolve, reject) => {
            console.log("🔄 Conectando a IMAP para leer bandeja...");
            
            // ✅ CONEXIÓN IMAP SOLO PARA LECTURA
            const imap = new Imap({
                user: CONFIG.EMAIL_ACCOUNT,
                password: CONFIG.EMAIL_PASSWORD,
                host: CONFIG.IMAP_SERVER,
                port: CONFIG.IMAP_PORT,
                tls: true,
                tlsOptions: { rejectUnauthorized: false },
                authTimeout: 10000
            });

            imap.once('ready', () => {
                console.log("✅ Conexión IMAP exitosa - Leyendo bandeja de entrada");
                imap.openBox('INBOX', false, (err, box) => {
                    if (err) {
                        console.error('❌ Error abriendo buzón:', err);
                        imap.end();
                        return reject(err);
                    }

                    console.log("🔍 Buscando SOLO emails no leídos...");
                    // ✅ SOLO BUSCAR EMAILS NO LEÍDOS
                    imap.search(['UNSEEN'], (err, results) => {
                        if (err) {
                            console.error('❌ Error buscando emails:', err);
                            imap.end();
                            return reject(err);
                        }

                        if (!results || results.length === 0) {
                            console.log('📭 No hay emails nuevos no leídos');
                            imap.end();
                            return resolve();
                        }

                        console.log(`📥 ${results.length} nuevo(s) email(s) no leído(s) para procesar`);

                        const fetch = imap.fetch(results, { bodies: '' });

                        fetch.on('message', (msg, seqno) => {
                            console.log(`📨 Procesando email no leído - Secuencia: ${seqno}`);

                            msg.on('body', (stream) => {
                                simpleParser(stream, async (err, parsed) => {
                                    if (err) {
                                        console.error('❌ Error parseando email:', err);
                                        return;
                                    }

                                    const emailId = `${seqno}-${parsed.messageId}`;
                                    if (this.processedEmails.has(emailId)) {
                                        console.log('⏭️ Email ya procesado:', emailId);
                                        return;
                                    }

                                    const senderEmail = this.extractSenderEmail(parsed.from.text);
                                    if (!senderEmail) {
                                        console.error('❌ No se pudo extraer email del remitente');
                                        return;
                                    }

                                    console.log(`👤 Email no leído de: ${senderEmail} - Asunto: ${parsed.subject}`);

                                    const youchatHeaders = this.extractYouChatHeaders(parsed.headers);
                                    const originalMsgId = parsed.messageId;

                                    if (originalMsgId) {
                                        console.log('🔗 Message-ID del mensaje original:', originalMsgId);
                                    }

                                    console.log('🚀 Preparando respuesta automática...');
                                    
                                    // ✅ ENVIAR RESPUESTA VÍA SMTP
                                    const success = await this.sendRawResponse(
                                        senderEmail,
                                        originalMsgId,
                                        youchatHeaders,
                                        parsed.subject
                                    );

                                    if (success) {
                                        this.processedEmails.add(emailId);
                                        this.totalProcessed++;
                                        console.log(`🎉 Respuesta #${this.totalProcessed} enviada exitosamente a: ${senderEmail}`);
                                        
                                        // ✅ MARCAR COMO LEÍDO después de procesar
                                        imap.addFlags(seqno, ['\\Seen'], (err) => {
                                            if (err) {
                                                console.error('❌ Error marcando email como leído:', err);
                                            } else {
                                                console.log('📭 Email marcado como leído');
                                            }
                                        });
                                    } else {
                                        console.error(`❌ Falló el envío de la respuesta a: ${senderEmail}`);
                                    }
                                });
                            });
                        });

                        fetch.once('end', () => {
                            console.log('✅ Procesamiento de emails no leídos completado');
                            imap.end();
                            resolve();
                        });

                        fetch.once('error', (err) => {
                            console.error('❌ Error en fetch:', err);
                            imap.end();
                            reject(err);
                        });
                    });
                });
            });

            imap.once('error', (err) => {
                console.error('❌ Error de conexión IMAP:', err);
                reject(err);
            });

            imap.once('end', () => {
                console.log('🔒 Conexión IMAP cerrada');
            });

            imap.connect();
        });
    }

    async runBot() {
        this.isRunning = true;
        console.log('🚀 Bot YouChat INICIADO - MONITOREO CADA 3 SEGUNDOS');
        console.log('⏰ Intervalo:', CONFIG.CHECK_INTERVAL, 'ms');
        console.log('📧 Cuenta configurada:', CONFIG.EMAIL_ACCOUNT);
        console.log('🎯 SOLO procesará emails NO LEÍDOS');

        let cycleCount = 0;
        while (this.isRunning) {
            try {
                cycleCount++;
                console.log(`\n🔄 CICLO #${cycleCount} - ${new Date().toLocaleTimeString()}`);
                await this.processUnreadEmails();
                console.log(`⏳ Esperando ${CONFIG.CHECK_INTERVAL}ms para siguiente verificación...`);
                await new Promise(resolve => setTimeout(resolve, CONFIG.CHECK_INTERVAL));
            } catch (error) {
                console.error('💥 Error en el bucle principal:', error);
                console.log(`⏳ Reintentando en ${CONFIG.CHECK_INTERVAL}ms...`);
                await new Promise(resolve => setTimeout(resolve, CONFIG.CHECK_INTERVAL));
            }
        }
    }

    stopBot() {
        this.isRunning = false;
        console.log('🛑 Bot YouChat detenido');
    }
}

// =============================================================================
// RUTAS DEL SERVICIO WEB
// =============================================================================
const youchatBot = new YouChatBot();

app.use(express.json());

app.get('/', (req, res) => {
    res.json({
        status: 'online',
        service: 'YouChat Bot - Solo Emails No Leídos',
        version: '2.0',
        bot_running: youchatBot.isRunning,
        total_processed: youchatBot.totalProcessed,
        check_interval: CONFIG.CHECK_INTERVAL + 'ms',
        features: [
            'Monitoreo cada 3 segundos', 
            'SOLO emails no leídos',
            'Headers YouChat', 
            'Respuestas automáticas',
            'IMAP para lectura',
            'SMTP para envío'
        ]
    });
});

app.get('/health', (req, res) => {
    res.json({
        status: 'healthy',
        timestamp: new Date().toISOString(),
        bot_running: youchatBot.isRunning,
        total_processed: youchatBot.totalProcessed,
        memory_usage: `${Math.round(process.memoryUsage().heapUsed / 1024 / 1024)}MB`
    });
});

app.post('/start', (req, res) => {
    if (youchatBot.isRunning) {
        return res.json({ 
            status: 'already_running', 
            message: 'El bot ya está en ejecución',
            total_processed: youchatBot.totalProcessed
        });
    }
    youchatBot.runBot();
    res.json({ 
        status: 'started', 
        message: 'Bot iniciado correctamente - Solo emails no leídos',
        check_interval: CONFIG.CHECK_INTERVAL + 'ms'
    });
});

app.post('/stop', (req, res) => {
    youchatBot.stopBot();
    res.json({ 
        status: 'stopped', 
        message: 'Bot detenido',
        final_stats: {
            total_processed: youchatBot.totalProcessed
        }
    });
});

app.get('/status', (req, res) => {
    res.json({
        is_running: youchatBot.isRunning,
        total_processed: youchatBot.totalProcessed,
        processed_emails_count: youchatBot.processedEmails.size,
        check_interval: CONFIG.CHECK_INTERVAL,
        last_check: new Date().toISOString(),
        mode: 'solo_emails_no_leidos'
    });
});

// =============================================================================
// INICIALIZACIÓN
// =============================================================================
app.listen(port, '0.0.0.0', () => {
    console.log(`🎯 Servidor ejecutándose en puerto ${port}`);
    console.log(`🌐 URL: http://0.0.0.0:${port}`);
    console.log('🔧 Iniciando bot automáticamente...');
    console.log('🎯 MODO: Solo procesará emails NO LEÍDOS');
    
    // Iniciar el bot automáticamente
    youchatBot.runBot().catch(error => {
        console.error('💥 Error crítico iniciando el bot:', error);
    });
});

// Manejo graceful de cierre
process.on('SIGINT', () => {
    console.log('\n🛑 Recibida señal de interrupción...');
    youchatBot.stopBot();
    setTimeout(() => {
        console.log('👋 Servidor cerrado');
        process.exit(0);
    }, 1000);
});

process.on('SIGTERM', () => {
    console.log('\n🛑 Recibida señal de terminación...');
    youchatBot.stopBot();
    setTimeout(() => {
        console.log('👋 Servidor cerrado');
        process.exit(0);
    }, 1000);
});