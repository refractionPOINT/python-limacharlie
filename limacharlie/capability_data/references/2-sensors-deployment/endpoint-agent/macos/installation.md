# macOS Agent Installation - Older Versions (macOS 10.15 Catalina to macOS 14 Sonoma)

This document provides details of how to install, verify, and uninstall the LimaCharlie Endpoint Agent on macOS (versions 10.15 Catalina though to macOS 14 Sonoma). We also offer documentation for [macOS 10.14 and prior](installation-older.md), and [macOS 10.15 and newer](sequoia.md).

## Installer Options

When running the installer from the command line, you can pass the following arguments:

```text
-v: verbose logging output.
-V: display the sensor build version.
-d <INSTALLATION_KEY>: the installation key to use to enroll, no permanent installation.
-i <INSTALLATION_KEY>: install executable as a service with deployment key.
-r: uninstall executable as a service.
-c: uninstall executable as a service and delete identity files.
-H: verify sensor health and write a diagnostic report.
-w: executable is running as a macOS service.
-h: displays the list of accepted arguments.
```

For the complete list of options, environment variables, and local files, see the [Agent CLI & Environment Reference](../cli-reference.md).

## Installation Flow

1. Download the Sensor installer file. Installer for: [Intel Mac](https://downloads.limacharlie.io/sensor/mac/64) -or- [Apple Silicon Mac](https://downloads.limacharlie.io/sensor/mac/arm64).
2. Add execute permission to the installer file via the command line

> chmod +x lc\_sensor

1. Run the installer via the command line. You'll pass the argument -i and your Installation Key.

> sudo ./lc\_sensor -i YOUR\_INSTALLATION\_KEY\_GOES\_HERE

![Basic installation](https://storage.googleapis.com/limacharlie-io/doc/sensor-installation/macOS/images/Installation/01-Basic_installation.png)

You can obtain the installation key from the [Installation Keys](../../installation-keys.md) section of the LimaCharlie web application.

The sensor will be installed as a launchctl service. Installation will trigger the sensors enrollment with the LimaCharlie cloud.

![Installation success](https://storage.googleapis.com/limacharlie-io/doc/sensor-installation/macOS/images/Installation/02-Installation_success.png)

1. An application (`RPHCP.app`) will be installed in the /Applications folder and will automatically launch. You will be prompted to grant permissions for system extensions to be installed.

![Permissions required](https://storage.googleapis.com/limacharlie-io/doc/sensor-installation/macOS/images/Installation/03-Permissions_Required.png)

1. Click the "Open System Preferences" button

![System Extensions Required](https://storage.googleapis.com/limacharlie-io/doc/sensor-installation/macOS/images/Installation/04-System_Extension_Required.png)

1. Unlock the preference pane using the padlock in the bottom left corner, then click the Allow button next to `System software from application "RPHCP" was blocked from loading.`

![Unlocked](https://storage.googleapis.com/limacharlie-io/doc/sensor-installation/macOS/images/Installation/06-Allow_System_Software_Unlocked.png)

1. You'll be prompted to allow the application to Filter Network Content. Click the Allow button.

![Network filter](https://storage.googleapis.com/limacharlie-io/doc/sensor-installation/macOS/images/Installation/07--Network_Filter.png)

1. You'll be prompted to grant Full Disk Access. Check the checkbox next to the RPHCP app in System Preferences -> Privacy -> Full Disk Access

![Full disk access](https://storage.googleapis.com/limacharlie-io/doc/sensor-installation/macOS/images/Installation/08-Full_Disk_Access.png)

The installation is now complete and you should see a message indicating that the installation was successful.

![Success](https://storage.googleapis.com/limacharlie-io/doc/sensor-installation/macOS/images/Installation/09-Success.png)

## Verifying Installation

To verify that the sensor was installed successfully, you can log into the LimaCharlie web application and see if the device has appeared in the Sensors section. Additionally, you can check the following on the device itself:

In a Terminal, run the command:

> sudo launchctl list | grep com.refractionpoint.rphcp

![Successful installation verification](https://storage.googleapis.com/limacharlie-io/doc/sensor-installation/macOS/images/Verification/Verification-installation-successful.png)

If the agent is running, this command should return records as shown above.

You can also check the /Applications folder and launch the RPHCP.app.

![Applications folder](https://storage.googleapis.com/limacharlie-io/doc/sensor-installation/macOS/images/Installation/10-Applications.png)

The application will show a message to indicate if the required permissions have been granted.

![App installed correctly](https://storage.googleapis.com/limacharlie-io/doc/sensor-installation/macOS/images/Installation/11-App_Installed_Correctly.png)

As described in the dialog, the RPHCP.app application must be left in the /Applications folder in order for it to continue operating properly.

### A note on permissions

Apple has purposely made installing extensions (like the ones used by LimaCharlie) a process that requires several clicks on macOS. The net effect of this is that the first time the sensor is installed on a macOS system, permissions will need to be granted via System Preferences

Currently, the only way to automate the installation is to use an Apple-approved MDM solution. These solutions are often used by large organizations to manage their Mac fleet. If you are using such a solution, see your vendor's documentation on how to add extensions to the allow list which can be applied to your entire fleet.

We're aware this is an inconvenience and hope Apple will provide better solutions for security vendors in future.

## Uninstallation Flow

To uninstall the sensor:

1. Run the installer via the command line. You'll pass the argument -c

> sudo ./hcp\_osx\_x64\_release\_4.23.0 -c

![Uninstall progress](https://storage.googleapis.com/limacharlie-io/doc/sensor-installation/macOS/images/Uninstallation/1-Uninstall_Progress.png)

1. You will be prompted for credentials to modify system extensions. Enteryour password and press OK.

![Uninstall permissions](https://storage.googleapis.com/limacharlie-io/doc/sensor-installation/macOS/images/Uninstallation/2-Uninstaller_Permissions.png)

The related system extension will be removed and the `RPHCP.app` will be removed from the /Applications folder.

1. You should see a message indicating that the uninstallation was successful.

![Uninstall success](https://storage.googleapis.com/limacharlie-io/doc/sensor-installation/macOS/images/Uninstallation/3-Uninstall_Success.png)

## Install Using MDM Solutions

See our document [macOS Agent Installation with MDM Solutions](mdm-profiles.md) for the Mobile Device Management (MDM) Configuration Profile that can be used to deploy the LimaCharlie agent to an enterprise fleet.
