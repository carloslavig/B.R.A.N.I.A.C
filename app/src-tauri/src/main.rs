// BRANIAC: UMA janela, UM programa. Esta casca sobe o backend (Python) escondido, espera ele responder e mostra a tela local.
// Fechar a janela so a ESCONDE: o assistente continua na bandeja (Telegram, modo jogo, voz). "Sair" no menu do icone encerra tudo.
// O navegador das contas de IA (ChatGPT/Gemini/WhatsApp) e controlado pelo backend e fica fora da vista.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::net::{SocketAddr, TcpListener, TcpStream};
#[cfg(windows)]
use std::os::windows::process::CommandExt;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};
use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Manager, RunEvent, WebviewUrl, WebviewWindowBuilder, WindowEvent};

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

/// Windows: processo sem janela de console. macOS/Linux: nada a fazer (nao existe console avulso).
#[cfg(windows)]
fn sem_janela(cmd: &mut Command) -> &mut Command {
    cmd.creation_flags(CREATE_NO_WINDOW)
}
#[cfg(not(windows))]
fn sem_janela(cmd: &mut Command) -> &mut Command {
    cmd
}

#[cfg(windows)]
const BACKEND_EXE: &str = "braniac-core.exe";
#[cfg(not(windows))]
const BACKEND_EXE: &str = "braniac-core";
#[cfg(windows)]
const PYTHON: &str = "python";
#[cfg(not(windows))]
const PYTHON: &str = "python3";

struct Backend(Mutex<Option<Child>>);

fn porta_livre() -> u16 {
    TcpListener::bind("127.0.0.1:0").expect("sem porta livre").local_addr().unwrap().port()
}

/// Release: usa o `braniac-core.exe` empacotado ao lado do app. Desenvolvimento: roda o Python do repositorio.
fn subir_backend(porta: u16) -> std::io::Result<Child> {
    let exe = std::env::current_exe()?;
    let dir = exe.parent().unwrap().to_path_buf();
    let empacotado = dir.join(BACKEND_EXE);
    let mut cmd = if empacotado.exists() {
        let mut c = Command::new(empacotado);
        c.arg(porta.to_string());
        c
    } else {
        let seed = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("..").join("..").join("seed");
        let mut c = Command::new(PYTHON);
        c.args(["-m", "braniac_seed.servidor", &porta.to_string()]).current_dir(seed);
        c
    };
    cmd.stdin(Stdio::null()).stdout(Stdio::null()).stderr(Stdio::null());
    sem_janela(&mut cmd).spawn()
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
    // mesma pasta que o backend usa (paths.py): %LOCALAPPDATA%\BRANIAC-dados no Windows, ~/Library/Application Support/BRANIAC-dados no macOS
    #[cfg(windows)]
    let pasta = std::path::Path::new(&std::env::var("LOCALAPPDATA").ok()?).join("BRANIAC-dados");
    #[cfg(not(windows))]
    let pasta = std::path::Path::new(&std::env::var("HOME").ok()?).join("Library").join("Application Support").join("BRANIAC-dados");
    let txt = std::fs::read_to_string(pasta.join("perfil.json")).ok()?;
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
        // macOS: clicar no icone do Dock com a janela escondida traz o assistente de volta
        #[cfg(target_os = "macos")]
        if let RunEvent::Reopen { .. } = evento {
            mostrar(handle);
            return;
        }
        if let RunEvent::Exit = evento {
            if let Some(mut filho) = handle.state::<Backend>().0.lock().unwrap().take() {
                // o backend empacotado (onefile) tem processo filho: encerra a arvore inteira para nao sobrar servidor orfao
                #[cfg(windows)]
                {
                    let _ = sem_janela(Command::new("taskkill").args(["/PID", &filho.id().to_string(), "/T", "/F"])).status();
                }
                #[cfg(not(windows))]
                {
                    // SIGTERM primeiro: o bootloader do PyInstaller repassa o sinal ao processo Python (SIGKILL deixaria o filho orfao)
                    let _ = Command::new("kill").args(["-TERM", &filho.id().to_string()]).status();
                    std::thread::sleep(Duration::from_millis(600));
                }
                let _ = filho.kill();
            }
        }
    });
}
