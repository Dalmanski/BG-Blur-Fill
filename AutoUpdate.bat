@echo off
cd "%USERPROFILE%\OneDrive\Documents\Code\Python tkinter\BG Blur Fill\BG Blur Fill.py"

set "VERSION=1.0.0"

echo === Building executable with PyInstaller ===
pyinstaller ^
  --noconsole ^
  --onefile ^
  --icon=favicon.ico ^
  --add-data "settings.json;." ^
  "BG Blur Fill.py"

echo === Updating version in dist/settings.json ===
powershell -NoProfile -Command ^
  "$path = 'dist\\settings.json'; if (-not (Test-Path $path)) { Write-Host 'Warning: dist\\settings.json not found, skipping version update.'; exit 0 } ; " ^
  "$raw = Get-Content -Raw -Encoding UTF8 $path; $obj = $raw | ConvertFrom-Json; $ht = @{}; $obj.psobject.properties | ForEach-Object { $ht[$_.Name] = $_.Value }; $ht['version'] = '%VERSION%'; $ht | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 $path"

echo === Creating ZIP archive ===
powershell -NoProfile -Command ^
  "Compress-Archive -Path 'dist\\*' -DestinationPath 'zip\\BG_Blur_Fill%VERSION%.zip' -Force"

echo === Done! ===