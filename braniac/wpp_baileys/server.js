// WhatsApp sem Chrome: protocolo direto (Baileys), so em 127.0.0.1. Quem fala com isto e o Python (wpp_direto.py).
const http = require("http");
const path = require("path");
const fs = require("fs");
const pino = require("pino");
const QR = require("qrcode");
const { default: makeWASocket, useMultiFileAuthState, DisconnectReason, fetchLatestBaileysVersion, downloadMediaMessage } = require("@whiskeysockets/baileys");

const PORTA = parseInt(process.env.WPP_PORTA || "8766", 10);
const AUTH = process.env.WPP_AUTH || path.join(__dirname, "..", "data", "wpp_baileys_auth");
const log = pino({ level: "silent" });

let sock = null;
let est = { estado: "ocioso", qr: null, eu: null };     // so gera QR quando o Dono clica em Conectar (o QR expira em ~1 min)
let ativo = false;
const caixa = [];            // ultimas mensagens recebidas/enviadas (memoria; o Python guarda o que importa)
let seq = 0;

function jid(para) {
  if (para.includes("@")) return para;
  return para.replace(/\D/g, "") + "@s.whatsapp.net";
}

function texto(m) {
  const x = m.message || {};
  return x.conversation || x.extendedTextMessage?.text || x.imageMessage?.caption || x.documentMessage?.caption || "";
}

function tipo(m) {
  const x = m.message || {};
  if (x.audioMessage) return "audio";
  if (x.imageMessage) return "imagem";
  if (x.documentMessage) return "documento";
  if (x.videoMessage) return "video";
  return "texto";
}

async function conectar() {
  ativo = true;
  const { state, saveCreds } = await useMultiFileAuthState(AUTH);
  const { version } = await fetchLatestBaileysVersion().catch(() => ({ version: undefined }));
  sock = makeWASocket({ auth: state, version, logger: log, printQRInTerminal: false, browser: ["Braniac", "Chrome", "1.0"], markOnlineOnConnect: false });
  sock.ev.on("creds.update", saveCreds);
  sock.ev.on("connection.update", async (u) => {
    if (u.qr) { est = { ...est, estado: "qr", qr: await QR.toDataURL(u.qr) }; }
    if (u.connection === "open") { est = { estado: "conectado", qr: null, eu: sock.user?.id || null }; }
    if (u.connection) fs.appendFileSync(path.join(__dirname, "..", "data", "wpp_baileys.log"), new Date().toISOString() + " " + u.connection + " " + (u.lastDisconnect?.error?.output?.statusCode || "") + " " + (u.lastDisconnect?.error?.message || "") + String.fromCharCode(10));
    if (u.connection === "close") {
      const cod = u.lastDisconnect?.error?.output?.statusCode;
      if (cod === DisconnectReason.restartRequired) { setTimeout(() => conectar().catch(() => {}), 500); return; }   // 515: normal logo apos ler o QR, o WhatsApp pede para reconectar
      const pareado = !!state.creds.registered;
      if (cod === DisconnectReason.loggedOut) { fs.rmSync(AUTH, { recursive: true, force: true }); }
      if (!pareado || cod === DisconnectReason.loggedOut) { ativo = false; est = { estado: "ocioso", qr: null, eu: null }; return; }   // QR expirou sem escanear: espera novo clique
      est = { estado: "desconectado", qr: null, eu: null };
      setTimeout(() => conectar().catch(() => {}), 3000);       // vigia: ja pareado, reconecta sozinho
    }
  });
  sock.ev.on("messages.upsert", ({ messages }) => {
    for (const m of messages) {
      if (!m.message) continue;
      caixa.push({ seq: ++seq, id: m.key.id, de: m.key.remoteJid, minha: !!m.key.fromMe, nome: m.pushName || "", tipo: tipo(m), texto: texto(m), ts: Number(m.messageTimestamp) || Math.floor(Date.now() / 1000), _m: m });
      if (caixa.length > 500) caixa.shift();
    }
  });
}

function corpo(req) {
  return new Promise((ok) => { let b = ""; req.on("data", (c) => (b += c)); req.on("end", () => { try { ok(JSON.parse(b || "{}")); } catch { ok({}); } }); });
}

http.createServer(async (req, res) => {
  const u = new URL(req.url, "http://x");
  const out = (c, o) => { res.writeHead(c, { "content-type": "application/json" }); res.end(JSON.stringify(o)); };
  try {
    if (u.pathname === "/status") return out(200, est);
    if (u.pathname === "/inbox") {
      const desde = parseInt(u.searchParams.get("desde") || "0", 10);
      return out(200, caixa.filter((m) => m.seq > desde).map(({ _m, ...r }) => r));
    }
    if (u.pathname === "/conectar") { if (!ativo) await conectar(); return out(200, { ok: true }); }
    if (est.estado !== "conectado") return out(503, { erro: "whatsapp nao conectado", estado: est.estado });
    const b = req.method === "POST" ? await corpo(req) : {};
    if (u.pathname === "/enviar") { const r = await sock.sendMessage(jid(b.para), { text: b.texto }); return out(200, { ok: true, id: r.key.id }); }
    if (u.pathname === "/enviar_arquivo") {
      const buf = fs.readFileSync(b.caminho);
      const msg = b.voz ? { audio: buf, ptt: true, mimetype: "audio/ogg; codecs=opus" }
        : /\.(png|jpe?g|webp)$/i.test(b.caminho) ? { image: buf, caption: b.legenda || "" }
        : { document: buf, fileName: path.basename(b.caminho), mimetype: "application/octet-stream", caption: b.legenda || "" };
      const r = await sock.sendMessage(jid(b.para), msg);
      return out(200, { ok: true, id: r.key.id });
    }
    if (u.pathname === "/baixar") {          // salva a midia de uma mensagem recebida (id) em `destino`
      const m = caixa.find((x) => x.id === b.id);
      if (!m) return out(404, { erro: "mensagem nao esta mais na memoria" });
      const buf = await downloadMediaMessage(m._m, "buffer", {}, { logger: log, reuploadRequest: sock.updateMediaMessage });
      fs.writeFileSync(b.destino, buf);
      return out(200, { ok: true, bytes: buf.length });
    }
    if (u.pathname === "/sair") { await sock.logout(); return out(200, { ok: true }); }
    out(404, { erro: "rota" });
  } catch (e) { out(500, { erro: String(e.message || e).slice(0, 200) }); }
}).listen(PORTA, "127.0.0.1", () => { if (fs.existsSync(path.join(AUTH, "creds.json"))) conectar().catch((e) => { est = { estado: "erro", qr: null, eu: null, erro: String(e) }; }); });
