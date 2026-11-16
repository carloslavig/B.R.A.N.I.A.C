"""Analise LOCAL de video, sem IA online e sem gastar token: quadros (ffmpeg) + descricao de cada
quadro (Ollama moondream) + transcricao da fala (Whisper local do Braniac).

Uso (na pasta Agente):
    python -m braniac.video_analise "C:\\caminho\\video.mp4"          # um video
    python -m braniac.video_analise "C:\\Users\\usuario\\Downloads"     # todos os .mp4 da pasta
    opcional: --quadros 8 (quantos quadros descrever; padrao 8)

Resultado por video: braniac/data/analises_video/<nome>/resumo.md, dados.json e frames/.
AVISO: nao rode junto com um render do Estudio3D (Ollama e Remotion brigam pela CPU/GPU).
E lento (modelo de visao local ~1,5 min por quadro): deixe rodando em segundo plano.
"""
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
SAIDA = RAIZ / "data" / "analises_video"
OLLAMA = "http://localhost:11434/api/generate"
MODELO_VISAO = "moondream:latest"   # cabe na GPU de 4 GB; qwen2.5vl:3b trava (limite de repeticao)
PROMPT = ("Describe this vertical video frame in detail: layout, every text you can read on screen "
          "(titles, labels, captions, watermark), colors, 3D objects and their position.")


def _ffprobe(video: Path) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_name,width,height,r_frame_rate",
                        "-of", "json", str(video)], capture_output=True, text=True)
    return json.loads(r.stdout or "{}")


def _quadros(video: Path, pasta: Path, n: int, duracao: float) -> list[Path]:
    pasta.mkdir(parents=True, exist_ok=True)
    arqs = []
    for i in range(n):
        t = duracao * (i + 0.5) / n
        arq = pasta / f"q{int(t):03d}s.jpg"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", str(t), "-i", str(video),
                        "-frames:v", "1", "-vf", "scale=540:-2", str(arq)], check=False)
        if arq.exists():
            arqs.append(arq)
    return arqs


def _descrever(arq: Path) -> str:
    import base64
    img = base64.b64encode(arq.read_bytes()).decode()
    corpo = json.dumps({"model": MODELO_VISAO, "prompt": PROMPT, "images": [img], "stream": False,
                        "options": {"num_predict": 220}}).encode()
    try:
        r = urllib.request.urlopen(urllib.request.Request(OLLAMA, corpo, {"Content-Type": "application/json"}), timeout=600)
        return json.loads(r.read()).get("response", "").strip()
    except Exception as e:  # segue sem a descricao desse quadro
        return f"(falhou: {e})"


def _transcrever(video: Path, pasta: Path) -> list[dict]:
    wav = pasta / "audio.wav"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(video), "-ac", "1", "-ar", "16000", str(wav)], check=False)
    if not wav.exists():
        return []
    from . import voz
    modelo = voz._carregar_whisper()
    segmentos, _ = modelo.transcribe(str(wav), language="pt", beam_size=5)
    return [{"inicio": round(s.start, 2), "fim": round(s.end, 2), "texto": s.text.strip()} for s in segmentos]


def analisar(video: Path, quadros: int = 8) -> Path:
    pasta = SAIDA / video.stem.replace(" ", "-")[:60]
    pasta.mkdir(parents=True, exist_ok=True)
    meta = _ffprobe(video)
    duracao = float(meta.get("format", {}).get("duration", 0) or 0)
    transcricao = _transcrever(video, pasta)
    arqs = _quadros(video, pasta / "frames", quadros, max(duracao, 1))
    descricoes = []
    for a in arqs:
        t0 = time.time()
        descricoes.append({"quadro": a.name, "descricao": _descrever(a)})
        print(f"  {a.name} em {int(time.time() - t0)}s", flush=True)
    dados = {"video": str(video), "duracao_s": round(duracao, 1), "meta": meta.get("streams", []),
             "transcricao": transcricao, "quadros": descricoes}
    (pasta / "dados.json").write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    md = [f"# {video.name}", f"Duracao: {duracao:.0f} s", "", "## Fala (Whisper local)"]
    md += [f"- [{s['inicio']:.0f}s] {s['texto']}" for s in transcricao] or ["(sem fala reconhecida)"]
    md += ["", "## Quadros (moondream local)"]
    md += [f"### {d['quadro']}\n{d['descricao']}" for d in descricoes]
    (pasta / "resumo.md").write_text("\n".join(md), encoding="utf-8")
    print(f"OK {video.name} -> {pasta / 'resumo.md'}", flush=True)
    return pasta


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    n = int(sys.argv[sys.argv.index("--quadros") + 1]) if "--quadros" in sys.argv else 8
    alvo = Path(args[0]) if args else Path.home() / "Downloads"
    videos = sorted(alvo.glob("*.mp4")) if alvo.is_dir() else [alvo]
    if not videos:
        print(f"nenhum .mp4 em {alvo}")
        return
    for v in videos:
        print(f"== {v.name}", flush=True)
        analisar(v, n)


if __name__ == "__main__":
    main()
