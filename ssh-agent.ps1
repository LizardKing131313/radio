# Run as administrator in PowerShell

Set-Service -Name ssh-agent -StartupType Automatic

Start-Service ssh-agent

ssh-add $env:USERPROFILE/.ssh/id_ed25519

pause
