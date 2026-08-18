# gitlab-token-expiry-exporter

A Prometheus exporter that reports the expiry of **GitLab group and project access
tokens** as metrics — packaged as a Helm chart that ships ready-made **alert rules**
and a **Grafana dashboard**, so "a token silently expired and CI/ESO/renovate broke"
stops being a way you discover token expiry.

## What it does

Given one or more GitLab group paths, the exporter walks each group, its
subgroups and all their projects, lists every access token that has an expiry
date, and serves:

```text
gitlab_token_days_remaining{name="renovate", type="project", project="my-org/app",
  active="true", revoked="false", scopes="read_api", expires_at="2026-09-01", ...}  13
gitlab_tokens_exporter_scan_errors 0
gitlab_tokens_exporter_last_scan_timestamp 1755550000
```

The bundled `PrometheusRule` alerts on:

| Alert | Meaning |
|---|---|
| `GitLabTokenExpiringSoon` | an active token has fewer than `expiringSoonDays` days left |
| `GitLabTokenExpired` | a token expired and no active token with the same name replaced it |
| `GitLabTokensExporterScanErrors` | the last scan was partial (the previous complete result keeps being served) |
| `GitLabTokensExporterStale` | no fully successful scan for `staleAfterSeconds` |
| `GitLabTokensExporterAbsent` | the metric vanished entirely — expiry is unmonitored |

Design notes worth knowing:

- **A partial scan never erases data.** On scan errors the exporter keeps serving
  the last complete result and does not advance `last_scan_timestamp` — so firing
  alerts don't silently resolve, and the `Stale` alert catches the condition.
- GitLab flips `active=false` on the expiry date, which is why `ExpiringSoon` and
  `Expired` are two rules: the expired rule only fires when no same-named active
  replacement exists.
- The exporter is ~200 lines of stdlib-only Python. No dependencies to update.

## Install

The chart is released as an OCI package:

```sh
helm install tokens oci://ghcr.io/xcloud-eu/charts/gitlab-token-expiry-exporter \
  --set gitlab.url=https://gitlab.example.com \
  --set 'gitlab.groups={my-org}' \
  --set gitlab.existingSecret=my-gitlab-token-secret
```

## Dashboard

![GitLab token expiry dashboard](docs/img/dashboard.png)

### The token

Create a **group access token** (or use a PAT of an owner) with the `read_api`
scope and the Owner role on each group listed in `gitlab.groups` — listing
access tokens requires owner. The token's reach also scopes the scan: a group
token only sees its own group tree.

Provide it either as an existing `Secret` (recommended — works with
external-secrets, sealed-secrets, vault-injector, anything that produces a
Secret):

```yaml
gitlab:
  existingSecret: my-gitlab-token-secret
  existingSecretKey: GITLAB_READ_TOKEN
```

or, for a quick start only, inline as `gitlab.token`.

An example ExternalSecret pulling the token from a GitLab CI/CD variable is in
[examples/externalsecret.yaml](examples/externalsecret.yaml).

### Wiring into kube-prometheus-stack

The ServiceMonitor and PrometheusRule need labels matching your Prometheus
selectors:

```yaml
serviceMonitor:
  additionalLabels:
    release: kube-prometheus-stack
prometheusRule:
  additionalLabels:
    release: kube-prometheus-stack
```

The Grafana dashboard ships as a ConfigMap labelled for the grafana sidecar
(`dashboard.enabled`, on by default).

## Values

See [values.yaml](charts/gitlab-token-expiry-exporter/values.yaml) — every
knob is documented inline. The notable ones:

| Value | Default | |
|---|---|---|
| `gitlab.url` | `https://gitlab.com` | your GitLab instance |
| `gitlab.groups` | `[]` (required) | group paths to scan, subgroups included |
| `refreshHours` | `4` | scan interval |
| `prometheusRule.expiringSoonDays` | `14` | warning threshold |
| `prometheusRule.alertLabels` | `severity: warning` | labels stamped on every alert |
| `dashboard.folderAnnotation` / `folder` | unset | place the dashboard in a sidecar folder |

## Scope

Group and project access tokens only. Personal access tokens are not scanned —
listing those instance-wide requires an admin token, which is a much bigger
credential than this needs. If you want PAT coverage, look at
[cnieg/gitlab-tokens-exporter](https://github.com/cnieg/gitlab-tokens-exporter),
whose subgroup-walking approach also informed this exporter.

## License

Apache-2.0 - Copyright 2026 [x-ion GmbH](https://www.x-ion.de/)
