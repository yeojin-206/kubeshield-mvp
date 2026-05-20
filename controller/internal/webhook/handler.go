package webhook

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/go-logr/logr"
	"github.com/kubeshield-mvp/controller/internal/mitigation"
)

type FalcoEvent struct {
	Output       string                 `json:"output"`
	Priority     string                 `json:"priority"`
	Rule         string                 `json:"rule"`
	Time         string                 `json:"time"`
	Hostname     string                 `json:"hostname"`
	Source       string                 `json:"source"`
	Tags         []string               `json:"tags"`
	OutputFields map[string]interface{} `json:"output_fields"`
}

type Handler struct {
	log       logr.Logger
	mitigator *mitigation.Engine
}

func NewHandler(log logr.Logger, mitigator *mitigation.Engine) *Handler {
	return &Handler{log: log, mitigator: mitigator}
}

func (h *Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	body, err := io.ReadAll(r.Body)
	if err != nil {
		h.log.Error(err, "failed to read request body")
		http.Error(w, "bad request", http.StatusBadRequest)
		return
	}
	defer r.Body.Close()

	var event FalcoEvent
	if err := json.Unmarshal(body, &event); err != nil {
		h.log.Error(err, "failed to parse Falco event")
		http.Error(w, "bad request", http.StatusBadRequest)
		return
	}

	if !strings.HasPrefix(event.Rule, "KubeShield") {
		w.WriteHeader(http.StatusOK)
		return
	}

	h.log.Info("Falco alert received",
		"rule", event.Rule,
		"priority", event.Priority,
		"hostname", event.Hostname,
	)

	stage := extractStage(event.Rule)
	podName := stringField(event.OutputFields, "k8s.pod.name")
	namespace := stringField(event.OutputFields, "k8s.ns.name")

	if podName == "" || namespace == "" {
		h.log.Info("skipping event: missing pod/namespace info", "rule", event.Rule)
		w.WriteHeader(http.StatusOK)
		return
	}

	action := mitigation.Action{
		Stage:     stage,
		Rule:      event.Rule,
		PodName:   podName,
		Namespace: namespace,
		Hostname:  event.Hostname,
		Timestamp: time.Now(),
	}

	go h.mitigator.Execute(action)

	w.WriteHeader(http.StatusOK)
	fmt.Fprintf(w, `{"status":"accepted","stage":"%s"}`, stage)
}

func extractStage(rule string) string {
	if strings.Contains(rule, "S1") {
		return "S1"
	}
	if strings.Contains(rule, "S2") {
		return "S2"
	}
	if strings.Contains(rule, "S3") {
		return "S3"
	}
	if strings.Contains(rule, "S4") {
		return "S4"
	}
	return "UNKNOWN"
}

func stringField(fields map[string]interface{}, key string) string {
	v, ok := fields[key]
	if !ok || v == nil {
		return ""
	}
	s, ok := v.(string)
	if !ok {
		return ""
	}
	return s
}
