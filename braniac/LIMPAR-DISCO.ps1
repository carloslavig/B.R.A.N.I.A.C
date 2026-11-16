# Limpeza SEGURA do disco: para cada item mostra o tamanho e PERGUNTA (S/N) antes de apagar. So itens que o Windows/apps recriam sozinhos
# (conselho de IAs do Braniac, 08/10/2026). Nada de fotos, documentos, jogos, saves ou projetos. Rode com o botao direito > "Executar com o PowerShell".
$itens = @(
  @{ nome = "Temporarios do usuario (%TEMP%)";                       caminho = $env:TEMP },
  @{ nome = "Cache do npm";                                         caminho = "$env:LOCALAPPDATA\npm-cache" },
  @{ nome = "Cache do pip";                                         caminho = "$env:LOCALAPPDATA\pip\Cache" },
  @{ nome = "Cache do Gradle";                                      caminho = "$env:USERPROFILE\.gradle\caches" },
  @{ nome = "Cache de shaders da NVIDIA (pasta que voce marcou PODE_DELETAR)"; caminho = "E:\PODE_DELETAR\NVIDIA-cache" },
  @{ nome = "Cache de shaders da Steam";                            caminho = "E:\SteamLibrary\steamapps\shadercache" },
  @{ nome = "Duplicados em quarentena (C:)  <- confira antes";      caminho = "$env:USERPROFILE\_REVISAR_DUPLICADOS" },
  @{ nome = "Duplicados em quarentena (E:)  <- confira antes";      caminho = "E:\_REVISAR_DUPLICADOS" }
)
function Tamanho($p) { if (Test-Path $p) { [math]::Round(((Get-ChildItem $p -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum) / 1GB, 2) } else { 0 } }
$total = 0
foreach ($i in $itens) {
  $gb = Tamanho $i.caminho
  if ($gb -le 0) { continue }
  $r = Read-Host ("{0}  [{1} GB]  apagar? (S/N)" -f $i.nome, $gb)
  if ($r -match '^[sS]') {
    Remove-Item -Path (Join-Path $i.caminho '*') -Recurse -Force -ErrorAction SilentlyContinue
    $total += $gb; Write-Host "  apagado." -ForegroundColor Green
  }
}
Write-Host ("`nLiberado: ~{0} GB. Esvazie tambem a Lixeira se quiser." -f $total)
Write-Host "Dica: Configuracoes > Sistema > Armazenamento > Arquivos temporarios tambem limpa o Windows Update e o Windows.old, se existir."
Read-Host "Enter para fechar"
