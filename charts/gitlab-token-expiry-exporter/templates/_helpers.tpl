{{- define "gte.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "gte.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "gte.labels" -}}
{{- $chart := printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" -}}
helm.sh/chart: {{ $chart | trunc 63 | trimSuffix "-" }}
app.kubernetes.io/name: {{ include "gte.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "gte.selectorLabels" -}}
app.kubernetes.io/name: {{ include "gte.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "gte.secretName" -}}
{{- if .Values.gitlab.existingSecret -}}
{{- .Values.gitlab.existingSecret -}}
{{- else -}}
{{- include "gte.fullname" . -}}
{{- end -}}
{{- end -}}

{{- define "gte.secretKey" -}}
{{- if .Values.gitlab.existingSecret -}}
{{- .Values.gitlab.existingSecretKey -}}
{{- else -}}
GITLAB_READ_TOKEN
{{- end -}}
{{- end -}}
