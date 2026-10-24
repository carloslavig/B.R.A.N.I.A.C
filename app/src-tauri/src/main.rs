// BRANIAC: UMA janela, UM programa. Esta casca sobe o backend (Python) escondido, espera ele responder e mostra a tela local.
// Fechar a janela so a ESCONDE: o assistente continua na bandeja (Telegram, modo jogo, voz). "Sair" no menu do icone encerra tudo.
// O navegador das contas de IA (ChatGPT/Gemini/WhatsApp) e controlado pelo backend e fica fora da vista.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::net::{SocketAddr, TcpListener, TcpStream};
use std::os::windows::process::CommandExt;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};
use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Manager, RunEvent, WebviewUrl, WebviewWindowBuilder, WindowEvent};

const CREATE_NO_WINDOW: u32 = 0x0800_0000;

struct Backend(Mutex<Option<Child>>);

fn porta_livre() -> u16 {
    TcpListener::bind("127.0.0.1:0").expect("sem porta livre").local_addr().unwrap().port()
}

/// Release: usa o `braniac-core.exe` empacotado ao lado do app. Desenvolvimento: roda o Python do repositorio.
fn subir_backend(porta: u16) -> std::io::Result<Child> {
    let exe = std::env::current_exe()?;
    let dir = exe.parent().unwrap().to_path_buf();
    let empacotado = dir.join("braniac-core.exe");
    let mut cmd = if empacotado.exists() {
        let mut c = Command::new(empacotado);
        c.arg(porta.to_string());
        c
    } else {
        let seed = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("..").join("..").join("seed");
        let mut c = Command::new("python");
        c.args(["-m", "braniac_seed.servidor", &porta.to_string()]).current_dir(seed);
        c
    };
    cmd.stdin(Stdio::null()).stdout(Stdio::null()).stderr(Stdio::null()).creation_flags(CREATE_NO_WINDOW);
    cmd.spawn()
}

fn esperar(porta: u16) -> bool {
    let fim = Instant::now() + Duration::from_secs(30);
    let addr: SocketAddr = format!("127.0.0.1:{porta}").parse().unwrap();
    while Instant::now() < fim {
        if TcpStream::connect_timeout(&addr, Duration::from_millis(300)).is_ok() {
            return true;
        }
        std::thread::sleep(Duration::from_millis(250));
    }
    false
}

/// GET /api/sinal no backend (o assistente foi chamado pelo nome?). Devolve o corpo da resposta.
fn sinal(porta: u16) -> String {
    use std::io::{Read, Write};
    let addr: SocketAddr = format!("127.0.0.1:{porta}").parse().unwrap();
    let Ok(mut s) = TcpStream::connect_timeout(&addr, Duration::from_millis(800)) else {
        return String::new();
    };
    let _ = s.set_read_timeout(Some(Duration::from_secs(3)));
    let _ = s.write_all(format!("GET /api/sinal HTTP/1.0\r\nHost: 127.0.0.1:{porta}\r\n\r\n").as_bytes());
    let mut r = String::new();
    let _ = s.read_to_string(&mut r);
    r
}

/// Nome e cor que a pessoa escolheu (perfil local), para a tela de carregamento ja sair com o jeito dela.
fn aparencia() -> Option<(String, String)> {
    let base = std::env::var("LOCALAPPDATA").ok()?;
    let txt = std::fs::read_to_string(std::path::Path::new(&base).join("BRANIAC-dados").join("perfil.json")).ok()?;
    let v: serde_json::Value = serde_json::from_str(txt.trim_start_matches('\u{feff}')).ok()?;
    let nome = v.get("nome_assistente")?.as_str()?.to_string();
    let cor = v.get("cor").and_then(|c| c.as_str()).unwrap_or("#2fe3ff").to_string();
    Some((nome, cor))
}

fn mostrar(app: &AppHandle) {
    if let Some(j) = app.get_webview_window("main") {
        let _ = j.show();
        let _ = j.unminimize();
        let _ = j.set_focus();
    }
}

fn main() {
    let porta = porta_livre();
    let em_segundo_plano = std::env::args().any(|a| a == "--background");
    let app = tauri::Builder::default()
        // so UMA copia: abrir de novo (atalho, iniciar com o Windows) apenas traz a janela da copia que ja esta rodando
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| mostrar(app)))
        .manage(Backend(Mutex::new(None)))
        .setup(move |app| {
            let filho = subir_backend(porta)?;
            *app.state::<Backend>().0.lock().unwrap() = Some(filho);
            // v0.7: abre JA com a tela de carregamento (ui-loader) e troca para o assistente quando o backend responder
            let janela = WebviewWindowBuilder::new(app, "main", WebviewUrl::App("index.html".into()))
                .title("BRANIAC")
                .inner_size(1120.0, 780.0)
                .min_inner_size(900.0, 620.0)
                .center()
                .visible(!em_segundo_plano)
                .build()?;
            let j3 = janela.clone();
            std::thread::spawn(move || {
                let p = |n: u32, t: &str| {
                    let _ = j3.eval(&format!("window.progresso && progresso({n}, '{t}')"));
                };
                std::thread::sleep(Duration::from_millis(600));
                if let Some((nome, cor)) = aparencia() {
                    let _ = j3.eval(&format!("window.tema && tema({})", serde_json::json!({"nome": nome, "cor": cor})));
                }
                p(20, "Ligando o assistente");
                if !esperar(porta) {
                    p(100, "O assistente nao ligou: feche e abra de novo");
                    return;
                }
                p(100, "Online");
                std::thread::sleep(Duration::from_millis(700));
                let _ = j3.navigate(format!("http://127.0.0.1:{porta}/").parse().unwrap());
                loop {
                    // chamaram o assistente pelo nome ('<nome>, ta acordado?'): a janela aparece na tela de voz
                    std::thread::sleep(Duration::from_secs(1));
                    if sinal(porta).contains("\"mostrar\": true") {
                        let _ = j3.show();
                        let _ = j3.unminimize();
                        let _ = j3.set_focus();
                        let _ = j3.eval("window.aba && aba('voz')");
                    }
                }
            });
            let j2 = janela.clone();
            janela.on_window_event(move |ev| {
                if let WindowEvent::CloseRequested { api, .. } = ev {
                    api.prevent_close(); // fechar = esconder; o assistente continua na bandeja
                    let _ = j2.hide();
                }
            });

            let abrir = MenuItem::with_id(app, "abrir", "Abrir BRANIAC", true, None::<&str>)?;
            let sair = MenuItem::with_id(app, "sair", "Sair (para o assistente e o Telegram)", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&abrir, &sair])?;
            TrayIconBuilder::new()
                .icon(app.default_window_icon().unwrap().clone())
                .tooltip("BRANIAC")
                .menu(&menu)
                .show_menu_on_left_click(false)
                .on_menu_event(|app, ev| match ev.id.as_ref() {
                    "abrir" => mostrar(app),
                    "sair" => app.exit(0),
                    _ => {}
                })
                .on_tray_icon_event(|tray, ev| {
                    if let TrayIconEvent::Click { button: MouseButton::Left, button_state: MouseButtonState::Up, .. } = ev {
                        mostrar(tray.app_handle());
                    }
                })
                .build(app)?;
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("erro ao iniciar o BRANIAC");

    app.run(|handle, evento| {
        if let RunEvent::Exit = evento {
            if let Some(mut filho) = handle.state::<Backend>().0.lock().unwrap().take() {
                // o backend empacotado (onefile) tem processo filho: encerra a arvore inteira para nao sobrar servidor orfao
                let _ = Command::new("taskkill").args(["/PID", &filho.id().to_string(), "/T", "/F"]).creation_flags(CREATE_NO_WINDOW).status();
                let _ = filho.kill();
            }
        }
    });
}
