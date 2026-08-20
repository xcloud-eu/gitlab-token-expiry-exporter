# Complete Helm installation

End-to-end: token, secret, values, install, verify.

## 1. Create the GitLab token

In GitLab: your group → *Settings → Access tokens* → role **Owner**, scope
**read_api**. Owner is required because GitLab only lets Owners list access
tokens; the token's group also bounds what gets scanned.

## 2. Put the token in a Secret

The chart defaults to a Secret named after the release with key
`GITLAB_READ_TOKEN`. For a release named `tokens` in namespace `monitoring`:

```sh
kubectl create namespace monitoring
kubectl -n monitoring create secret generic tokens-gitlab-token-expiry-exporter \
  --from-literal=GITLAB_READ_TOKEN=glpat-xxxxxxxxxxxxxxxxxxxx
```

(Prefer a secret manager in real deployments — see
[externalsecret.yaml](externalsecret.yaml) for the external-secrets variant.)

## 3. Values

```yaml
# values.yaml
gitlab:
  url: https://gitlab.example.com
  groups:
    - my-org
    - another-org/infrastructure

# match your Prometheus operator's selectors (these are the
# kube-prometheus-stack defaults)
serviceMonitor:
  additionalLabels:
    release: kube-prometheus-stack
prometheusRule:
  additionalLabels:
    release: kube-prometheus-stack
  # optional tuning
  expiringSoonDays: 14

# optional tuning
refreshHours: 4
```

## 4. Install

```sh
helm install tokens \
  oci://ghcr.io/xcloud-eu/charts/gitlab-token-expiry-exporter \
  --version 0.4.0 -n monitoring -f values.yaml
```

## 5. Verify

```sh
kubectl -n monitoring get pods -l app.kubernetes.io/name=gitlab-token-expiry-exporter
kubectl -n monitoring port-forward svc/tokens-gitlab-token-expiry-exporter 9184 &
curl -s localhost:9184/metrics | head
```

The pod turns Ready only after its first successful scan; until the Secret from
step 2 exists it stays in `CreateContainerConfigError`. The Grafana dashboard
appears automatically if you run the grafana sidecar (`dashboard.enabled` is on
by default).
