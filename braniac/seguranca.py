# -*- coding: utf-8 -*-
"""Checagem de seguranca do PC e da rede do Dono (30/10/2026). SO LE: nao muda firewall, contas, registro nem roteador, e nao tenta senha de nada.
Cada achado vem com a correcao sugerida; quem corrige e o Dono (mexer em seguranca do sistema e decisao dele). Relatorio em relatorios/seguranca-AAAA-MM-DD.md."""
import json
import subprocess
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PS = r"""
$o=@{}
$d=Get-MpComputerStatus; $o.defender=@($d.AntivirusEnabled,$d.RealTimeProtectionEnabled,$d.AntivirusSignatureAge,$d.IsTamperProtected)
$o.firewall=@(Get-NetFirewallProfile|?{-not $_.Enabled}|%{$_.Name})
$o.rdp=((Get-ItemProperty 'HKLM:\System\CurrentControlSet\Control\Terminal Server').fDenyTSConnections -eq 0)
$o.smb1=[bool](Get-SmbServerConfiguration).EnableSMB1Protocol
$o.guest=[bool](Get-LocalUser|?{$_.SID -like '*-501' -and $_.Enabled})
$o.autologon=((Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon').AutoAdminLogon -eq '1')
$o.uac=((Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System').EnableLUA -eq 1)
$o.publica=@(Get-NetConnectionProfile|?{$_.NetworkCategory -eq 'Public'}|%{$_.Name})
$o.smb_publico=[bool](Get-NetFirewallRule -Direction Inbound -Enabled True -Action Allow -ea 0|?{$_.Profile -match 'Public|Any'}|%{($_|Get-NetFirewallPortFilter).LocalPort}|?{$_ -eq '445'})
$o.atualizado_em=(Get-HotFix|sort InstalledOn -Desc|select -First 1).InstalledOn.ToString('yyyy-MM-dd')
$o.escuta=@(Get-NetTCPConnection -State Listen|?{$_.LocalAddress -in '0.0.0.0','::'}|%{"$($_.LocalPort)"}|sort -u)
$gw=(Get-NetRoute -DestinationPrefix 0.0.0.0/0|select -First 1).NextHop; $o.gw=$gw
$o.gw_abertas=@(foreach($p in 21,22,23,80,443,7547,8080){$c=New-Object Net.Sockets.TcpClient;$r=$c.BeginConnect($gw,$p,$null,$null);if($r.AsyncWaitHandle.WaitOne(600) -and $c.Connected){$p};$c.Close()})
# sinais de invasao (precisam de admin para o log de Seguranca: sem acesso vira null e nao conta como achado)
$ini=(Get-Date).AddDays(-7)
$o.falhas=$null; try{$o.falhas=@(Get-WinEvent -FilterHashtable @{LogName='Security';Id=4625;StartTime=$ini} -ea Stop).Count}catch{if($_.Exception.Message -match 'Nenhum evento|No events'){$o.falhas=0}}
$o.rdp_entrou=$null; try{$o.rdp_entrou=@(Get-WinEvent -FilterHashtable @{LogName='Security';Id=4624;StartTime=$ini} -ea Stop|?{$_.Properties[8].Value -in 3,10 -and $_.Properties[18].Value -notmatch '^(127\.|::1|-|192\.168\.)'}).Count}catch{if($_.Exception.Message -match 'Nenhum evento|No events'){$o.rdp_entrou=0}}
$o.ameacas=@(Get-MpThreatDetection -ea 0|?{$_.InitialDetectionTime -gt (Get-Date).AddDays(-30)}|%{"$($_.ThreatID)"}|sort -u)
$o.contas=@(Get-LocalUser|?{$_.Enabled}|%{$_.Name}|sort)
$o.admins=@(Get-LocalGroupMember -SID S-1-5-32-544 -ea 0|%{$_.Name}|sort)
$o.externas_suspeitas=@(Get-NetTCPConnection -State Established -ea 0|?{$_.RemoteAddress -notmatch '^(127\.|::1|192\.168\.|10\.|0\.|fe80)'}|%{$pr=Get-Process -Id $_.OwningProcess -ea 0; if($pr.Path -match '\(Temp|Downloads|Users\Public)\'){"$($pr.ProcessName)->$($_.RemoteAddress):$($_.RemotePort)"}}|sort -u)
$o|ConvertTo-Json -Compress
"""
BASE = RAIZ / "braniac" / "data" / "seguranca_base.json"   # contas e admins vistos na 1a checagem: o que aparecer depois e novidade


def coletar(rodar=None):
    if rodar:
        return rodar()
    r = subprocess.run(["powershell", "-NoProfile", "-Command", PS], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120, creationflags=0x08000000)
    return json.loads(r.stdout.strip().splitlines()[-1])


def avaliar(d, hoje=None):
    """[(gravidade, achado, correcao)] a partir dos dados coletados. Gravidade: alta, media, baixa."""
    a, hoje = [], hoje or time.strftime("%Y-%m-%d")
    av, rt, idade = (list(d.get("defender") or []) + [None] * 3)[:3]
    if not av or not rt:
        a.append(("alta", "Antivirus do Windows desligado.", "Ligar a Seguranca do Windows (protecao em tempo real)."))
    if (idade or 0) > 7:
        a.append(("media", f"Definicoes do antivirus com {idade} dias.", "Atualizar pela Seguranca do Windows."))
    for nome in d.get("firewall") or []:
        a.append(("alta", f"Firewall desligado no perfil {nome}.", "Ligar o Firewall do Windows nesse perfil."))
    if d.get("rdp"):
        a.append(("alta", "Area de Trabalho Remota (RDP) ligada.", "Desligar em Configuracoes > Sistema > Area de Trabalho Remota, se nao usa."))
    if d.get("smb1"):
        a.append(("alta", "SMB1 (protocolo antigo e inseguro) ligado.", "Desativar o recurso SMB 1.0 do Windows."))
    if d.get("autologon"):
        a.append(("alta", "Login automatico do Windows ligado (senha guardada no registro).", "Desligar o login automatico."))
    if not d.get("uac", True):
        a.append(("alta", "UAC desligado.", "Ligar o Controle de Conta de Usuario."))
    if d.get("guest"):
        a.append(("media", "Conta Convidado ativa (sem senha).", "Desativar: 'net user Convidado /active:no' num terminal de administrador."))
    if d.get("smb_publico") and d.get("publica"):
        a.append(("media", "Compartilhamento de arquivos (porta 445) liberado para qualquer endereco em rede Publica (" + ", ".join(d["publica"]) + ").",
                  "Desativar a regra 'Compartilhamento de Arquivo e Impressora (Restritivo)' ou deixar so para a sub-rede local."))
    if d.get("atualizado_em") and d["atualizado_em"] < time.strftime("%Y-%m-%d", time.localtime(time.mktime(time.strptime(hoje, "%Y-%m-%d")) - 45 * 86400)):
        a.append(("media", f"Ultima atualizacao do Windows instalada em {d['atualizado_em']}.", "Rodar o Windows Update."))
    for p in d.get("gw_abertas") or []:
        if p in (21, 23, 7547):
            a.append(("alta", f"Roteador {d.get('gw')} com porta {p} (FTP/Telnet/TR-069) aberta na rede interna.", "Desligar esse servico no painel do roteador."))
        elif p == 80 and 443 not in (d.get("gw_abertas") or []):
            a.append(("baixa", "Painel do roteador so em HTTP (sem criptografia).", "Usar o painel so de casa e trocar a senha de admin do roteador."))
    a += invasao(d)
    a.append(("baixa", "Painel do roteador: nao tento senhas nem entro nele. Confira voce mesmo se a senha de admin nao e a de fabrica e se a Wi-Fi usa WPA2/WPA3 e WPS desligado.", "Acessar http://" + str(d.get("gw")) + " de dentro de casa."))
    return a


def invasao(d):
    """Sinais de que alguem tentou ou conseguiu entrar (7 dias). Falta de permissao no log = sem dado, nunca 'tudo certo'."""
    a = []
    if (d.get("falhas") or 0) >= 20:
        a.append(("media", f"{d['falhas']} tentativas de login que falharam nos ultimos 7 dias.", "Ver o Visualizador de Eventos (Seguranca, ID 4625) e trocar a senha se nao foram voce."))
    if (d.get("rdp_entrou") or 0) > 0:
        a.append(("alta", f"{d['rdp_entrou']} login(s) vindo de fora da rede local nos ultimos 7 dias.", "Conferir o IP no Visualizador de Eventos (ID 4624); se nao foi voce, trocar a senha e desligar o acesso remoto."))
    if d.get("ameacas"):
        a.append(("alta", f"O Defender detectou {len(d['ameacas'])} ameaca(s) nos ultimos 30 dias.", "Abrir Seguranca do Windows > Protecao contra virus > Historico de protecao."))
    if d.get("externas_suspeitas"):
        a.append(("alta", "Programa rodando de Temp/Downloads/Public com conexao para a internet: " + ", ".join(d["externas_suspeitas"][:5]), "Identificar o programa no Gerenciador de Tarefas; se nao reconhece, desconectar da rede e rodar uma verificacao completa."))
    atual = {"contas": sorted(d.get("contas") or []), "admins": sorted(d.get("admins") or [])}
    try:
        base = json.loads(BASE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        base = None
        if atual["contas"]:
            BASE.write_text(json.dumps(atual), encoding="utf-8")
    if base:
        for chave, nome in (("contas", "Conta ativa nova"), ("admins", "Novo administrador")):
            for x in sorted(set(atual[chave]) - set(base.get(chave, []))):
                a.append(("alta", f"{nome} no PC: {x}.", "Se nao foi voce, desativar a conta e trocar as senhas."))
    if d.get("falhas") is None:
        a.append(("baixa", "Sem permissao para ler o log de Seguranca: tentativas de login nao foram checadas.", "Rodar o Braniac como administrador, se quiser essa checagem."))
    return a


def arquivos_sensiveis():
    """Segredos soltos em pastas comuns (so nomes, nunca o conteudo)."""
    achados = []
    for pasta in (Path.home() / "Downloads", Path.home() / "Desktop", Path.home() / "Documents"):
        for p in pasta.rglob("client_secret*.json") if pasta.exists() else []:
            achados.append(("media", f"Segredo do Google (client_secret) solto em {p.parent.name}/.", "Mover para uma pasta protegida ou apagar se nao usa; nunca enviar a ninguem."))
    env = RAIZ / "braniac" / ".env"
    if env.exists():
        achados.append(("baixa", "braniac/.env guarda chaves em texto puro (esta fora do git).", "Manter fora de nuvem/backup publico."))
    return achados


def relatorio(achados, d):
    ordem = {"alta": 0, "media": 1, "baixa": 2}
    achados = sorted(achados, key=lambda x: ordem[x[0]])
    linhas = [f"# Seguranca do PC e da rede — {time.strftime('%d/%m/%Y %H:%M')}", "", "Checagem somente de leitura. Nada foi alterado.", ""]
    linhas += [f"- **{g.upper()}** — {t}\n  - Correcao: {c}" for g, t, c in achados]
    linhas += ["", f"Portas escutando em todas as interfaces: {', '.join(d.get('escuta') or [])} (a internet so chega nelas se o roteador abrir porta; o firewall bloqueia as que nao tem regra)."]
    arq = RAIZ / "relatorios" / f"seguranca-{time.strftime('%Y-%m-%d')}.md"
    arq.parent.mkdir(exist_ok=True)
    arq.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return arq


def rodar(registrar=None, rodar_ps=None):
    d = coletar(rodar_ps)
    achados = avaliar(d) + arquivos_sensiveis()
    arq = relatorio(achados, d)
    n = {g: sum(1 for x in achados if x[0] == g) for g in ("alta", "media", "baixa")}
    if registrar:
        registrar(f"🔒 Seguranca do PC e da rede: {n['alta']} alta(s), {n['media']} media(s), {n['baixa']} baixa(s). Detalhes em relatorios/{arq.name}.")
    return achados


if __name__ == "__main__":
    for g, t, c in rodar():
        print(f"[{g}] {t}\n      -> {c}")
