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
// CLASE YOUCHAT BOT CON CONEXIÓN IMAP PERSISTENTE CORREGIDA
// =============================================================================
class YouChatBot {
    constructor() {
        this.isRunning = false;
        this.processedEmails = new Set();
        this.totalProcessed = 0;
        this.imapConnection = null;
        this.isImapReady = false;
        this.lastKeepAlive = Date.now();
        this.currentBox = null;
        console.log('🤖 Bot YouChat inicializado');
    }

    // ✅ CONEXIÓN IMAP PERSISTENTE MEJORADA - BUZÓN READ/WRITE
    async connectIMAP() {
        return new Promise((resolve, reject) => {
            if (this.imapConnection && this.isImapReady) {
                console.log("✅ Usando conexión IMAP existente");
                return resolve(this.imapConnection);
            }

            console.log("🔄 Estableciendo conexión IMAP persistente...");
            
            this.imapConnection = new Imap({
                user: CONFIG.EMAIL_ACCOUNT,
                password: CONFIG.EMAIL_PASSWORD,
                host: CONFIG.IMAP_SERVER,
                port: CONFIG.IMAP_PORT,
                tls: true,
                tlsOptions: { rejectUnauthorized: false },
                authTimeout: 10000,
                keepalive: true // ✅ Keepalive automático
            });

            this.imapConnection.once('ready', () => {
                console.log("✅ Conexión IMAP persistente establecida");
                this.isImapReady = true;
                this.lastKeepAlive = Date.now();
                
                // ✅ ABRIR BUZÓN EN MODO LECTURA/ESCRITURA (false = read/write)
                this.imapConnection.openBox('INBOX', false, (err, box) => {
                    if (err) {
                        console.error('❌ Error abriendo buzón:', err);
                        return reject(err);
                    }
                    this.currentBox = box;
                    console.log("📬 Buzón INBOX abierto en modo LECTURA/ESCRITURA - Listo para monitoreo continuo");
                    console.log(`📊 Total de mensajes en buzón: ${box.messages.total}`);
                    resolve(this.imapConnection);
                });
            });

            this.imapConnection.once('error', (err) => {
                console.error('❌ Error en conexión IMAP:', err);
                this.isImapReady = false;
                this.imapConnection = null;
                this.currentBox = null;
            });

            this.imapConnection.once('end', () => {
                console.log('🔒 Conexión IMAP cerrada por el servidor');
                this.isImapReady = false;
                this.imapConnection = null;
                this.currentBox = null;
            });

            // ✅ EVENTOS PARA DETECTAR NUEVOS EMAILS
            this.imapConnection.on('mail', (numNewMsgs) => {
                this.lastKeepAlive = Date.now();
                console.log(`📨 Evento mail - ${numNewMsgs} nuevo(s) email(s) detectado(s)`);
                // Procesar inmediatamente cuando llegue nuevo email
                this.processUnreadEmails();
            });

            this.imapConnection.on('update', (seqno, info) => {
                console.log('🔄 Evento update en IMAP:', info);
                this.lastKeepAlive = Date.now();
            });

            this.imapConnection.connect();
        });
    }

    // ✅ MANTENER CONEXIÓN ACTIVA CORREGIDA
    async keepAliveIMAP() {
        if (!this.imapConnection || !this.isImapReady) {
            console.log("❌ No hay conexión IMAP activa, reconectando...");
            await this.connectIMAP();
            return;
        }

        try {
            // ✅ VERIFICACIÓN DE CONEXIÓN USANDO SEARCH EN LUGAR DE NOOP
            await new Promise((resolve, reject) => {
                this.imapConnection.search(['ALL'], (err, results) => {
                    if (err) {
                        console.error('❌ Error en verificación de conexión IMAP:', err);
                        this.isImapReady = false;
                        reject(err);
                    } else {
                        this.lastKeepAlive = Date.now();
                        console.log("💓 Verificación IMAP exitosa - Conexión activa");
                        resolve(results);
                    }
                });
            });
        } catch (error) {
            console.error('❌ Error en keep-alive IMAP, reconectando...', error);
            this.isImapReady = false;
            this.imapConnection = null;
            await this.connectIMAP();
        }
    }

    extractYouChatHeaders(emailHeaders) {
        const headersYouchat = {};
        
        // ✅ HEADERS ESPECÍFICOS DE YOUCHAT BASADOS EN EL EJEMPLO REAL
        const youchatSpecificHeaders = [
            'version_contacto', 'cant_seguidores', 'Chat-Version', 'youchat', 
            'msg_id', 'pd', 'message-id', 'content-type', 'content-transfer-encoding',
            'mime-version'
        ];

        for (const [key, value] of Object.entries(emailHeaders)) {
            const keyLower = key.toLowerCase();
            
            // ✅ CAPTURAR HEADERS ESPECÍFICOS DE YOUCHAT
            if (youchatSpecificHeaders.some(header => keyLower === header.toLowerCase())) {
                headersYouchat[key] = value;
            }
            // ✅ CAPTURAR HEADERS QUE CONTENGAN "youchat" O "chat"
            else if (keyLower.includes('youchat') || keyLower.includes('chat-')) {
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

    buildRawYouChatMessage(destinatario, messageId = null, youchat_profile_headers = {}, asuntoOriginal = null) {
        try {
            console.log("🔨 Construyendo mensaje RAW con estructura EXACTA de YouChat...");
            let headersString = "";

            // 1. Headers de YouChat Generales (EXACTAMENTE como en el ejemplo real)
            if (youchat_profile_headers && typeof youchat_profile_headers === 'object') {
                for (const key in youchat_profile_headers) {
                    if (youchat_profile_headers[key]) {
                        headersString += `${key}: ${youchat_profile_headers[key]}\r\n`;
                    }
                }
            }

            // 2. Headers de Threading (EXACTAMENTE como en el ejemplo real)
            const domain = CONFIG.EMAIL_ACCOUNT.split('@')[1];
            headersString += `Message-ID: <auto-reply-${Date.now()}@${domain}>\r\n`;

            if (messageId) {
                const cleanMessageId = messageId.startsWith('<') && messageId.endsWith('>') 
                    ? messageId 
                    : `<${messageId}>`;

                headersString += `In-Reply-To: ${cleanMessageId}\r\n`;
                headersString += `References: ${cleanMessageId}\r\n`;
            }

            // 3. Headers del Bot (BASADOS EN EL EJEMPLO REAL RECIBIDO)
            // ✅ CORREGIDO: msg_id en formato YouChat real
            const timestamp = new Date();
            const formattedDate = `${timestamp.getFullYear().toString().slice(2)}${(timestamp.getMonth()+1).toString().padStart(2, '0')}${timestamp.getDate().toString().padStart(2, '0')}`;
            const formattedTime = `${timestamp.getHours().toString().padStart(2, '0')}${timestamp.getMinutes().toString().padStart(2, '0')}${timestamp.getSeconds().toString().padStart(2, '0')}${timestamp.getMilliseconds().toString().padStart(3, '0')}`;
            
            headersString += `msg_id: YCchat${CONFIG.EMAIL_ACCOUNT.split('@')[0]}${formattedDate}${formattedTime}\r\n`;

            // ✅ HEADERS ESPECÍFICOS DEL EJEMPLO REAL
            const chatVersion = youchat_profile_headers?.['Chat-Version'] || '1.0';
            headersString += `Chat-Version: ${chatVersion}\r\n`;
            
            headersString += `youchat: 1\r\n`;
            
            // ✅ CORREGIDO: Usar valores REALES del mensaje original
            const versionContacto = youchat_profile_headers?.['version_contacto'] || '4';
            headersString += `version_contacto: ${versionContacto}\r\n`;
            
            const cantSeguidores = youchat_profile_headers?.['cant_seguidores'] || '1';
            headersString += `cant_seguidores: ${cantSeguidores}\r\n`;

            // ✅ HEADER Pd (MUY IMPORTANTE - PRESERVAR EXACTAMENTE)
            const pdValue = youchat_profile_headers?.['Pd'];
            if (pdValue) {
                headersString += `Pd: ${String(pdValue).trim()}\r\n`;
            }

            // 4. Headers Estándar (EXACTAMENTE como en el ejemplo real)
            headersString += `MIME-Version: 1.0\r\n`;
            // ✅ CORREGIDO: Content-Type exacto como YouChat real
            headersString += `Content-Type: text/plain; charset=us-ascii\r\n`;
            headersString += `Content-Transfer-Encoding: 7bit\r\n`;

            // 5. Construcción FINAL del mensaje RAW
            const mensajeTexto = "¡Hola! Soy un bot en desarrollo. Pronto podré descargar tus Reels de Instagram.";

            // ✅ ESTRUCTURA EXACTA como el ejemplo real recibido
            const mailRaw = 
                `From: ${CONFIG.EMAIL_ACCOUNT}\r\n` + 
                `To: ${destinatario}\r\n` + 
                `Subject: ${asuntoOriginal || 'YouChat'}\r\n` +
                headersString +
                `\r\n` + 
                `${mensajeTexto}`;

            console.log("📧 Mensaje RAW construido EXACTAMENTE como YouChat real para:", destinatario);
            return mailRaw;

        } catch (error) {
            console.error("❌ Error construyendo mensaje RAW:", error);
            return null;
        }
    }

    buildCustomHeaders(messageId, youchat_profile_headers) {
        const domain = CONFIG.EMAIL_ACCOUNT.split('@')[1];
        const headers = {};

        // 1. Headers de YouChat Generales (PRESERVAR TODOS)
        if (youchat_profile_headers && typeof youchat_profile_headers === 'object') {
            for (const key in youchat_profile_headers) {
                if (youchat_profile_headers[key]) {
                    headers[key] = youchat_profile_headers[key];
                }
            }
        }

        // 2. Headers de Threading
        headers['Message-ID'] = `<auto-reply-${Date.now()}@${domain}>`;
        if (messageId) {
            const cleanMessageId = messageId.startsWith('<') && messageId.endsWith('>') 
                ? messageId 
                : `<${messageId}>`;
            headers['In-Reply-To'] = cleanMessageId;
            headers['References'] = cleanMessageId;
        }

        // 3. Headers del Bot (FORMATO EXACTO DE YOUCHAT REAL)
        // ✅ CORREGIDO: msg_id en formato YouChat real
        const timestamp = new Date();
        const formattedDate = `${timestamp.getFullYear().toString().slice(2)}${(timestamp.getMonth()+1).toString().padStart(2, '0')}${timestamp.getDate().toString().padStart(2, '0')}`;
        const formattedTime = `${timestamp.getHours().toString().padStart(2, '0')}${timestamp.getMinutes().toString().padStart(2, '0')}${timestamp.getSeconds().toString().padStart(2, '0')}${timestamp.getMilliseconds().toString().padStart(3, '0')}`;
        
        headers['msg_id'] = `YCchat${CONFIG.EMAIL_ACCOUNT.split('@')[0]}${formattedDate}${formattedTime}`;
        
        // ✅ CORREGIDO: Usar valores REALES del mensaje original
        headers['Chat-Version'] = youchat_profile_headers?.['Chat-Version'] || '1.0';
        headers['youchat'] = '1';
        headers['version_contacto'] = youchat_profile_headers?.['version_contacto'] || '4';
        headers['cant_seguidores'] = youchat_profile_headers?.['cant_seguidores'] || '1';
        
        // ✅ HEADER Pd (PRESERVAR EXACTAMENTE)
        const pdValue = youchat_profile_headers?.['Pd'];
        if (pdValue) headers['Pd'] = String(pdValue).trim();

        // ✅ CORREGIDO: Content-Type exacto como YouChat real
        headers['Content-Type'] = 'text/plain; charset=us-ascii';

        return headers;
    }

    async sendRawResponse(destinatario, messageId = null, youchat_profile_headers = {}, asuntoOriginal = null) {
        try {
            console.log("🔄 Iniciando envío de respuesta con estructura EXACTA de YouChat...");

            // ✅ CONEXIÓN SMTP PARA ENVÍO CON DEBUG MEJORADO
            const transporter = nodemailer.createTransport({
                host: CONFIG.SMTP_SERVER,
                port: CONFIG.SMTP_PORT,
                secure: false,
                auth: {
                    user: CONFIG.EMAIL_ACCOUNT,
                    pass: CONFIG.EMAIL_PASSWORD
                },
                debug: true,
                logger: true,
                timeout: 30000
            });

            console.log("🔗 Conectando al servidor SMTP...");
            
            // Verificar conexión primero
            await transporter.verify();
            console.log("✅ SMTP VERIFICADO - Conexión exitosa");
            
            // ✅ ENVIAR USANDO MÉTODO TRADICIONAL CON HEADERS PERSONALIZADOS EXACTOS
            const mailOptions = {
                from: CONFIG.EMAIL_ACCOUNT,
                to: destinatario,
                subject: asuntoOriginal ? `Re: ${asuntoOriginal}` : 'YouChat',
                text: "¡Hola! Soy un bot en desarrollo. Pronto podré descargar tus Reels de Instagram.",
                headers: this.buildCustomHeaders(messageId, youchat_profile_headers)
            };

            const result = await transporter.sendMail(mailOptions);
            console.log(`✅ MENSAJE ACEPTADO POR SMTP: ${result.messageId}`);
            console.log("✅ Respuesta enviada exitosamente con estructura EXACTA de YouChat a:", destinatario);
            return true;

        } catch (error) {
            console.error("❌ ERROR DETALLADO SMTP:", error);
            return false;
        }
    }

    // ✅ MARCAR EMAIL COMO LEÍDO - CORREGIDO PARA USAR UID
    async markEmailAsRead(uid) {
        return new Promise((resolve, reject) => {
            if (!this.imapConnection || !this.isImapReady) {
                console.log('❌ No hay conexión IMAP para marcar como leído');
                return resolve(false);
            }

            console.log(`📭 Intentando marcar email UID:${uid} como leído...`);
            
            this.imapConnection.addFlags(uid, ['\\Seen'], (err) => {
                if (err) {
                    console.error('❌ Error marcando email como leído:', err.message);
                    resolve(false);
                } else {
                    console.log('✅ Email marcado como leído exitosamente');
                    resolve(true);
                }
            });
        });
    }

    // ✅ PROCESAR EMAILS CORREGIDO - USANDO UID PARA MARCAR COMO LEÍDO
    async processUnreadEmails() {
        if (!this.imapConnection || !this.isImapReady) {
            console.log("❌ No hay conexión IMAP activa, intentando reconectar...");
            await this.connectIMAP();
            return;
        }

        return new Promise((resolve, reject) => {
            console.log("🔍 Buscando emails VERDADERAMENTE no leídos...");

            // ✅ BUSCAR SOLO EMAILS NO LEÍDOS (UNSEEN)
            this.imapConnection.search(['UNSEEN'], (err, results) => {
                if (err) {
                    console.error('❌ Error buscando emails:', err);
                    this.isImapReady = false;
                    return reject(err);
                }

                if (!results || results.length === 0) {
                    console.log('📭 No hay emails nuevos no leídos');
                    this.lastKeepAlive = Date.now();
                    return resolve();
                }

                console.log(`📥 ${results.length} nuevo(s) email(s) no leído(s) para procesar`);

                // ✅ USAR UID EN LUGAR DE SEQNO PARA OPERACIONES DE ESCRITURA
                const fetch = this.imapConnection.fetch(results, { 
                    bodies: '',
                    struct: true,
                    markSeen: false, // No marcar como leído automáticamente
                    envelope: true
                });

                let processedCount = 0;

                fetch.on('message', (msg, seqno) => {
                    console.log(`📨 Procesando email - Secuencia: ${seqno}`);

                    let emailData = {
                        headers: {},
                        body: '',
                        seqno: seqno,
                        uid: null
                    };

                    msg.on('body', (stream) => {
                        let buffer = '';
                        stream.on('data', (chunk) => {
                            buffer += chunk.toString('utf8');
                        });
                        stream.on('end', () => {
                            emailData.body = buffer;
                        });
                    });

                    msg.on('attributes', (attrs) => {
                        emailData.attributes = attrs;
                        emailData.uid = attrs.uid; // ✅ OBTENER EL UID
                        console.log(`🆔 UID del email: ${attrs.uid}`);
                    });

                    msg.on('end', async () => {
                        try {
                            const parsed = await simpleParser(emailData.body);
                            const emailId = emailData.uid ? `uid-${emailData.uid}` : `seq-${seqno}`;
                            
                            if (this.processedEmails.has(emailId)) {
                                console.log('⏭️ Email ya procesado:', emailId);
                                processedCount++;
                                if (processedCount === results.length) resolve();
                                return;
                            }

                            const senderEmail = this.extractSenderEmail(parsed.from.text);
                            if (!senderEmail) {
                                console.error('❌ No se pudo extraer email del remitente');
                                processedCount++;
                                if (processedCount === results.length) resolve();
                                return;
                            }

                            console.log(`👤 Nuevo email no leído de: ${senderEmail}`);
                            console.log(`📝 Asunto: ${parsed.subject}`);
                            console.log(`🆔 UID: ${emailData.uid}`);

                            const youchatHeaders = this.extractYouChatHeaders(parsed.headers);
                            const originalMsgId = parsed.messageId;

                            console.log('🚀 Preparando respuesta automática con estructura EXACTA de YouChat...');
                            console.log('📋 Headers preservados:', youchatHeaders);
                            
                            // ✅ ENVIAR RESPUESTA VÍA SMTP CON ESTRUCTURA EXACTA
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
                                
                                // ✅ MARCAR COMO LEÍDO USANDO UID (más confiable que seqno)
                                if (emailData.uid) {
                                    await this.markEmailAsRead(emailData.uid);
                                } else {
                                    console.log('⚠️ No se pudo obtener UID para marcar como leído');
                                }
                            } else {
                                console.error(`❌ Falló el envío de la respuesta a: ${senderEmail}`);
                            }

                            processedCount++;
                            if (processedCount === results.length) {
                                console.log('✅ Todos los emails procesados');
                                resolve();
                            }

                        } catch (error) {
                            console.error('❌ Error procesando email:', error);
                            processedCount++;
                            if (processedCount === results.length) resolve();
                        }
                    });
                });

                fetch.once('error', (err) => {
                    console.error('❌ Error en fetch:', err);
                    reject(err);
                });

                fetch.once('end', () => {
                    console.log('✅ Fetch completado');
                    if (processedCount === 0) {
                        resolve();
                    }
                });
            });
        });
    }

    async runBot() {
        if (this.isRunning) {
            console.log('⚠️ Bot ya está en ejecución');
            return;
        }

        this.isRunning = true;
        console.log('🚀 Bot YouChat INICIADO - CONEXIÓN IMAP PERSISTENTE');
        console.log('⏰ Intervalo:', CONFIG.CHECK_INTERVAL, 'ms');
        console.log('📧 Cuenta configurada:', CONFIG.EMAIL_ACCOUNT);

        // ✅ ESTABLECER CONEXIÓN IMAP PERSISTENTE AL INICIAR
        await this.connectIMAP();

        let cycleCount = 0;
        let keepAliveCounter = 0;
        
        while (this.isRunning) {
            try {
                cycleCount++;
                console.log(`\n🔄 CICLO #${cycleCount} - ${new Date().toLocaleTimeString()}`);
                
                // ✅ VERIFICAR Y MANTENER CONEXIÓN IMAP (cada 10 ciclos para evitar spam)
                keepAliveCounter++;
                if (keepAliveCounter >= 10) {
                    await this.keepAliveIMAP();
                    keepAliveCounter = 0;
                }
                
                // ✅ PROCESAR EMAILS SOLO SI LA CONEXIÓN ESTÁ ACTIVA
                if (this.isImapReady) {
                    await this.processUnreadEmails();
                } else {
                    console.log('⚠️ Conexión IMAP no disponible, intentando reconectar...');
                    await this.connectIMAP();
                }
                
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
        if (this.imapConnection) {
            console.log('🔒 Cerrando conexión IMAP persistente...');
            this.imapConnection.end();
            this.imapConnection = null;
            this.isImapReady = false;
            this.currentBox = null;
        }
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
        service: 'YouChat Bot - Conexión IMAP Persistente CORREGIDA',
        version: '2.3.0',
        bot_running: youchatBot.isRunning,
        total_processed: youchatBot.totalProcessed,
        imap_connected: youchatBot.isImapReady,
        check_interval: CONFIG.CHECK_INTERVAL + 'ms',
        features: [
            'Conexión IMAP persistente CORREGIDA', 
            'Buzón en modo LECTURA/ESCRITURA',
            'Monitoreo cada 3 segundos',
            'Detección en tiempo real de nuevos emails',
            'Solo emails NO LEÍDOS', 
            'Marcado como leído usando UID',
            '✅ ESTRUCTURA EXACTA de headers YouChat REAL',
            '✅ msg_id en formato YouChat real: YCchatvideodown797251013093612345',
            '✅ version_contacto: 4 (valor real)',
            '✅ cant_seguidores: 1 (valor real)', 
            '✅ Content-Type: charset=us-ascii (exacto)'
        ]
    });
});

app.get('/health', (req, res) => {
    res.json({
        status: 'healthy',
        timestamp: new Date().toISOString(),
        bot_running: youchatBot.isRunning,
        imap_connected: youchatBot.isImapReady,
        total_processed: youchatBot.totalProcessed,
        memory_usage: `${Math.round(process.memoryUsage().heapUsed / 1024 / 1024)}MB`
    });
});

app.post('/start', (req, res) => {
    if (youchatBot.isRunning) {
        return res.json({ 
            status: 'already_running', 
            message: 'El bot ya está en ejecución',
            total_processed: youchatBot.totalProcessed,
            imap_connected: youchatBot.isImapReady
        });
    }
    youchatBot.runBot();
    res.json({ 
        status: 'started', 
        message: 'Bot iniciado con conexión IMAP persistente CORREGIDA',
        check_interval: CONFIG.CHECK_INTERVAL + 'ms'
    });
});

app.post('/stop', (req, res) => {
    youchatBot.stopBot();
    res.json({ 
        status: 'stopped', 
        message: 'Bot detenido - Conexión IMAP cerrada',
        final_stats: {
            total_processed: youchatBot.totalProcessed
        }
    });
});

app.get('/status', (req, res) => {
    res.json({
        is_running: youchatBot.isRunning,
        imap_connected: youchatBot.isImapReady,
        total_processed: youchatBot.totalProcessed,
        processed_emails_count: youchatBot.processedEmails.size,
        check_interval: CONFIG.CHECK_INTERVAL,
        last_check: new Date().toISOString(),
        mode: 'estructura_exacta_youchat_real'
    });
});

// =============================================================================
// INICIALIZACIÓN
// =============================================================================
app.listen(port, '0.0.0.0', () => {
    console.log(`🎯 Servidor ejecutándose en puerto ${port}`);
    console.log(`🌐 URL: http://0.0.0.0:${port}`);
    console.log('🔧 Iniciando bot automáticamente...');
    console.log('🎯 MODO: ESTRUCTURA EXACTA de headers YouChat REAL');
    console.log('📋 FORMATO msg_id: YCchatvideodown797251013093612345');
    console.log('📋 version_contacto: 4 | cant_seguidores: 1 | charset=us-ascii');
    
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