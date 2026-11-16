//! fcc: ponte local Anthropic Messages -> provedores gratis do Braniac (providers.json + .env).
//! Uso: fcc [pasta-do-braniac] [porta]   (padrao: pasta atual, porta 8791)
//! Claude Code: ANTHROPIC_BASE_URL=http://127.0.0.1:8791 ANTHROPIC_AUTH_TOKEN=local
mod conv;

use serde_json::{json, Value};
use std::collections::{HashMap, VecDeque};
use std::io::{BufRead, BufReader, Read};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use tiny_http::{Header, Method, Response, Server, StatusCode};

struct Provedor {
    nome: String,
    url: String,
    modelo: String,
    chave: String,
}

fn ler_env(pasta: &str) -> HashMap<String, String> {
    let mut m: HashMap<String, String> = std::env::vars().collect();
    if let Ok(t) = std::fs::read_to_string(format!("{pasta}/.env")) {
        for l in t.lines() {
            if let Some((k, v)) = l.split_once('=') {
                if !l.trim_start().starts_with('#') {
                    m.entry(k.trim().into()).or_insert(v.trim().trim_matches('"').into());
                }
            }
        }
    }
    m
}

/// Provedores online no formato OpenAI com chave presente, na ordem do providers.json.
fn carregar(pasta: &str) -> Vec<Provedor> {
    let env = ler_env(pasta);
    let cfg: Value = std::fs::read_to_string(format!("{pasta}/providers.json"))
        .ok()
        .and_then(|t| serde_json::from_str(&t).ok())
        .unwrap_or(json!({}));
    cfg["cadeia"]
        .as_array()
        .into_iter()
        .flatten()
        .filter(|p| p["tipo"] == "online" && p["api"] == "openai" && p["nome"] != "omniroute")
        .filter_map(|p| {
            let chave = env.get(p["chave_env"].as_str()?).filter(|c| !c.is_empty())?.clone();
            Some(Provedor { nome: p["nome"].as_str()?.into(), url: p["url"].as_str()?.into(), modelo: p["modelo"].as_str()?.into(), chave })
        })
        .collect()
}

type Esfriando = Arc<Mutex<HashMap<String, Instant>>>;

/// Le o streaming do provedor e entrega, sob demanda, os eventos SSE da Anthropic.
struct Sse {
    fonte: BufReader<Box<dyn Read + Send + Sync>>,
    fluxo: conv::Fluxo,
    pronto: VecDeque<u8>,
    fim: bool,
}

impl Read for Sse {
    fn read(&mut self, buf: &mut [u8]) -> std::io::Result<usize> {
        while self.pronto.is_empty() && !self.fim {
            let mut l = String::new();
            let n = self.fonte.read_line(&mut l).unwrap_or(0);
            let dado = l.trim().strip_prefix("data:").map(str::trim);
            let saida = match dado {
                _ if n == 0 => { self.fim = true; self.fluxo.terminar() }
                Some("[DONE]") => { self.fim = true; self.fluxo.terminar() }
                Some(d) => serde_json::from_str::<Value>(d).map(|c| self.fluxo.chunk(&c)).unwrap_or_default(),
                None => String::new(),
            };
            self.pronto.extend(saida.into_bytes());
        }
        let n = buf.len().min(self.pronto.len());
        for b in buf.iter_mut().take(n) {
            *b = self.pronto.pop_front().unwrap();
        }
        Ok(n)
    }
}

fn cabecalho(k: &str, v: &str) -> Header {
    Header::from_bytes(k.as_bytes(), v.as_bytes()).unwrap()
}

fn erro(status: u16, msg: &str) -> Response<std::io::Cursor<Vec<u8>>> {
    let c = json!({"type": "error", "error": {"type": "api_error", "message": msg}}).to_string();
    Response::from_string(c).with_status_code(StatusCode(status)).with_header(cabecalho("Content-Type", "application/json"))
}

fn tentar(provs: &[Provedor], frio: &Esfriando, corpo: &Value, stream: bool) -> Result<(String, ureq::Response), String> {
    let mut ultimo = "nenhum provedor com chave".to_string();
    for p in provs {
        if frio.lock().unwrap().get(&p.nome).is_some_and(|t| t.elapsed() < Duration::from_secs(60)) {
            continue;
        }
        let mut c = corpo.clone();
        c["model"] = json!(p.modelo);
        c["stream"] = json!(stream);
        match ureq::post(&p.url).set("Authorization", &format!("Bearer {}", p.chave)).timeout(Duration::from_secs(180)).send_json(c) {
            Ok(r) => return Ok((p.modelo.clone(), r)),
            Err(e) => {
                let corpo = if let ureq::Error::Status(_, r) = e { r.into_string().unwrap_or_default() } else { e.to_string() };
                eprintln!("fcc: {} falhou: {}", p.nome, corpo.chars().take(300).collect::<String>());
                let e = corpo;
                frio.lock().unwrap().insert(p.nome.clone(), Instant::now());
                ultimo = format!("{}: {e}", p.nome);
            }
        }
    }
    Err(ultimo)
}

fn atender(mut rq: tiny_http::Request, provs: &[Provedor], frio: &Esfriando, n: u64) {
    let caminho = rq.url().split('?').next().unwrap_or("").to_string();
    if rq.method() == &Method::Get {
        let _ = rq.respond(Response::from_string(json!({"ok": true, "provedores": provs.iter().map(|p| &p.nome).collect::<Vec<_>>()}).to_string())
            .with_header(cabecalho("Content-Type", "application/json")));
        return;
    }
    let mut txt = String::new();
    let _ = rq.as_reader().read_to_string(&mut txt);
    let req: Value = match serde_json::from_str(&txt) {
        Ok(v) => v,
        Err(_) => return drop(rq.respond(erro(400, "json invalido"))),
    };
    if caminho.ends_with("/count_tokens") {
        let t = (req.to_string().len() / 4) as u64;
        return drop(rq.respond(Response::from_string(json!({"input_tokens": t}).to_string()).with_header(cabecalho("Content-Type", "application/json"))));
    }
    if !caminho.ends_with("/v1/messages") {
        return drop(rq.respond(erro(404, "rota desconhecida")));
    }
    let id = format!("msg_fcc{n}");
    let stream = req["stream"].as_bool().unwrap_or(false);
    let corpo = conv::pedido(&req, std::env::var("FCC_MAX_FERRAMENTAS").ok().and_then(|v| v.parse().ok()).unwrap_or(40));
    let (modelo, r) = match tentar(provs, frio, &corpo, stream) {
        Ok(x) => x,
        Err(e) => return drop(rq.respond(erro(529, &format!("todos os provedores falharam ({e})")))),
    };
    if stream {
        let sse = Sse { fonte: BufReader::new(Box::new(r.into_reader())), fluxo: conv::Fluxo::novo(&modelo, &id), pronto: VecDeque::new(), fim: false };
        let resp = Response::new(StatusCode(200), vec![cabecalho("Content-Type", "text/event-stream"), cabecalho("Cache-Control", "no-cache")], sse, None, None);
        let _ = rq.respond(resp);
    } else {
        let v: Value = r.into_json().unwrap_or(json!({}));
        let _ = rq.respond(Response::from_string(conv::resposta(&v, &modelo, &id).to_string()).with_header(cabecalho("Content-Type", "application/json")));
    }
}

fn main() {
    let a: Vec<String> = std::env::args().collect();
    let pasta = a.get(1).cloned().unwrap_or(".".into());
    let porta = a.get(2).cloned().unwrap_or("8791".into());
    let provs = Arc::new(carregar(&pasta));
    if provs.is_empty() {
        eprintln!("fcc: nenhum provedor com chave em {pasta}/providers.json + .env");
        std::process::exit(2);
    }
    let srv = Server::http(format!("127.0.0.1:{porta}")).unwrap_or_else(|e| { eprintln!("fcc: porta {porta}: {e}"); std::process::exit(3) });
    eprintln!("fcc: http://127.0.0.1:{porta} com {} provedores: {}", provs.len(), provs.iter().map(|p| p.nome.as_str()).collect::<Vec<_>>().join(", "));
    let frio: Esfriando = Arc::default();
    let mut n = 0u64;
    for rq in srv.incoming_requests() {
        n += 1;
        let (p, f) = (provs.clone(), frio.clone());
        std::thread::spawn(move || atender(rq, &p, &f, n));
    }
}
