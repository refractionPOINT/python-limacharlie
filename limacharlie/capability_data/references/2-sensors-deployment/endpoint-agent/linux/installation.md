# Linux Agent Installation

The LimaCharlie Linux Sensor runs on every mainstream Linux distribution and architecture (x86_64, i386, ARM64, Alpine/musl). It is shipped as a single binary that adapts at runtime to the kernel features available on the host — there is no separate build or installer per mode. On modern kernels it uses eBPF for in-kernel telemetry; on older kernels it transparently falls back to lighter mechanisms.

## Linux Distribution Support

The agent is regularly tested against current Debian, Ubuntu, CentOS/RHEL/Rocky/Alma, Amazon Linux, and Alpine releases on x86_64 and ARM64. Because of the diversity of the Linux ecosystem it usually runs unmodified on other distributions as well — if you need to validate a specific platform, contact us.

### Kernel Feature Tiers

The agent picks the most capable acquisition mode supported by the host kernel and degrades gracefully when newer features are not available. All tiers run **the same binary** — selection happens at startup.

| Tier | Minimum kernel | Acquisition path | What you get |
|------|----------------|------------------|--------------|
| User-mode only | any (incl. 2.4 / 2.6 era) | `/proc` polling | Inventory of running processes, host metadata, live response, file integrity, USB monitoring, YARA scans, network isolation, and all detection-and-response features that operate from user space. **No real-time process / file / network / DNS kernel events.** |
| User-mode + netlink connector | 2.6.15 | `/proc` polling + netlink `CN_PROC` connector | Adds real-time process create / exit notifications from the kernel. Process command-line and executable path are still scraped post-event from `/proc`, so very short-lived processes can be missed. |
| User-mode + eBPF (default when available) | 5.7+ recommended | eBPF programs (CO-RE / BTF) attached for processes, files, network, DNS | Full in-kernel telemetry: process exec with reliable cmdline capture, file I/O, TCP / UDP connections, DNS queries — collected synchronously and attributed to the originating task. This is the mode used on supported modern systems. |

The agent does **not** require eBPF, kernel headers, or `bpftool` to be installed on the target host — the eBPF programs are pre-compiled into the binary and loaded via libbpf using BTF when the kernel exposes it (`/sys/kernel/btf/vmlinux`). On kernels without BTF / CO-RE the agent automatically remains in the netlink or user-mode tier.

Use `uname -r` to check the host kernel version. If it is below 5.4, expect the agent to run in netlink (2.6.15+) or user-mode-only (anything older) tier with reduced kernel telemetry but full agent control-plane functionality.

### Forcing a lower tier

The agent exposes one runtime override for compatibility scenarios (the eBPF tier has no opt-out — it is selected only when the kernel actually supports it):

- `DISABLE_NETLINK` — set to any value in the sensor process environment to skip the netlink connector. Used when an unrelated component on the host already consumes netlink proc events or when the connector behaves unexpectedly. Has no effect when eBPF is in use.

## Installation Instructions

### System Requirements

The agent runs on glibc-based distributions back to **glibc 2.12** (released May 2010). In practice that covers:

- RHEL / CentOS / Oracle Linux **6** and newer (glibc 2.12)
- Debian **7** (wheezy) and newer (glibc 2.13)
- Ubuntu **12.04 LTS** and newer (glibc 2.15)

Anything below that baseline — RHEL / CentOS **5** (glibc 2.5), Debian 6 (2.11), Ubuntu 10.04 (2.11) — is not supported by the standard glibc build. For those hosts, or for non-glibc systems, use the **Alpine / musl** build, which is statically linked and has no host libc dependency.

On distributions this old, expect reduced kernel telemetry: RHEL / CentOS 6 ships kernel 2.6.32, which supports the netlink proc connector tier (real-time process create / exit) but not eBPF. Check the tier table above for what each kernel generation provides.

Run `ldd --version` to check the glibc version on a host.

### Deb Package

If you are deploying on a Debian Linux system, we recommend using the `.deb` package. You can find a link to the Debian package for various architectures at [Downloading the Agent](../../index.md).

The deb package will install the LimaCharlie sensor using a `systemd` service, or if unavailable a `system V` service.

The Installation Key is required by the installer via the `debconf` configuration mechanism. By default, installing the package interactively will request the installation key via a local command/GUI interface. To perform large scale installations, we recommend setting the installation key programmatically.

**Installing interactively:**

```python
sudo dpkg -i limacharlie.deb
```

or

```python
sudo apt install ./limacharlie.deb
```

**Uninstalling interactively:**

```bash
sudo dpkg -r limacharlie
```

or

```bash
sudo apt remove limacharlie
```

**Installing and setting the installation key programmatically with dpkg:**

```powershell
echo "limacharlie limacharlie/installation_key string INSTALLATION_KEY_HERE" | sudo debconf-set-selections && sudo dpkg -i limacharlie.deb
```

**Installing and setting the installation key programmatically with apt:**

```powershell
echo "limacharlie limacharlie/installation_key string INSTALLATION_KEY_HERE" | sudo debconf-set-selections && sudo apt install ./limacharlie.deb -y
```

Debian packages are offered for the various architectures the Linux sensor supports, like:

- **x64**: <https://downloads.limacharlie.io/sensor/linux/deb64>
- **arm64**: <https://downloads.limacharlie.io/sensor/linux/debarm64>

### RPM Package

If you are deploying on an RPM-based Linux distribution (RHEL, CentOS, Rocky, AlmaLinux, Fedora, openSUSE, Amazon Linux), use the `.rpm` package.

The rpm package will install the LimaCharlie sensor as a `systemd` service.

Unlike the `.deb` package, RPM has no native interactive prompt mechanism — the installation key cannot be requested at install time. Instead, the post-install scriptlet looks for the key in one of two locations, in this order:

1. The `LC_INSTALLATION_KEY` environment variable.
2. The file `/etc/limacharlie/installation_key`.

If neither is present the package install will abort with an explanatory error before any system state is changed, so a missing key never leaves the host in a half-configured state.

**Installing with the environment variable:**

```bash
sudo LC_INSTALLATION_KEY=INSTALLATION_KEY_HERE rpm -i limacharlie.rpm
```

or with `dnf` / `yum`:

```bash
sudo LC_INSTALLATION_KEY=INSTALLATION_KEY_HERE dnf install ./limacharlie.rpm
```

**Installing with the key file:**

```bash
sudo mkdir -p /etc/limacharlie
echo "INSTALLATION_KEY_HERE" | sudo tee /etc/limacharlie/installation_key >/dev/null
sudo chmod 600 /etc/limacharlie/installation_key
sudo rpm -i limacharlie.rpm
```

The key file is read once during install. You can delete it afterwards if you don't want the key sitting on disk — the sensor's own enrollment files take over from there.

**Uninstalling:**

```bash
sudo rpm -e limacharlie
```

or

```bash
sudo dnf remove limacharlie
```

Uninstall stops the service and removes the sensor binary, identity files, and the package staging directory.

RPM packages are offered for the architectures the Linux sensor supports, like:

- **x64**: <https://downloads.limacharlie.io/sensor/linux/rpm64>
- **arm64**: <https://downloads.limacharlie.io/sensor/linux/rpmarm64>

### Custom Installation

For systems where neither the `.deb` nor the `.rpm` package fits (e.g. distributions without `dpkg` or `rpm`, or installs that need a non-standard layout), download the installer directly using the following command:

```python
wget https://downloads.limacharlie.io/sensor/linux/64 -O /tmp/lc_sensor
```

> Other Linux Versions
>
> If installing on an ARM64 or Alpine64 system, replace the URL in the command above with the respective URL from the installation wizard within LimaCharlie

Executing the installer via the command line, pass the `-d INSTALLATION_KEY` argument where `INSTALLATION_KEY` is the key mentioned above.

Because Linux supports a plethora of service management frameworks, by default the LC sensor does not install itself onto the system. Rather it assumes the "current working directory" is the installation directory and immediately begins enrollment from there.

This means you can wrap the executable using the specific service management technology used within your Organization by simply specifying the location of the installer, the `-d INSTALLATION_KEY` parameter and making sure the current working directory is the directory where you want the few sensor-related files written to disk to reside.

A common methodology for Linux is to use `init.d`, if this is sufficient for your needs, see this [sample install script](https://github.com/refractionPOINT/lce_doc/blob/master/docs/lc_linux_installer.sh).
You can invoke it like this:

```bash
sudo chmod +x ./lc_linux_installer.sh
sudo ./lc_linux_installer.sh <PATH_TO_LC_SENSOR> <YOUR_INSTALLATION_KEY>
```

You may also pass the value `-` instead of the `INSTALLATION_KEY` like: `-d -`. This will make the installer look for the installation key in an alternate place in the following order:

- Environment variable `LC_INSTALLATION_KEY`
- Text file in current working directory: `lc_installation_key.txt`

### Disabling Netlink

By default, when running on a kernel where eBPF is unavailable, the Linux sensor uses the netlink proc connector (`CN_PROC`) to receive real-time process events. In some rare configurations this auto-detection may be unwanted — for example when another agent on the host already consumes the same connector — and netlink usage can be disabled by setting the environment variable `DISABLE_NETLINK` to any value on the sensor process. With netlink disabled and no eBPF available, the agent falls back to user-mode `/proc` polling. This setting has no effect when eBPF is the active acquisition path.

### Custom Data Directory

The sensor stores its data and status files under `/opt/limacharlie` by default. On non-standard or hardened distributions where that path is not writable, you can point the sensor at a different directory by setting the `LC_DATA_DIRECTORY` environment variable on the sensor process to an absolute path. The directory must exist and be writable by the sensor.

### Restricting DNS Tracking to an Interface

By default DNS tracking watches all network interfaces. To restrict it to a single interface, set the `LC_DNS_IFACE` environment variable to the interface name (for example `LC_DNS_IFACE=eth0`) on the sensor process.

For the complete list of supported options, see the [Agent CLI & Environment Reference](../cli-reference.md).

## Uninstalling the Agent

For additional agent uninstall options, see [Endpoint Agent Uninstallation](../uninstallation.md)

Linux agent uninstallation depends on how the sensor was installed. For example, if installed via a Debian package (`dpkg` file) or an RPM package (`rpm` / `dnf` / `yum`), you should uninstall via the same package manager. If you installed via the SystemV installation method, please utilize the bottom of [this script](https://github.com/refractionPOINT/lce_doc/blob/master/docs/lc_linux_installer.sh#L97).

### Sensor Command

The `uninstall` command does not work for Linux systems. However, there is a chained command that can be run from the Sensor Console:

```powershell
 run --shell-command "service limacharlie stop; rm /bin/rphcp; update-rc.d limacharlie remove -f; rm -rf /etc/init.d/limacharlie; rm /etc/hcp ; rm /etc/hcp_conf; rm /etc/hcp_hbs"
```

The above command removes LimaCharlie and associated files from the system when run remotely. Note that the above command could also be coupled with a rule for automated sensor uninstallation, if necessary.

### Debian Systems

If the sensor was originally installed with the .deb file, this option is the cleanest uninstall method.

```bash
apt remove limacharlie
```

### RPM-based Systems

If the sensor was originally installed with the .rpm file, use the matching package manager:

```bash
sudo dnf remove limacharlie
```

or

```bash
sudo rpm -e limacharlie
```
