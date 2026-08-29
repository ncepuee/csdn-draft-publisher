$ErrorActionPreference = "Stop"
$toolRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
python (Join-Path $toolRoot "csdn_bridge.py")
