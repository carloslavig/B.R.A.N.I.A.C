# -*- coding: utf-8 -*-
"""GUARDA DE SEGURANCA (opcional, a pessoa liga). SO OBSERVA E AVISA; nao muda firewall nem fecha porta sozinho.
A cada ~10 min, tudo local (so o IP publico consulta a internet, em api.ipify.org):
 - IP publico mudou? (normal com VPN/provedor dinamico, mas a pessoa fica sabendo)
 - portas escutando para a REDE que nao existiam antes; portas de risco (banco de dados, RDP, Telnet...) avisam sempre
 - Firewall do Windows desligado, Area de Trabalho Remota ligada, Defender sem protecao em tempo real ou com definicoes velhas
 - rajada de falhas de login (>= 10 na ultima hora)
Limite honesto: nao e antivirus e nao impede ataque; atras de roteador domestico o PC ja nao e alcancavel de fora sem redirecionamento de porta.
O aviso vai so para a pessoa (Telegram dela e a tela do assistente). Exige a permissao 'sistema.seguranca'."""
import json, subprocess, threading, time, urllib.request
from . import paths, perfil, permissoes

PORTAS_RISCO = {21: "FTP", 23: "Telnet", 1433: "SQL Server", 3306: "MySQL", 3389: "Área de Trabalho Remota (RDP)", 5432: "PostgreSQL", 5900: "VNC",
                6379: "Redis", 27017: "MongoDB", 9200: "Elasticsearch"}
ESPERADAS = {135, 445, 5040, 7680, 2179}
COOLDOWN_S = 12 * 3600


def _arq():
    return paths.arquivo("guarda.json")


def _ler():
    try:
        return json.loads(_arq().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _gravar(d):
    _arq().write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def ativa():
    return bool(perfil.carregar().get("guarda_ativa")) and permissoes.permitido("sistema.seguranca")


def ligar(sim=True):
    if sim:
        permissoes.exigir("sistema.seguranca")
    perfil.atualizar(guarda_ativa=bool(sim))


def _ps(cmd, timeout=40):
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd], capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace",
                       creationflags=0x08000000)
    return r.stdout.strip()


def _json(cmd):
    out = _ps(cmd)
    try:
        return json.loads(out) if out else None
    except ValueError:
        return None


def coletar():
    est = {"quando": time.time()}
    try:
        est["ip"] = urllib.request.urlopen("https://api.ipify.org", timeout=8).read().decode().strip()
    except Exception:
        est["ip"] = None
    p = _json("Get-NetTCPConnection -State Listen | Where-Object { $_.LocalAddress -in '0.0.0.0','::' } | ForEach-Object { [pscustomobject]@{p=$_.LocalPort; n=(Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue).ProcessName} } | ConvertTo-Json -Compress")
    p = [p] if isinstance(p, dict) else p
    est["portas"] = {str(x["p"]): x.get("n") or "?" for x in p} if p else None
    fw = _json("Get-NetFirewallProfile | Select-Object Name,Enabled | ConvertTo-Json -Compress")
    if fw:
        fw = fw if isinstance(fw, list) else [fw]
        est["firewall_desligado"] = [x["Name"] for x in fw if not x.get("Enabled")]
    else:
        est["firewall_desligado"] = None
    rdp = _ps("(Get-ItemProperty 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Terminal Server').fDenyTSConnections")
    est["rdp_ligado"] = (rdp == "0") if rdp in ("0", "1") else None
    d = _json("Get-MpComputerStatus | Select-Object RealTimeProtectionEnabled,@{n='dias';e={((Get-Date)-$_.AntivirusSignatureLastUpdated).Days}} | ConvertTo-Json -Compress")
    est["defender"] = {"tempo_real": bool(d.get("RealTimeProtectionEnabled")), "assinatura_dias": d.get("dias")} if d else None
    f = _ps("try { (Get-WinEvent -FilterHashtable @{LogName='Security';Id=4625;StartTime=(Get-Date).AddHours(-1)} -ErrorAction Stop | Measure-Object).Count } catch { 0 }")
    est["falhas_login_1h"] = int(f) if f.isdigit() else None
    return est


def avaliar(est, base):
    a = []
    if est.get("ip") and base.get("ip") and est["ip"] != base["ip"]:
        a.append((f"ip:{est['ip']}", f"🌐 Seu IP público mudou: {base['ip']} → {est['ip']}. Normal com provedor dinâmico ou VPN; se não foi isso, vale conferir."))
    if est.get("portas") is not None:
        conhecidas = set(base.get("portas_conhecidas") or [])
        for p, nome in sorted(est["portas"].items(), key=lambda x: int(x[0])):
            pi = int(p)
            if pi in PORTAS_RISCO:
                a.append((f"risco:{pi}", f"⚠️ A porta {pi} ({PORTAS_RISCO[pi]}, processo {nome}) está aberta para a rede, não só para este PC. Se outros aparelhos não precisam dela, "
                                          "o ideal é o serviço escutar só em 127.0.0.1 ou bloquear no firewall. Não mexi em nada."))
            elif conhecidas and p not in conhecidas and pi not in ESPERADAS and pi < 49152:
                a.append((f"nova:{pi}", f"🔎 Nova porta aberta para a rede: {pi} (processo {nome}). Se você não instalou nada agora, vale conferir."))
    if est.get("firewall_desligado"):
        a.append(("firewall", "🚨 O Firewall do Windows está DESLIGADO no perfil: " + ", ".join(est["firewall_desligado"]) + "."))
    if est.get("rdp_ligado"):
        a.append(("rdp", "🚨 A Área de Trabalho Remota (RDP) está LIGADA: é a porta de entrada mais atacada. Desligue se não usa."))
    d = est.get("defender")
    if d and not d["tempo_real"]:
        a.append(("defender", "🚨 A proteção em tempo real do Windows Defender está DESLIGADA."))
    if d and (d.get("assinatura_dias") or 0) > 7:
        a.append(("assinatura", f"🛡 As definições do antivírus estão com {d['assinatura_dias']} dias. Abra Segurança do Windows e atualize."))
    if (est.get("falhas_login_1h") or 0) >= 10:
        a.append(("login", f"🚨 {est['falhas_login_1h']} tentativas de login falhas na última hora: alguém pode estar tentando entrar no PC."))
    return a


def verificar(avisar, coletor=coletar, agora=None):
    """Uma checagem. `avisar(texto)` entrega A PESSOA. Primeira vez: so memoriza as portas ja abertas."""
    agora = agora or time.time()
    est = coletor()
    base = _ler()
    primeira = not base.get("portas_conhecidas") and est.get("portas")
    alertas = avaliar(est, {**base, "portas_conhecidas": []} if primeira else base)
    avisados = base.get("avisados", {})
    enviados = []
    for chave, texto in alertas:
        if agora - avisados.get(chave, 0) >= COOLDOWN_S:
            avisar(texto)
            avisados[chave] = agora
            enviados.append(texto)
    novo = dict(base)
    novo["avisados"] = {k: v for k, v in avisados.items() if agora - v < 7 * 86400}
    if est.get("ip"):
        novo["ip"] = est["ip"]
    if est.get("portas") is not None:
        novo["portas_conhecidas"] = sorted(set(base.get("portas_conhecidas") or []) | set(est["portas"]))
    novo["ultima"] = est
    if enviados:
        novo["ultimos_avisos"] = (enviados + base.get("ultimos_avisos", []))[:10]
    _gravar(novo)
    return enviados


def resumo():
    b = _ler()
    u = b.get("ultima")
    if not u:
        return "🛡 Guarda de segurança: ainda sem leitura."
    exp = [f"{p}({n})" for p, n in sorted((u.get("portas") or {}).items(), key=lambda x: int(x[0])) if int(p) in PORTAS_RISCO]
    partes = [f"IP {u.get('ip') or '?'}", "firewall " + ("OK" if u.get("firewall_desligado") == [] else "ATENÇÃO" if u.get("firewall_desligado") else "?"),
              "antivírus " + ("OK" if (u.get("defender") or {}).get("tempo_real") else "ATENÇÃO"), f"falhas de login/h: {u.get('falhas_login_1h', '?')}"]
    return "🛡 Segurança: " + " · ".join(partes) + (f"\n⚠️ Portas de risco abertas para a rede: {', '.join(exp)}" if exp else "")


def entregar(texto):
    try:
        from . import remoto
        remoto.avisar_dono(texto)
    except Exception:
        pass


def iniciar(intervalo_s=600):
    def laco():
        while True:
            try:
                if ativa():
                    verificar(entregar)
            except Exception:
                pass
            time.sleep(intervalo_s)
    threading.Thread(target=laco, daemon=True, name="guarda-seguranca").start()
