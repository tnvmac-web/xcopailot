"""CLI install command — generate PowerShell installer."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console

console = Console()


@click.command()
@click.option("--output", "-o", type=click.Path(), default="install.ps1", help="Output file path")
@click.option(
    "--channel",
    type=click.Choice(["stable", "beta", "nightly"]),
    default="stable",
    help="Release channel",
)
@click.option("--version", default="0.1.0", help="Version to install")
def install(output, channel, version):
    """Generate PowerShell installer script."""
    installer_content = f'''# X-Copilot Installer

<#
.SYNOPSIS
    Install X-Copilot — Self-growing AI agent for Windows
    
.DESCRIPTION
    One-command install for Windows 10 19041+ / Windows 11
    Installs Python 3.11, Node.js 18+, and X-Copilot package
    
.EXAMPLE
    irm https://xcopilot.ai/install.ps1 | iex
#>

#Requires -Version 5.1

[CmdletBinding()]
param(
    [switch]$Dev,
    [switch]$NoProfile,
    [string]$Channel = "{channel}",
    [string]$InstallDir = "$env:USERPROFILE\\.xcopilot"
)

# Configuration
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

Write-Host "╔══════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║  X-Copilot — Self-growing AI agent for Windows               ║" -ForegroundColor Cyan
Write-Host "║  Installing from channel: $Channel                            ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan

function Check-Admin {{
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]$currentUser
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}}

function Install-WingetPackages {{
    $packages = @(
        "Python.Python.3.11",
        "Nodejs.Nodejs.20",
        "Git.Git"
    )
    
    foreach ($pkg in $packages) {{
        Write-Host "Installing $pkg via winget..." -ForegroundColor Yellow
        try {{
            winget install --id $pkg --silent --accept-source-agreements --accept-package-agreements
            Write-Host "✓ $pkg installed" -ForegroundColor Green
        }}
        catch {{
            Write-Warning "Failed to install $pkg: $_"
        }}
    }}
}}

function Install-PythonPackages {{
    $packages = @(
        "x-copilot=={version}",
        "pip"
    )
    
    foreach ($pkg in $packages) {{
        Write-Host "Installing $pkg via pip..." -ForegroundColor Yellow
        try {{
            python -m pip install --upgrade pip
            python -m pip install $pkg
            Write-Host "✓ $pkg installed" -ForegroundColor Green
        }}
        catch {{
            Write-Warning "Failed to install $pkg: $_"
        }}
    }}
}}

function Setup-XCopilot {{
    Write-Host "Setting up X-Copilot directories..." -ForegroundColor Yellow
    
    $dirs = @(
        "$InstallDir\\memory",
        "$InstallDir\\skills",
        "$InstallDir\\checkpoints",
        "$InstallDir\\graph",
        "$InstallDir\\updater"
    )
    
    foreach ($dir in $dirs) {{
        if (-not (Test-Path $dir)) {{
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
        }}
    }}
    
    # Create default config
    $configPath = "$InstallDir\\config.json"
    if (-not (Test-Path $configPath)) {{
        $config = @{{
            preferred_tools = @()
            code_style = @{{}}
            conventions = @{{}}
            anti_patterns = @()
            update = @{{
                mode = "auto"
                channel = $Channel
            }}
        }} | ConvertTo-Json -Depth 5
        Set-Content -Path $configPath -Value $config
    }}
    
    Write-Host "✓ Directories created" -ForegroundColor Green
}}

function Add-ToPath {{
    $pythonScripts = "$env:APPDATA\\Python\\Python311\\Scripts"
    $nodePath = "$env:APPDATA\\npm"
    
    $currentPath = [Environment]::GetEnvironmentVariable("PATH", "User")
    
    foreach ($path in @($pythonScripts, $nodePath)) {{
        if ($currentPath -notlike "*$path*") {{
            [Environment]::SetEnvironmentVariable("PATH", "$currentPath;$path", "User")
            Write-Host "✓ Added $path to PATH" -ForegroundColor Green
        }}
    }}
}}

function Create-Shortcut {{
    $shortcutPath = "$env:USERPROFILE\\Desktop\\X-Copilot.lnk"
    $targetPath = "python.exe"
    $arguments = "-m xcopilot.cli.main start"
    
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $targetPath
    $shortcut.Arguments = $arguments
    $shortcut.WorkingDirectory = $env:USERPROFILE
    $shortcut.Description = "X-Copilot — Self-growing AI agent"
    $shortcut.Save()
    
    Write-Host "✓ Desktop shortcut created" -ForegroundColor Green
}}

function Verify-Installation {{
    Write-Host "Verifying installation..." -ForegroundColor Yellow
    
    $checks = @(
        @{{Cmd = "python --version"; Name = "Python"}},
        @{{Cmd = "node --version"; Name = "Node.js"}},
        @{{Cmd = "npm --version"; Name = "npm"}},
        @{{Cmd = "git --version"; Name = "Git"}},
        @{{Cmd = "xcopilot --version"; Name = "X-Copilot"}}
    )
    
    foreach ($check in $checks) {{
        try {{
            $output = & cmd /c $check.Cmd 2>&1
            if ($LASTEXITCODE -eq 0) {{
                Write-Host "✓ $($check.Name): $output" -ForegroundColor Green
            }}
            else {{
                Write-Host "✗ $($check.Name): Not found" -ForegroundColor Red
            }}
        }}
        catch {{
            Write-Host "✗ $($check.Name): Error" -ForegroundColor Red
        }}
    }}
}}

# Main installation flow
try {{
    Write-Host "Step 1: Installing prerequisites via winget..." -ForegroundColor Yellow
    Install-WingetPackages
    
    Write-Host "Step 2: Installing Python packages..." -ForegroundColor Yellow
    Install-PythonPackages
    
    Write-Host "Step 3: Setting up X-Copilot..." -ForegroundColor Yellow
    Setup-XCopilot
    
    Write-Host "Step 4: Adding to PATH..." -ForegroundColor Yellow
    Add-ToPath
    
    if (-not $NoProfile) {{
        Write-Host "Step 5: Creating desktop shortcut..." -ForegroundColor Yellow
        Create-Shortcut
    }}
    
    Write-Host "Step 6: Verifying installation..." -ForegroundColor Yellow
    Verify-Installation
    
    Write-Host "`n╔══════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "║  Installation complete!                                      ║" -ForegroundColor Cyan
    Write-Host "║  Run 'xcopilot start' to begin                               ║" -ForegroundColor Cyan
    Write-Host "╚══════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
}}
catch {{
    Write-Error "Installation failed: $_"
    exit 1
}}
'''

    Path(output).write_text(installer_content, encoding="utf-8")
    console.print(f"[green]✓[/green] Generated installer: {output}")


if __name__ == "__main__":
    install()
