# Docker Agent Installation

## Docker

The LimaCharlie agent is designed to run within a Docker container, providing seamless integration with containerized environments. Running the agent in a container allows for efficient deployment and management while ensuring security monitoring and telemetry collection.

Additionally, the agent can also be deployed on various container cluster technologies, such as Kubernetes. For Kubernetes deployment details, refer to [Container Clusters](../containers/clusters.md).

## Host Visibility Requirements

For the LimaCharlie agent to have full visibility into activities on the host system, the following configurations are required:

- The container must run in **privileged mode** to access host-level resources.
- The container must use **host networking** to observe network activity.
- The container must use **host PID mode** to track running processes.
- Various **host-level directories** must be mounted into the container, including:

  - The root filesystem (`rootfs`)
  - Docker network namespaces (`netns`)
  - The directory containing kernel modules and debug symbols

Additionally, on newer Linux kernel versions (5.7+), the agent leverages **eBPF** for enhanced visibility and telemetry collection.

## Agent Docker Image

Build your own agent image so you get the latest agent version and control the base distribution:

```dockerfile
# Requires an LC_INSTALLATION_KEY environment variable at runtime
# specifying the installation key value.
FROM debian:12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /lc

# Fetch the latest official glibc x64 sensor at build time.
RUN curl -fsSL https://downloads.limacharlie.io/sensor/linux/64 -o lc_sensor \
    && chmod 500 ./lc_sensor

# Where the host's root filesystem and network namespaces directory
# are mounted within the container.
ENV HOST_FS=/rootfs
ENV NET_NS=/netns

CMD ["./lc_sensor", "-d", "-"]
```

Rebuild the image regularly so new deployments pick up the latest agent version.

!!! warning "eBPF requires a glibc-based image"
    Kernel-level telemetry on Linux is only available for **glibc-based x64 sensors** (Debian, Ubuntu, RHEL/Rocky, etc.). An Alpine (musl) based image using the `alpine64` sensor binary will always operate in usermode acquisition, without eBPF kernel visibility.

## Available Environment Variables

The agent supports several environment variables to control its behavior:

- `LC_INSTALLATION_KEY` - Specifies the installation key required to authenticate the agent.
- `HOST_FS` - Defines the path where the host's root filesystem is mounted within the container. Example: `/rootfs`.
- `NET_NS` - Specifies the path to the host's network namespace directory. Example: `/netns`.

These variables must be configured appropriately to ensure the agent functions as expected.

## Running the Agent Using Docker CLI

To run the LimaCharlie agent in a Docker container, use the following command:

```bash
docker run --privileged --net=host \
  -v /:/rootfs:ro \
  -v /var/run/docker/netns:/netns:ro \
  -v /sys/kernel/debug:/sys/kernel/debug:ro \
  -v /sys/kernel/btf:/sys/kernel/btf:ro \
  -v /lib/modules:/lib/modules:ro \
  --env LC_INSTALLATION_KEY=<your_key> \
  --env HOST_FS=/rootfs \
  --env NET_NS=/netns \
  your-registry.example.com/lc-sensor:your-tag
```

Ensure that you replace `<your_key>` with your actual LimaCharlie installation key.

## Running the Agent Using Docker Compose

You can also manage the LimaCharlie agent using Docker Compose. Below is a sample `docker-compose.yml` file:

```yaml
services:
  lc-sensor:
    image: your-registry.example.com/lc-sensor:your-tag
    restart: unless-stopped
    network_mode: "host"
    pid: "host"
    privileged: true
    environment:
      - HOST_FS=/rootfs
      - NET_NS=/netns
      - LC_INSTALLATION_KEY=<your key>
    deploy:
      resources:
        limits:
          cpus: "0.9"
          memory: "256M"
        reservations:
          cpus: "0.01"
          memory: "128M"
    cap_add:
      - SYS_ADMIN
    volumes:
      - /:/rootfs
      - /var/run/docker/netns:/netns
      - /sys/kernel/debug:/sys/kernel/debug
      - /sys/kernel/btf:/sys/kernel/btf
      - /lib/modules:/lib/modules
```

To start the container, run:

```bash
docker-compose up -d
```

This setup ensures the agent runs as a privileged container, enabling full visibility into the host system while being managed through Docker Compose.
