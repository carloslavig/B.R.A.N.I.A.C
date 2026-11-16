//! Anthropic Messages <-> OpenAI chat completions (so JSON, sem rede).
use serde_json::{json, Value};

fn texto_de(c: &Value) -> String {
    match c {
        Value::String(s) => s.clone(),
        Value::Array(a) => a
            .iter()
            .filter_map(|b| match b["type"].as_str() {
                Some("text") => b["text"].as_str().map(String::from),
                Some("image") => Some("[imagem]".into()),
                _ => None,
            })
            .collect::<Vec<_>>()
            .join("\n"),
        _ => String::new(),
    }
}

/// Pedido da Anthropic -> corpo OpenAI chat (sem `model`, que cada provedor poe o seu).
pub fn pedido(req: &Value, maximo_ferramentas: usize) -> Value {
    let mut msgs: Vec<Value> = Vec::new();
    let sistema = texto_de(&req["system"]);
    if !sistema.is_empty() {
        msgs.push(json!({"role": "system", "content": sistema}));
    }
    for m in req["messages"].as_array().into_iter().flatten() {
        let blocos = match &m["content"] {
            Value::Array(a) => a.clone(),
            Value::String(s) => vec![json!({"type": "text", "text": s})],
            _ => vec![],
        };
        if m["role"] == "assistant" {
            let texto = texto_de(&Value::Array(blocos.clone()));
            let chamadas: Vec<Value> = blocos
                .iter()
                .filter(|b| b["type"] == "tool_use")
                .map(|b| json!({"id": b["id"], "type": "function",
                    "function": {"name": b["name"], "arguments": b["input"].to_string()}}))
                .collect();
            let mut o = json!({"role": "assistant", "content": texto});
            if !chamadas.is_empty() {
                o["tool_calls"] = Value::Array(chamadas);
            }
            msgs.push(o);
        } else {
            // tool_result vira mensagem "tool" e vai ANTES do texto do usuario
            for b in blocos.iter().filter(|b| b["type"] == "tool_result") {
                msgs.push(json!({"role": "tool", "tool_call_id": b["tool_use_id"], "content": texto_de(&b["content"])}));
            }
            let resto: Vec<Value> = blocos.into_iter().filter(|b| b["type"] != "tool_result").collect();
            let texto = texto_de(&Value::Array(resto));
            if !texto.is_empty() {
                msgs.push(json!({"role": "user", "content": texto}));
            }
        }
    }
    let mut o = json!({"messages": msgs});
    if let Some(n) = req["max_tokens"].as_u64() {
        o["max_tokens"] = json!(n.min(8192)); // Groq recusa valores grandes
    }
    for k in ["temperature", "top_p"] {
        if !req[k].is_null() {
            o[k] = req[k].clone();
        }
    }
    if let Some(s) = req["stop_sequences"].as_array().filter(|s| !s.is_empty()) {
        o["stop"] = Value::Array(s.clone());
    }
    if let Some(ts) = req["tools"].as_array().filter(|t| !t.is_empty()) {
        // limites dos provedores gratis: Groq aceita ate 128 ferramentas e a cota de tokens e curta.
        // Fica com as nativas (Read, Edit, Bash...) antes das mcp__ e corta as descricoes.
        let mut ord: Vec<&Value> = ts.iter().collect();
        ord.sort_by_key(|t| t["name"].as_str().is_some_and(|n| n.starts_with("mcp__")));
        let curta = |d: &Value| -> String { d.as_str().unwrap_or("").chars().take(400).collect() };
        o["tools"] = Value::Array(
            ord.into_iter()
                .take(maximo_ferramentas)
                .map(|t| json!({"type": "function", "function": {
                    "name": t["name"], "description": curta(&t["description"]),
                    "parameters": if t["input_schema"].is_null() { json!({"type": "object", "properties": {}}) } else { t["input_schema"].clone() }}}))
                .collect(),
        );
        o["tool_choice"] = match req["tool_choice"]["type"].as_str() {
            Some("any") => json!("required"),
            Some("none") => json!("none"),
            Some("tool") => json!({"type": "function", "function": {"name": req["tool_choice"]["name"]}}),
            _ => json!("auto"),
        };
    }
    o
}

pub fn parada(finish: &str) -> &'static str {
    match finish {
        "tool_calls" | "function_call" => "tool_use",
        "length" => "max_tokens",
        _ => "end_turn",
    }
}

fn args(s: &str) -> Value {
    serde_json::from_str(s).unwrap_or_else(|_| json!({}))
}

/// Resposta OpenAI (sem streaming) -> mensagem Anthropic.
pub fn resposta(r: &Value, modelo: &str, id: &str) -> Value {
    let esc = &r["choices"][0];
    let mut blocos: Vec<Value> = Vec::new();
    if let Some(t) = esc["message"]["content"].as_str().filter(|t| !t.is_empty()) {
        blocos.push(json!({"type": "text", "text": t}));
    }
    for (i, c) in esc["message"]["tool_calls"].as_array().into_iter().flatten().enumerate() {
        blocos.push(json!({"type": "tool_use", "id": c["id"].as_str().map(String::from).unwrap_or(format!("toolu_{i}")),
            "name": c["function"]["name"], "input": args(c["function"]["arguments"].as_str().unwrap_or("{}"))}));
    }
    if blocos.is_empty() {
        blocos.push(json!({"type": "text", "text": ""}));
    }
    json!({"id": id, "type": "message", "role": "assistant", "model": modelo, "content": blocos,
        "stop_reason": parada(esc["finish_reason"].as_str().unwrap_or("stop")), "stop_sequence": null,
        "usage": {"input_tokens": r["usage"]["prompt_tokens"].as_u64().unwrap_or(0), "output_tokens": r["usage"]["completion_tokens"].as_u64().unwrap_or(0)}})
}

/// Converte o streaming OpenAI (um chunk por vez) nos eventos SSE da Anthropic.
pub struct Fluxo {
    modelo: String,
    id: String,
    iniciado: bool,
    prox: usize,
    texto: Option<usize>,
    ferramentas: Vec<(u64, usize)>, // (indice no provedor, indice Anthropic)
    aberto: Option<usize>,
    saida: u64,
    fim: Option<String>,
}

fn ev(nome: &str, d: Value) -> String {
    format!("event: {nome}\ndata: {d}\n\n")
}

impl Fluxo {
    pub fn novo(modelo: &str, id: &str) -> Self {
        Fluxo { modelo: modelo.into(), id: id.into(), iniciado: false, prox: 0, texto: None, ferramentas: vec![], aberto: None, saida: 0, fim: None }
    }

    fn inicio(&mut self, o: &mut String) {
        if !self.iniciado {
            self.iniciado = true;
            o.push_str(&ev("message_start", json!({"type": "message_start", "message": {"id": self.id, "type": "message", "role": "assistant",
                "model": self.modelo, "content": [], "stop_reason": null, "stop_sequence": null, "usage": {"input_tokens": 0, "output_tokens": 0}}})));
        }
    }

    fn fechar(&mut self, o: &mut String) {
        if let Some(i) = self.aberto.take() {
            o.push_str(&ev("content_block_stop", json!({"type": "content_block_stop", "index": i})));
        }
    }

    /// `chunk` e o JSON de um `data:` do provedor.
    pub fn chunk(&mut self, c: &Value) -> String {
        let mut o = String::new();
        self.inicio(&mut o);
        let esc = &c["choices"][0];
        if let Some(t) = esc["delta"]["content"].as_str().filter(|t| !t.is_empty()) {
            let i = match self.texto {
                Some(i) if self.aberto == Some(i) => i,
                _ => {
                    self.fechar(&mut o);
                    let i = self.prox;
                    self.prox += 1;
                    self.texto = Some(i);
                    self.aberto = Some(i);
                    o.push_str(&ev("content_block_start", json!({"type": "content_block_start", "index": i, "content_block": {"type": "text", "text": ""}})));
                    i
                }
            };
            self.saida += (t.len() as u64 / 4).max(1);
            o.push_str(&ev("content_block_delta", json!({"type": "content_block_delta", "index": i, "delta": {"type": "text_delta", "text": t}})));
        }
        for tc in esc["delta"]["tool_calls"].as_array().into_iter().flatten() {
            let up = tc["index"].as_u64().unwrap_or(0);
            let i = match self.ferramentas.iter().find(|(u, _)| *u == up) {
                Some((_, i)) => *i,
                None => {
                    self.fechar(&mut o);
                    let i = self.prox;
                    self.prox += 1;
                    self.ferramentas.push((up, i));
                    self.aberto = Some(i);
                    let id = tc["id"].as_str().map(String::from).unwrap_or(format!("toolu_{up}"));
                    o.push_str(&ev("content_block_start", json!({"type": "content_block_start", "index": i,
                        "content_block": {"type": "tool_use", "id": id, "name": tc["function"]["name"].as_str().unwrap_or(""), "input": {}}})));
                    i
                }
            };
            if let Some(a) = tc["function"]["arguments"].as_str().filter(|a| !a.is_empty()) {
                self.saida += (a.len() as u64 / 4).max(1);
                o.push_str(&ev("content_block_delta", json!({"type": "content_block_delta", "index": i, "delta": {"type": "input_json_delta", "partial_json": a}})));
            }
        }
        if let Some(f) = esc["finish_reason"].as_str() {
            self.fim = Some(f.into());
        }
        if let Some(n) = c["usage"]["completion_tokens"].as_u64() {
            self.saida = n;
        }
        o
    }

    pub fn terminar(&mut self) -> String {
        let mut o = String::new();
        self.inicio(&mut o);
        if self.prox == 0 {
            // resposta vazia: o Claude Code espera ao menos um bloco de texto
            o.push_str(&ev("content_block_start", json!({"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}})));
            self.aberto = Some(0);
        }
        self.fechar(&mut o);
        let parada = if !self.ferramentas.is_empty() { "tool_use" } else { parada(self.fim.as_deref().unwrap_or("stop")) };
        o.push_str(&ev("message_delta", json!({"type": "message_delta", "delta": {"stop_reason": parada, "stop_sequence": null}, "usage": {"output_tokens": self.saida}})));
        o.push_str(&ev("message_stop", json!({"type": "message_stop"})));
        o
    }
}

#[cfg(test)]
mod testes {
    use super::*;

    #[test]
    fn pedido_com_ferramenta_e_resultado() {
        let r = json!({"system": [{"type": "text", "text": "seja breve"}], "max_tokens": 50,
            "tools": [{"name": "ler", "description": "d", "input_schema": {"type": "object"}}], "tool_choice": {"type": "any"},
            "messages": [
                {"role": "user", "content": "oi"},
                {"role": "assistant", "content": [{"type": "text", "text": "vou ler"}, {"type": "tool_use", "id": "t1", "name": "ler", "input": {"a": 1}}]},
                {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": [{"type": "text", "text": "ok"}]}, {"type": "text", "text": "e agora?"}]}]});
        let o = pedido(&r, 40);
        let m = o["messages"].as_array().unwrap();
        assert_eq!(m[0]["role"], "system");
        assert_eq!(m[2]["tool_calls"][0]["function"]["arguments"], "{\"a\":1}");
        assert_eq!(m[3]["role"], "tool");
        assert_eq!(m[3]["content"], "ok");
        assert_eq!(m[4]["content"], "e agora?");
        assert_eq!(o["tool_choice"], "required");
        assert_eq!(o["tools"][0]["function"]["name"], "ler");
    }

    #[test]
    fn resposta_com_ferramenta() {
        let r = json!({"choices": [{"message": {"content": null, "tool_calls": [{"id": "c1", "function": {"name": "ler", "arguments": "{\"x\":2}"}}]}, "finish_reason": "tool_calls"}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 4}});
        let a = resposta(&r, "m", "msg_1");
        assert_eq!(a["stop_reason"], "tool_use");
        assert_eq!(a["content"][0]["input"]["x"], 2);
        assert_eq!(a["usage"]["output_tokens"], 4);
    }

    #[test]
    fn fluxo_texto_depois_ferramenta() {
        let mut f = Fluxo::novo("m", "msg_1");
        let mut s = String::new();
        s += &f.chunk(&json!({"choices": [{"delta": {"content": "ola"}}]}));
        s += &f.chunk(&json!({"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "function": {"name": "ler", "arguments": "{\"x\""}}]}}]}));
        s += &f.chunk(&json!({"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": ":1}"}}]}, "finish_reason": "tool_calls"}]}));
        s += &f.terminar();
        assert!(s.starts_with("event: message_start"));
        assert!(s.contains("\"type\":\"text_delta\""));
        assert!(s.contains("\"type\":\"tool_use\""));
        assert_eq!(s.matches("event: content_block_stop").count(), 2);
        assert!(s.contains("\"stop_reason\":\"tool_use\""));
        assert!(s.trim_end().ends_with("\"type\":\"message_stop\"}"));
    }

    #[test]
    fn fluxo_vazio_ainda_e_valido() {
        let mut f = Fluxo::novo("m", "msg_1");
        let s = f.terminar();
        assert!(s.contains("content_block_start") && s.contains("end_turn"));
    }
}
