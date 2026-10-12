# UPDATE 16: local OneCore TTS (Yating/Zhiwei) -> wav, called by tts.py via subprocess.
# ASCII-only on purpose: PowerShell 5.1 reads BOM-less .ps1 as ANSI, so non-ASCII here breaks parsing.
# The Chinese text to speak is read from a UTF-8 file (-TextFile), so it is unaffected.
param(
  [Parameter(Mandatory = $true)][string]$TextFile,
  [Parameter(Mandatory = $true)][string]$OutFile,
  [string]$VoiceMatch = 'Yating',
  [double]$Rate = 1.0
)
$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() |
  Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
                 $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, $t) { $m = $asTask.MakeGenericMethod($t); $tk = $m.Invoke($null, @($op)); $tk.Wait(-1) | Out-Null; $tk.Result }

[Windows.Media.SpeechSynthesis.SpeechSynthesizer, Windows.Media, ContentType = WindowsRuntime] | Out-Null
[Windows.Storage.Streams.DataReader, Windows.Storage.Streams, ContentType = WindowsRuntime] | Out-Null

$text = Get-Content -Raw -Encoding UTF8 $TextFile
$synth = New-Object Windows.Media.SpeechSynthesis.SpeechSynthesizer
$v = [Windows.Media.SpeechSynthesis.SpeechSynthesizer]::AllVoices |
  Where-Object { $_.DisplayName -match $VoiceMatch } | Select-Object -First 1
if ($v) { $synth.Voice = $v }
try { $synth.Options.SpeakingRate = $Rate } catch { }

$stream = Await ($synth.SynthesizeTextToStreamAsync($text)) ([Windows.Media.SpeechSynthesis.SpeechSynthesisStream])
$size = [uint32]$stream.Size
$dr = New-Object Windows.Storage.Streams.DataReader($stream)
Await ($dr.LoadAsync($size)) ([uint32]) | Out-Null
$bytes = New-Object byte[] $size
$dr.ReadBytes($bytes)
[System.IO.File]::WriteAllBytes($OutFile, $bytes)
