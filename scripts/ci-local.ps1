param(
    [switch]$PythonOnly,
    [switch]$MetaOnly,
    [switch]$PostgresOnly,
    [switch]$SkipPostgres,
    [switch]$SkipMeta,
    [switch]$Qodana
)

$ErrorActionPreference = "Stop"

function Invoke-Step {
    param(
        [string]$Name,
        [scriptblock]$Command
    )
    Write-Host "`n==> $Name" -ForegroundColor Cyan
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE"
    }
}

function Project-Python {
    $candidate = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
    if (Test-Path $candidate) {
        return (Resolve-Path $candidate).Path
    }
    return "python"
}

function Venv-Tool {
    param([string]$Name)
    $candidate = Join-Path $PSScriptRoot "..\.venv\Scripts\$Name.exe"
    if (Test-Path $candidate) {
        return (Resolve-Path $candidate).Path
    }
    return $Name
}

function Get-FreePort {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
    $listener.Start()
    try {
        return $listener.LocalEndpoint.Port
    }
    finally {
        $listener.Stop()
    }
}

function Wait-Postgres {
    param(
        [string]$Container,
        [int]$Attempts = 40
    )
    for ($i = 0; $i -lt $Attempts; $i++) {
        docker exec $Container pg_isready -U radio -d radio | Out-Null
        if ($LASTEXITCODE -eq 0) {
            return
        }
        Start-Sleep -Seconds 1
    }
    throw "Postgres container did not become ready"
}

function Invoke-PythonCi {
    $ruff = Venv-Tool "ruff"
    $black = Venv-Tool "black"
    $mypy = Venv-Tool "mypy"
    $pytest = Venv-Tool "pytest"
    $python = Project-Python

    Invoke-Step "pip check" { & $python -m pip check }
    Invoke-Step "ruff check" { & $ruff check . }
    Invoke-Step "black --check" { & $black --check . }
    Invoke-Step "mypy" { & $mypy --cache-dir=.mypy_cache . }
    Invoke-Step "pytest" {
        & $pytest -q --maxfail=1 -r fE --cov --cov-report=xml --junitxml=test-results/pytest.xml
    }
    Invoke-Step "windows smoke import" { & $python -c "import manager; print('manager import ok')" }
}

function Invoke-PostgresCi {
    $pytest = Venv-Tool "pytest"
    $postgresContainer = "radio-ci-postgres-local"
    $postgresPort = Get-FreePort
    docker rm -f $postgresContainer 2>$null | Out-Null
    try {
        Invoke-Step "start postgres docker" {
            docker run --rm -d --name $postgresContainer `
                -e POSTGRES_DB=radio `
                -e POSTGRES_USER=radio `
                -e POSTGRES_PASSWORD=radio `
                -p "${postgresPort}:5432" postgres:16 | Out-Null
        }
        Wait-Postgres -Container $postgresContainer
        $env:RADIO_INTEGRATION_DATABASE_DSN = "postgresql://radio:radio@localhost:$postgresPort/radio"
        Invoke-Step "postgres integration" { & $pytest -q tests/integration }
    }
    finally {
        Remove-Item Env:\RADIO_INTEGRATION_DATABASE_DSN -ErrorAction SilentlyContinue
        docker rm -f $postgresContainer 2>$null | Out-Null
    }
}

function Invoke-MetaCi {
    $python = Project-Python
    $yamllint = Venv-Tool "yamllint"
    Invoke-Step "install yamllint" {
        & $python -m pip install --disable-pip-version-check --quiet yamllint
    }
    $workflowFiles = Get-ChildItem ".github/workflows/*.yml" | ForEach-Object { $_.FullName }
    Invoke-Step "yamllint workflows" { & $yamllint -s @workflowFiles }

    Invoke-Step "markdownlint" {
        npx --yes markdownlint-cli2 `
            "**/*.md" `
            "#.venv/**" `
            "#.venv-wsl/**" `
            "#.git/**" `
            "#htmlcov/**" `
            "#radio_manager.egg-info/**" `
            "#.mypy_cache/**" `
            "#.pytest_cache/**" `
            "#.ruff_cache/**"
    }

    $actionlintFiles = Get-ChildItem ".github/workflows/*.yml" |
        ForEach-Object { $_.FullName.Replace((Get-Location).Path + "\", "").Replace("\", "/") }
    $args = ($actionlintFiles -join " ")
    Invoke-Step "actionlint workflows" {
        docker run --rm `
            -v "${PWD}:/repo" `
            -w /repo `
            --entrypoint /bin/sh `
            rhysd/actionlint:1.7.7 `
            -c "actionlint -color $args"
    }
}

function Invoke-QodanaCi {
    Invoke-Step "qodana docker" {
        docker run --rm `
            -v "${PWD}:/data/project" `
            -v "${PWD}/qodana:/data/results" `
            jetbrains/qodana-python-community:2025.2 `
            --results-dir,/data/results
    }
}

$runPython = -not $MetaOnly -and -not $PostgresOnly
$runPostgres = -not $PythonOnly -and -not $MetaOnly -and -not $SkipPostgres
$runMeta = -not $PythonOnly -and -not $PostgresOnly -and -not $SkipMeta

if ($runPython) {
    Invoke-PythonCi
}
if ($runPostgres) {
    Invoke-PostgresCi
}
if ($runMeta) {
    Invoke-MetaCi
}
if ($Qodana) {
    Invoke-QodanaCi
}

Write-Host "`nLocal CI passed" -ForegroundColor Green
