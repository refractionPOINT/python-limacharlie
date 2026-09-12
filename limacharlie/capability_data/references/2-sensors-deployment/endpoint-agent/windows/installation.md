# Windows Agent Installation

This guide walks you through installing the LimaCharlie Endpoint Detection and Response (EDR) sensor on Windows systems. The sensor provides deep visibility into your Windows endpoints, enabling real-time threat detection and response.

## Supported Windows Versions

**Desktop:**

- Windows 7, 8, 8.1, 10, 11

**Server:**

- Windows Server 2008 R2, 2012, 2012 R2, 2016, 2019, 2022

**Architectures:**

- x64 (64-bit) - Most common
- x86 (32-bit) - Legacy systems
- ARM64 - Windows on ARM devices

## Prerequisites

Before installing the LimaCharlie sensor, ensure you have:

1. **Administrator privileges** on the Windows system
2. **An Installation Key** from your LimaCharlie organization
3. **Network access** to LimaCharlie cloud services (outbound HTTPS on port 443)

## Getting Your Installation Key

An Installation Key is required to enroll your sensor with the LimaCharlie cloud. To obtain your key:

1. Log in to the [LimaCharlie web application](https://app.limacharlie.io)
2. Select your organization
3. Navigate to **Sensors** > **Installation Keys** in the left sidebar
4. Copy an existing key, or create a new one by clicking **Create Installation Key**
5. Keep this key ready - you'll need it during installation

For more details on managing keys, see [Installation Keys](../../installation-keys.md).

> **Tip:** Installation keys can have tags associated with them. When a sensor enrolls using a key with tags, those tags are automatically applied to the sensor.

## Downloading the Sensor

Choose the correct download for your system architecture:

### Executable (EXE) Downloads

| Architecture | Download Link |
|--------------|---------------|
| 64-bit (x64) | [https://downloads.limacharlie.io/sensor/windows/64](https://downloads.limacharlie.io/sensor/windows/64) |
| 32-bit (x86) | [https://downloads.limacharlie.io/sensor/windows/32](https://downloads.limacharlie.io/sensor/windows/32) |
| ARM64 | [https://downloads.limacharlie.io/sensor/windows/arm64](https://downloads.limacharlie.io/sensor/windows/arm64) |

> **Note:** A native ARM64 build is available for Windows on ARM devices (sensor 4.33.26 or later). Earlier sensor versions ran under x64 emulation; this is no longer required.

### MSI Installer Downloads

| Architecture | Download Link |
|--------------|---------------|
| 64-bit (x64) | [https://downloads.limacharlie.io/sensor/windows/msi64](https://downloads.limacharlie.io/sensor/windows/msi64) |
| 32-bit (x86) | [https://downloads.limacharlie.io/sensor/windows/msi32](https://downloads.limacharlie.io/sensor/windows/msi32) |
| ARM64 | [https://downloads.limacharlie.io/sensor/windows/msiarm64](https://downloads.limacharlie.io/sensor/windows/msiarm64) |

> **Note about downloaded filenames:** The downloaded file will have a versioned name like `hcp_win_x64_release_4.33.23.exe`. You can rename it to `rphcp.exe` for convenience, or use the original filename in commands.
>
> **How do I know which architecture I need?**
>
> On Windows 10/11: Go to **Settings** > **System** > **About** and look at **System type**.
>
> On older Windows: Right-click **Computer** > **Properties** and check the **System type**.

## Command-Line Options

When running the installer from the command line, you can use the following options:

| Option | Description |
|--------|-------------|
| `-i <KEY>` | Install as a Windows service with the specified installation key |
| `-d <KEY>` | Run with installation key (temporary, no permanent installation) |
| `-r` | Uninstall the service |
| `-c` | Uninstall the service and delete identity files (clean uninstall) |
| `-V` | Display the sensor version |
| `-v` | Enable verbose logging output |
| `-H` | Verify sensor health and installation |
| `-h` | Display help message |

For the complete list of options, environment variables, and local files, see the [Agent CLI & Environment Reference](../cli-reference.md).

## Installation Methods

### Method 1: Executable (EXE) Installation

This method is recommended for installing on individual systems.

**Step 1:** Download the appropriate EXE for your architecture (see download links above).

**Step 2:** Open **Command Prompt** or **PowerShell** as Administrator.

> To run as Administrator: Right-click Command Prompt or PowerShell and select **Run as administrator**.

**Step 3:** Navigate to the folder where you downloaded the installer:

```bash
cd C:\Users\YourUsername\Downloads
```

**Step 4:** Run the installer with your Installation Key:

```batch
rphcp.exe -i YOUR_INSTALLATION_KEY_GOES_HERE
```

Replace `YOUR_INSTALLATION_KEY_GOES_HERE` with the actual key you copied from the LimaCharlie web application.

**Step 5:** Wait for the installation to complete. You should see output indicating successful installation and service start.

The sensor is now installed and running as a Windows service. It will start automatically when Windows boots.

### Method 2: MSI Installation

MSI installers are ideal for enterprise deployment using tools like Group Policy, SCCM, or Intune.

#### Interactive Installation

1. Download the appropriate MSI for your architecture
2. Double-click the MSI file to launch the installer
3. Follow the installation prompts

> **Note:** The MSI installation will require you to provide the Installation Key. Ensure you have it ready.

#### Silent Installation (Command Line)

For automated deployments, use the following command in an elevated Command Prompt or PowerShell:

```batch
msiexec /i "path\to\installer.msi" /qn INSTALLATIONKEY="YOUR_INSTALLATION_KEY_GOES_HERE"
```

Example with a specific MSI:

```batch
msiexec /i "C:\Downloads\hcp_win_x64.msi" /qn INSTALLATIONKEY="YOUR_INSTALLATION_KEY_GOES_HERE"
```

Options explained:

- `/i` - Install the package
- `/qn` - Quiet mode with no user interface
- `INSTALLATIONKEY` - The LimaCharlie installation key for enrollment

### Method 3: PowerShell Script (Automated)

This script automates the download and installation process. It detects your system architecture and downloads the correct installer.

> **Note:** This script requires PowerShell 3.0 or later. Windows 7 and Server 2008 R2 ship with PowerShell 2.0 by default; you may need to install [Windows Management Framework 3.0+](https://www.microsoft.com/en-us/download/details.aspx?id=34595) first.

Save this script as `Install-LimaCharlie.ps1`:

```powershell
#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Downloads and installs the LimaCharlie sensor.
.DESCRIPTION
    This script detects the system architecture, downloads the appropriate
    LimaCharlie sensor installer, and installs it as a Windows service.
.PARAMETER InstallationKey
    The LimaCharlie installation key for enrollment.
#>

param(
    [Parameter(Mandatory=$true)]
    [string]$InstallationKey
)

# Determine system architecture using WMI for accurate detection
$CpuArch = (Get-CimInstance -ClassName Win32_Processor).Architecture
# Architecture values: 0 = x86, 9 = x64, 12 = ARM64
$Arch = switch ($CpuArch) {
    0  { "32" }
    9  { "64" }
    12 { "arm64" }
    default { if ([Environment]::Is64BitOperatingSystem) { "64" } else { "32" } }
}

Write-Host "Detected architecture: $Arch" -ForegroundColor Cyan

# Set download URL and local path
$InstallerUrl = "https://downloads.limacharlie.io/sensor/windows/$Arch"
$TempDownload = Join-Path $env:TEMP "lc_sensor_download.exe"
$InstallerPath = Join-Path $env:TEMP "rphcp.exe"

# Download the installer (filename from server varies, so we normalize it)
Write-Host "Downloading LimaCharlie sensor..." -ForegroundColor Cyan
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $InstallerUrl -OutFile $TempDownload -UseBasicParsing
    # Rename to consistent filename
    Move-Item -Path $TempDownload -Destination $InstallerPath -Force
    Write-Host "Download complete." -ForegroundColor Green
} catch {
    Write-Host "Error downloading installer: $_" -ForegroundColor Red
    Remove-Item $TempDownload -Force -ErrorAction SilentlyContinue
    exit 1
}

# Install the sensor
Write-Host "Installing LimaCharlie sensor..." -ForegroundColor Cyan
try {
    $process = Start-Process -FilePath $InstallerPath -ArgumentList "-i", $InstallationKey -Wait -PassThru -NoNewWindow
    if ($process.ExitCode -eq 0) {
        Write-Host "Installation successful!" -ForegroundColor Green
    } else {
        Write-Host "Installation may have encountered issues. Exit code: $($process.ExitCode)" -ForegroundColor Yellow
    }
} catch {
    Write-Host "Error during installation: $_" -ForegroundColor Red
    exit 1
}

# Verify installation
Write-Host "Verifying installation..." -ForegroundColor Cyan
$service = Get-Service -Name "rphcpsvc" -ErrorAction SilentlyContinue
if ($service -and $service.Status -eq "Running") {
    Write-Host "LimaCharlie sensor is installed and running." -ForegroundColor Green
} else {
    Write-Host "Warning: Service may not be running. Please check manually." -ForegroundColor Yellow
}

# Clean up
Remove-Item $InstallerPath -Force -ErrorAction SilentlyContinue
```

**To run the script:**

1. Open PowerShell as Administrator
2. If you haven't already, allow script execution:

   ```powershell
   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
   ```

3. Run the script with your Installation Key:

   ```powershell
   .\Install-LimaCharlie.ps1 -InstallationKey "YOUR_INSTALLATION_KEY_GOES_HERE"
   ```

## Verifying Installation

After installation, verify that the sensor is running correctly using any of these methods:

### Windows Services GUI

1. Press `Win + R`, type `services.msc`, and press Enter
2. Scroll down to find **LimaCharlie** in the list
3. Verify that the **Status** is **Running** and **Startup Type** is **Automatic**

### PowerShell

Run this command to check the service status:

```powershell
Get-Service rphcpsvc | Select-Object Name, Status, StartType
```

Expected output:

```text
Name     Status StartType
----     ------ ---------
rphcpsvc Running Automatic
```

### Command Prompt

Run this command:

```text
sc query rphcpsvc
```

Look for `STATE : 4  RUNNING` in the output.

### Verification Script

Save and run this PowerShell script for a quick status check:

```powershell
# Verify LimaCharlie installation
$service = Get-Service -Name "rphcpsvc" -ErrorAction SilentlyContinue
if ($null -eq $service) {
    Write-Host "LimaCharlie sensor is NOT installed." -ForegroundColor Red
} elseif ($service.Status -eq "Running") {
    Write-Host "LimaCharlie sensor is installed and running." -ForegroundColor Green
    Write-Host "  Service Name: $($service.Name)"
    Write-Host "  Display Name: $($service.DisplayName)"
    Write-Host "  Start Type:   $($service.StartType)"
} else {
    Write-Host "LimaCharlie sensor is installed but NOT running." -ForegroundColor Yellow
    Write-Host "  Current Status: $($service.Status)"
}
```python

### LimaCharlie Web Application

1. Log in to [app.limacharlie.io](https://app.limacharlie.io)
2. Navigate to **Sensors** in the left sidebar
3. Your newly installed sensor should appear in the list within a few minutes

## Troubleshooting

### "Access Denied" Error

**Cause:** The installer must be run with Administrator privileges.

**Solution:** Right-click Command Prompt or PowerShell and select **Run as administrator** before running the installer.

### Architecture Mismatch Error

**Cause:** Using a 32-bit installer on a 64-bit system (or vice versa).

**Solution:** Download and use the correct installer for your system architecture. The sensor will display an error message indicating the mismatch.

### Antivirus Blocking Installation

**Cause:** Some antivirus software may flag the sensor installer.

**Solution:**
1. Temporarily disable your antivirus during installation, OR
2. Add an exclusion for `rphcp.exe` and `C:\Windows\System32\rphcp.exe`
3. Contact your antivirus vendor if issues persist

### Firewall Blocking Connection

**Cause:** The sensor cannot reach LimaCharlie cloud services.

**Solution:** Ensure outbound HTTPS (port 443) traffic is allowed to:
- `*.limacharlie.io`

### Installation Key Errors

**Cause:** The installation key is invalid, expired, or incorrectly copied.

**Solution:**
1. Verify the key in the LimaCharlie web application
2. Ensure you copied the entire key without extra spaces
3. Check that the key hasn't been revoked or expired

### Service Won't Start

**Cause:** Various issues including file permission problems or system configuration.

**Solution:**
1. Check Windows Event Viewer (Application and System logs) for errors
2. Ensure the system meets minimum requirements
3. Try reinstalling with the `-c` flag first to clean up, then install fresh

## Uninstallation

### Using the Executable

Run the installer with the clean uninstall flag:

```

rphcp.exe -c

```text

This removes the service and deletes all identity files.

To uninstall but keep identity files (for potential reinstallation):

```

rphcp.exe -r

```text

### Using the MSI

1. Open **Control Panel** > **Programs** > **Programs and Features**
2. Find **LimaCharlie** in the list
3. Click **Uninstall**

Or via command line:

```

msiexec /x "path\to\installer.msi" /qn

```text

### Using LimaCharlie Console

You can remotely uninstall the sensor from the LimaCharlie web application:

1. Navigate to the sensor in the Sensors list
2. Open the **Console** tab
3. Run the command: `uninstall`

For MSI installations, use: `uninstall --msi`

For more uninstallation options, see [Endpoint Agent Uninstallation](../uninstallation.md).

## Next Steps

Now that your sensor is installed, you can:

- [Configure Detection & Response rules](../../../3-detection-response/index.md) to detect threats
- [Explore Sensor Commands](../../../8-reference/endpoint-commands.md) to interact with your endpoints
- [Build a Custom MSI](custom-msi.md) with your branding for enterprise deployment
- [Deploy via Microsoft Intune](../../enterprise-deployment/intune.md) for large-scale rollout
