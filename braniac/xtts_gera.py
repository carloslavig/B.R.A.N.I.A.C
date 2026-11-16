"""Voz XTTS-v2 (Coqui, local na placa de video). Roda SO no venv proprio data/xtts (torch nao entra no Python do Braniac).
Uso: data/xtts/Scripts/python.exe braniac/xtts_gera.py --texto "..." --ref voz_de_referencia.wav --saida fala.wav
Imprime uma linha JSON com os tempos (carga do modelo e geracao). Chamado por voz._xtts_wav."""
import argparse, json, os, sys, time

# O XTTS-v2 so baixa depois de aceitar a licenca CPML (uso nao comercial); o Braniac so liga isto quando o dono aceita (XTTS_LICENCA_OK=1).
if os.environ.get("XTTS_LICENCA_OK") == "1":
    os.environ["COQUI_TOS_AGREED"] = "1"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--texto", required=True)
    ap.add_argument("--ref", required=True)
    ap.add_argument("--saida", required=True)
    ap.add_argument("--cpu", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    import torch
    from TTS.api import TTS
    disp = "cpu" if a.cpu or not torch.cuda.is_available() else "cuda"
    tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(disp)
    t1 = time.time()
    tts.tts_to_file(text=a.texto, speaker_wav=a.ref, language="pt", file_path=a.saida)
    t2 = time.time()
    print(json.dumps({"dispositivo": disp, "carga_s": round(t1 - t0, 2), "geracao_s": round(t2 - t1, 2)}))


if __name__ == "__main__":
    sys.exit(main())
