# Kubernetes Pods Logs

## Overview

This Adapter allows you to ingest the logs from the pods running in a Kubernetes cluster.

The adapter relies on local filesystem access to the standard Kubernetes pod logging structure. This means the adapter is best run as a Daemon Set in Kubernetes with the pod logs location mounted (usually `/var/log/pods`).

A [public Docker container](https://hub.docker.com/r/refractionpoint/lc-adapter-k8s-pods) is available as `refractionpoint/lc-adapter-k8s-pods`.

## Configurations

Adapter Type: `k8s_pods`

The following fields are required for configuration:

- `client_options`: see [common adapter configuration](../usage.md).
- `root`: The root of the Kubernetes directory storing logs, usually `/var/log/pods`.

### Infrastructure as Code Deployment

```python
sensor_type: "k8_pods"
k8s_pods:
    client_options:
      identity:
        oid: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
        installation_key: "YOUR_LC_INSTALLATION_KEY_K8SPODS"
      hostname: "k8s-worker-node"
      platform: "k8s_pods"
      sensor_seed_key: "k8s-pods-sensor"
    root: "/var/log/pods"                              # Required: Pod logs directory
    write_timeout_sec: 600                             # Optional: defaults to 600
    include_pods_re: "^production_.*"                  # Optional: include filter
    exclude_pods_re: "^kube-system_kube-proxy-.*$"    # Optional: exclude filter
```

## Sample Kubernetes Configuration

An example Daemon Set configuration for Kubernetes:

```yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: lc-adapter-k8s-pods
  namespace: default
spec:
  minReadySeconds: 30
  selector:
    matchLabels:
      name: lc-adapter-k8s-pods
  template:
    metadata:
      labels:
        name: lc-adapter-k8s-pods
    spec:
      containers:
      - image: refractionpoint/lc-adapter-k8s-pods
        name: lc-adapter-k8s-pods
        volumeMounts:
        - mountPath: /k8s-pod-logs
          name: pod-logs
        env:
        - name: K8S_POD_LOGS
          value: /k8s-pod-logs
        - name: OID
          value: aaaaaaaa-bfa1-bbbb-cccc-138cd51389cd
        - name: IKEY
          value: aaaaaaaa-9ae6-bbbb-cccc-5e42b854adf5
        - name: NAME
          value: k8s-pods
      volumes:
      - hostPath:
          path: /var/log/pods
        name: pod-logs
  updateStrategy:
    rollingUpdate:
      maxUnavailable: 1
    type: RollingUpdate
```
