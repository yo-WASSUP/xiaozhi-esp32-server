param(
    [string]$PythonExe = "C:\Users\38370\anaconda3\envs\paddlespeech-tts\python.exe",
    [string]$HostName = "127.0.0.1",
    [int]$Port = 8092,
    [string]$Device = "cpu"
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$TmpDir = Join-Path $RepoRoot "tmp"
$ConfigPath = Join-Path $TmpDir "paddlespeech_tts_online_application.yaml"
$PaddleUserHome = Join-Path $TmpDir "paddle_userhome"
$PaddleSpeechHome = Join-Path $TmpDir "paddlespeech_home"
$PaddleNlpHome = Join-Path $TmpDir "paddlenlp_home"
$LogPath = Join-Path $TmpDir "paddlespeech_server.log"

if (-not (Test-Path -LiteralPath $PythonExe)) {
    Write-Error "PaddleSpeech python not found: $PythonExe"
}

New-Item -ItemType Directory -Force -Path $TmpDir, $PaddleUserHome, $PaddleSpeechHome, $PaddleNlpHome | Out-Null

@"
host: $HostName
port: $Port
protocol: websocket
engine_list:
  - tts_online

tts_online:
  device: $Device
  am: fastspeech2_cnndecoder_csmsc
  am_config:
  am_ckpt:
  am_stat:
  phones_dict:
  tones_dict:
  speaker_dict:
  voc: mb_melgan_csmsc
  voc_config:
  voc_ckpt:
  voc_stat:
  lang: zh
  am_block: 72
  am_pad: 12
  voc_block: 36
  voc_pad: 14
"@ | Set-Content -LiteralPath $ConfigPath -Encoding UTF8

$env:PYTHONUTF8 = "1"
$env:USERPROFILE = $PaddleUserHome
$env:HOME = $PaddleUserHome
$env:PPSPEECH_HOME = $PaddleSpeechHome
$env:PPNLP_HOME = $PaddleNlpHome

Write-Host "Starting PaddleSpeech streaming TTS..."
Write-Host "URL: ws://$HostName`:$Port/paddlespeech/tts/streaming"
Write-Host "Config: $ConfigPath"
Write-Host "Model cache: $PaddleSpeechHome"
Write-Host "Press Ctrl+C to stop."

& $PythonExe -c "from paddlespeech.server.bin.paddlespeech_server import ServerExecutor; ServerExecutor()(r'$ConfigPath', r'$LogPath')"
