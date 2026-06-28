{{- define "zavashop.name" -}}
orchestrator
{{- end -}}

{{- define "zavashop.labels" -}}
app.kubernetes.io/name: {{ include "zavashop.name" . }}
app.kubernetes.io/part-of: zavashop
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version | replace "+" "_" }}
{{- end -}}
