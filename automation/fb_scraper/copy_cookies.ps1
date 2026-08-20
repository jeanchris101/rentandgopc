$src = [System.IO.Path]::Combine($env:LOCALAPPDATA, "Google", "Chrome", "User Data", "Default", "Network", "Cookies")
$dst = "C:\Claude\puntacana-properties\automation\fb_scraper\_cookies_tmp.db"
$fs = [System.IO.File]::Open($src, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
$buf = New-Object byte[] $fs.Length
$null = $fs.Read($buf, 0, $fs.Length)
$fs.Close()
[System.IO.File]::WriteAllBytes($dst, $buf)
Write-Host "Copied $($buf.Length) bytes to $dst"
