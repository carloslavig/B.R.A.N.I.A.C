"""Controle da VM Windows isolada do Braniac (VirtualBox, sem janela).

Ambiente fechado: rede NAT, sem pasta compartilhada, sem area de transferencia e
sem arrastar-e-soltar. So entra/sai o que o Braniac copia de proposito (copiar_para/copiar_de).
Login do Dono dentro da VM (WhatsApp, Google, IAs) e sempre feito por ele.
"""
import re
import secrets
import subprocess
from pathlib import Path

VBOX = r"C:\Program Files\Oracle\VirtualBox\VBoxManage.exe"
NOME = "BraniacWin"
PASTA = Path(r"E:\BraniacVM")
DADOS = Path(__file__).parent / "data" / "vm"
USUARIO = "braniac"
SNAP_LIMPO = "limpo"


def _vb(*args, timeout=120):
    try:
        r = subprocess.run([VBOX, *map(str, args)], capture_output=True, text=True, timeout=timeout,
                           creationflags=0x08000000)  # sem janela de console
    except subprocess.TimeoutExpired:
        return 124, "tempo esgotado"
    return r.returncode, (r.stdout + r.stderr).strip()


def _arq_senha():
    _senha()
    return DADOS / "senha.txt"


def _senha():
    DADOS.mkdir(parents=True, exist_ok=True)
    f = DADOS / "senha.txt"
    if not f.exists():
        f.write_text(secrets.token_urlsafe(14), encoding="utf-8")
    return f.read_text(encoding="utf-8").strip()


def estado():
    """'inexistente', 'poweroff', 'running', 'saved', 'paused'..."""
    rc, out = _vb("showvminfo", NOME, "--machinereadable")
    if rc:
        return "inexistente"
    m = re.search(r'^VMState="([^"]+)"', out, re.M)
    return m.group(1) if m else "desconhecido"


def criar(iso, ram_mb=4096, cpus=2, disco_mb=51200):
    """Cria a VM e instala o Windows sozinho (unattended). Idempotente: nao recria se existir."""
    if estado() != "inexistente":
        return "A VM ja existe."
    iso = str(iso)
    PASTA.mkdir(parents=True, exist_ok=True)
    passos = [
        ("createvm", "--name", NOME, "--ostype", "Windows11_64", "--register", "--basefolder", PASTA),
        ("modifyvm", NOME, "--memory", ram_mb, "--cpus", cpus, "--vram", 128, "--firmware", "efi",
         "--tpm-type", "2.0", "--graphicscontroller", "vboxsvga",
         "--nic1", "nat", "--clipboard-mode", "disabled", "--draganddrop", "disabled",
         "--audio-driver", "none", "--usb-ehci", "off", "--usb-xhci", "off"),
        ("createmedium", "disk", "--filename", PASTA / NOME / f"{NOME}.vdi", "--size", disco_mb, "--variant", "Standard"),
        ("storagectl", NOME, "--name", "SATA", "--add", "sata", "--controller", "IntelAhci"),
        ("storageattach", NOME, "--storagectl", "SATA", "--port", 0, "--device", 0, "--type", "hdd",
         "--medium", PASTA / NOME / f"{NOME}.vdi"),
        ("unattended", "install", NOME, f"--iso={iso}", f"--user={USUARIO}", f"--passwordfile={_arq_senha()}",
         "--full-user-name=Braniac", "--install-additions", "--locale=pt_BR", "--country=BR",
         "--time-zone=E. South America Standard Time", "--image-index=1"),
        # tira bypass de requisitos nao e necessario: VirtualBox 7 emula TPM 2.0 + EFI
    ]
    for p in passos:
        rc, out = _vb(*p, timeout=600)
        if rc:
            return f"Falhou em '{p[0]}': {out[-400:]}"
    return "VM criada. A instalacao automatica começa ao ligar (ligar())."


def ligar():
    s = estado()
    if s == "running":
        return "Ja esta ligada."
    return _vb("startvm", NOME, "--type", "headless", timeout=180)[1] or "Ligando sem janela."


def abrir_tela():
    """Abre a janela para o Dono acompanhar/auditar (a VM continua a mesma)."""
    if estado() == "running":
        subprocess.Popen([str(Path(VBOX).with_name("VirtualBoxVM.exe")), "--startvm", NOME, "--separate"])
        return "Janela aberta."
    return "A VM nao esta ligada."


def pausar():
    """Congela e libera a RAM; ligar() volta de onde parou."""
    return _vb("controlvm", NOME, "savestate", timeout=180)[1] or "VM pausada (RAM liberada)."


def desligar():
    rc, out = _vb("controlvm", NOME, "acpipowerbutton")
    return out or "Pedido de desligamento enviado."


def forcar_desligar():
    return _vb("controlvm", NOME, "poweroff")[1] or "VM desligada a forca."


def print_tela(destino=None):
    destino = Path(destino or DADOS / "tela.png")
    destino.parent.mkdir(parents=True, exist_ok=True)
    rc, out = _vb("controlvm", NOME, "screenshotpng", destino)
    return str(destino) if not rc else f"Sem print: {out}"


def executar(exe, *args, timeout_s=120):
    """Roda um programa DENTRO do Windows convidado (precisa das Guest Additions)."""
    rc, out = _vb("guestcontrol", NOME, "run", f"--username={USUARIO}", f"--passwordfile={_arq_senha()}",
                  f"--exe={exe}", f"--timeout={timeout_s * 1000}", "--wait-stdout", "--wait-stderr", "--", exe, *args,
                  timeout=timeout_s + 30)
    return rc, out


def copiar_para(origem, destino_no_guest):
    return _vb("guestcontrol", NOME, "copyto", f"--username={USUARIO}", f"--passwordfile={_arq_senha()}",
               origem, destino_no_guest, "--recursive")[1] or "Copiado para a VM."


def copiar_de(origem_no_guest, destino):
    return _vb("guestcontrol", NOME, "copyfrom", f"--username={USUARIO}", f"--passwordfile={_arq_senha()}",
               origem_no_guest, destino, "--recursive")[1] or "Copiado da VM."


def snapshot(nome=SNAP_LIMPO):
    return _vb("snapshot", NOME, "take", nome, timeout=600)[1] or f"Snapshot '{nome}' criado."


def restaurar(nome=SNAP_LIMPO):
    if estado() == "running":
        forcar_desligar()
    return _vb("snapshot", NOME, "restore", nome, timeout=600)[1] or f"Voltou ao snapshot '{nome}'."


def _tela_preta():
    # o VirtualBox 7.2 trava o EFI no reinicio a quente do guest: tela fica toda preta (PNG minusculo)
    f = print_tela(DADOS / "vigia.png")
    return f.endswith(".png") and Path(f).stat().st_size < 3000


def vigiar(max_min=90, intervalo_s=30):
    """Religa a frio quando o guest trava na tela preta; para quando as Guest Additions respondem."""
    import time
    pretas, fim = 0, time.time() + max_min * 60
    while time.time() < fim:
        time.sleep(intervalo_s)
        if estado() != "running":
            continue
        rc, out = _vb("showvminfo", NOME, "--machinereadable")
        if re.search(r"GuestAdditionsRunLevel=([1-9])", out):
            return "Windows no ar (Guest Additions ativas)."
        pretas = pretas + 1 if _tela_preta() else 0
        if pretas >= 4:  # ~2 min preto
            forcar_desligar()
            time.sleep(5)
            ligar()
            pretas = 0
    return "Tempo do vigia esgotado."


def resumo():
    return f"VM {NOME}: {estado()}"


if __name__ == "__main__":
    # autoteste leve: so le estado, nao cria nem liga nada
    assert VBOX and Path(VBOX).exists(), "VirtualBox nao encontrado"
    print(resumo())
