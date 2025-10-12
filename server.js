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
    CHECK_INTERVAL: 3000
};

// =============================================================================
// CLASE YOUCHAT BOT
// =============================================================================
class YouChatBot {
    constructor() {
        this.isRunning = false;
        this.processedEmails = new Set();
        this.totalProcessed = 0;
        this.imapConnection = null;
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
        return headersYouchat;
    }

    extractSenderEmail(fromHeader) {
        try {
            if (fromHeader.includes('<') && fromHeader.includes('>')) {
                return fromHeader.split('<')[1].split('>')[0].trim();
            }
            return fromHeader.trim();
        } catch (error) {
            return null;
        }
    }

    buildRawYouChatMessage(destinatario, messageId = null, youchatHeaders = {}, asuntoOriginal = null) {
        try {
            let headersString = "";

            if (youchatHeaders && typeof youchatHeaders === 'object') {
                for (const key in youchatHeaders) {
                    if (youchatHeaders[key] && !['Msg_id', 'Chat-Version', 'Pd', 'Sender-Alias', 'From-Alias'].includes(key)) {
                        headersString += `${key}: ${youchatHeaders[key]}\r\n`;
                    }
                }
            }

            const domain = CONFIG.EMAIL_ACCOUNT.split('@')[1];
            headersString += `Message-ID: <auto-reply-${Date.now()}@${domain}>\r\n`;

            if (messageId) {
                const cleanMessageId = messageId.startsWith('<') && messageId.endsWith('>') 
                    ? messageId 
                    : `<${messageId}>`;
                headersString += `In-Reply-To: ${cleanMessageId}\r\n`;
                headersString += `References: ${cleanMessageId}\r\n`;
            }

            headersString += `Msg_id: auto-reply-${Date.now()}\r\n`;
            const chatVersion = youchatHeaders?.['Chat-Version'] || '1.1';
            headersString += `Chat-Version: ${chatVersion}\r\n`;
            
            const pdValue = youchatHeaders?.['Pd'];
            if (pdValue) {
                headersString += `Pd: ${String(pdValue).trim()}\r\n`;
            }

            headersString += `MIME-Version: 1.0\r\n`;
            headersString += `Content-Type: text/plain; charset="UTF-8"\r\n`;
            headersString += `Content-Transfer-Encoding: 8bit\r\n`;

            let asunto = "YouChat";
            if (asuntoOriginal) {
                if (!asuntoOriginal.toLowerCase().startsWith('re:')) {
                    asunto = `Re: ${asuntoOriginal}`;
                } else {
                    asunto = asuntoOriginal;
                }
            }

            const mensajeTexto = "¡Hola! Soy un bot en desarrollo. Pronto podré descargar tus Reels de Instagram.";

            const mailRaw = 
                `From: ${CONFIG.EMAIL_ACCOUNT}\r\n` +
                `To: ${destinatario}\r\n` +
                `Subject: ${asunto}\r\n` +
                headersString +
                `\r\n` +
                `${mensajeTexto}`;

            return mailRaw;

        } catch (error) {
            return null;
        }
    }

    async sendRawResponse(destinatario, messageId = null, youchatHeaders = {}, asuntoOriginal = null) {
        try {
            const rawMessage = this.buildRawYouChatMessage(destinatario, messageId, youchatHeaders, asuntoOriginal);
            if (!rawMessage) return false;

            const transporter = nodemailer.createTransporter({
                host: CONFIG.SMTP_SERVER,
                port: CONFIG.SMTP_PORT,
                secure: false,
                auth: {
                    user: CONFIG.EMAIL_ACCOUNT,
                    pass: CONFIG.EMAIL_PASSWORD
                }
            });

            await transporter.sendMail({
                from: CONFIG.EMAIL_ACCOUNT,
                to: destinatario,
                subject: asuntoOriginal ? `Re: ${asuntoOriginal}` : 'YouChat',
                text: "¡Hola! Soy un bot en desarrollo. Pronto podré descargar tus Reels de Instagram.",
                headers: this.buildCustomHeaders(messageId, youchatHeaders)
            });

            return true;
        } catch (error) {
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
            const imap = new Imap({
                user: CONFIG.EMAIL_ACCOUNT,
                password: CONFIG.EMAIL_PASSWORD,
                host: CONFIG.IMAP_SERVER,
                port: CONFIG.IMAP_PORT,
                tls: true
            });

            imap.once('ready', () => {
                imap.openBox('INBOX', false, (err, box) => {
                    if (err) return reject(err);

                    imap.search(['UNSEEN'], (err, results) => {
                        if (err) return reject(err);

                        if (!results || results.length === 0) {
                            imap.end();
                            return resolve();
                        }

                        const fetch = imap.fetch(results, { bodies: '' });

                        fetch.on('message', (msg, seqno) => {
                            msg.on('body', (stream) => {
                                simpleParser(stream, async (err, parsed) => {
                                    if (err) return;

                                    const emailId = `${seqno}-${parsed.messageId}`;
                                    if (this.processedEmails.has(emailId)) return;

                                    const senderEmail = this.extractSenderEmail(parsed.from.text);
                                    if (!senderEmail) return;

                                    const youchatHeaders = this.extractYouChatHeaders(parsed.headers);
                                    const success = await this.sendRawResponse(
                                        senderEmail,
                                        parsed.messageId,
                                        youchatHeaders,
                                        parsed.subject
                                    );

                                    if (success) {
                                        this.processedEmails.add(emailId);
                                        this.totalProcessed++;
                                    }
                                });
                            });
                        });

                        fetch.once('end', () => {
                            imap.end();
                            resolve();
                        });

                        fetch.once('error', reject);
                    });
                });
            });

            imap.once('error', reject);
            imap.connect();
        });
    }

    async runBot() {
        this.isRunning = true;
        while (this.isRunning) {
            try {
                await this.processUnreadEmails();
                await new Promise(resolve => setTimeout(resolve, CONFIG.CHECK_INTERVAL));
            } catch (error) {
                await new Promise(resolve => setTimeout(resolve, CONFIG.CHECK_INTERVAL));
            }
        }
    }

    stopBot() {
        this.isRunning = false;
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
        service: 'YouChat Bot',
        bot_running: youchatBot.isRunning,
        total_processed: youchatBot.totalProcessed
    });
});

app.get('/health', (req, res) => {
    res.json({ status: 'healthy', timestamp: new Date().toISOString() });
});

app.post('/start', (req, res) => {
    if (youchatBot.isRunning) {
        return res.json({ status: 'already_running' });
    }
    youchatBot.runBot();
    res.json({ status: 'started' });
});

app.post('/stop', (req, res) => {
    youchatBot.stopBot();
    res.json({ status: 'stopped' });
});

app.get('/status', (req, res) => {
    res.json({
        is_running: youchatBot.isRunning,
        total_processed: youchatBot.totalProcessed
    });
});

// =============================================================================
// INICIALIZACIÓN
// =============================================================================
app.listen(port, '0.0.0.0', () => {
    console.log(`Servidor ejecutándose en puerto ${port}`);
    youchatBot.runBot();
});