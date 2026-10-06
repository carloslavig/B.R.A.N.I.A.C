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
            let url = if esperar(porta) {
                WebviewUrl::External(format!("http://127.0.0.1:{porta}/").parse().unwrap())
            } else {
                WebviewUrl::App("index.html".into()) // backend nao subiu: mostra a tela de espera em vez de uma janela vazia
            };
            let janela = WebviewWindowBuilder::new(app, "main", url)
                .title("BRANIAC")
                .inner_size(1120.0, 780.0)
                .min_inner_size(900.0, 620.0)
                .center()
                .visible(!em_segundo_plano)
                .build()?;
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
