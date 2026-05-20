package mitigation

import (
	"context"
	"fmt"
	"sync"
	"time"

	"github.com/go-logr/logr"
	corev1 "k8s.io/api/core/v1"
	networkingv1 "k8s.io/api/networking/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/util/intstr"
	"k8s.io/client-go/kubernetes"
)

type Action struct {
	Stage     string
	Rule      string
	PodName   string
	Namespace string
	Hostname  string
	Timestamp time.Time
}

type Result struct {
	Action    Action
	Success   bool
	Actions   []string
	Error     error
	Duration  time.Duration
}

type Engine struct {
	log       logr.Logger
	clientset kubernetes.Interface
	mu        sync.Mutex
	history   []Result
}

func NewEngine(log logr.Logger, clientset kubernetes.Interface) *Engine {
	return &Engine{
		log:       log,
		clientset: clientset,
		history:   make([]Result, 0),
	}
}

func (e *Engine) Execute(action Action) {
	start := time.Now()
	ctx := context.Background()

	e.log.Info("executing mitigation",
		"stage", action.Stage,
		"pod", action.PodName,
		"namespace", action.Namespace,
	)

	result := Result{Action: action, Success: true}

	switch action.Stage {
	case "S1", "S2":
		if err := e.isolateNetwork(ctx, action); err != nil {
			e.log.Error(err, "network isolation failed", "pod", action.PodName)
			result.Success = false
			result.Error = err
		} else {
			result.Actions = append(result.Actions, "NetworkPolicy:egress-deny")
		}

		if err := e.deletePod(ctx, action); err != nil {
			e.log.Error(err, "pod deletion failed", "pod", action.PodName)
			result.Success = false
			result.Error = err
		} else {
			result.Actions = append(result.Actions, "Pod:delete")
		}

	case "S3":
		result.Actions = append(result.Actions, "Alert:rbac-escalation")
		e.log.Info("RBAC escalation detected — alert only (manual review required)",
			"pod", action.PodName,
			"namespace", action.Namespace,
		)

	case "S4":
		if err := e.deletePod(ctx, action); err != nil {
			e.log.Error(err, "pod deletion failed", "pod", action.PodName)
			result.Success = false
			result.Error = err
		} else {
			result.Actions = append(result.Actions, "Pod:delete")
		}

	default:
		e.log.Info("unknown stage, no action taken", "stage", action.Stage)
	}

	result.Duration = time.Since(start)
	e.recordResult(result)

	e.log.Info("mitigation complete",
		"stage", action.Stage,
		"pod", action.PodName,
		"success", result.Success,
		"actions", result.Actions,
		"duration", result.Duration,
	)
}

func (e *Engine) deletePod(ctx context.Context, action Action) error {
	gracePeriod := int64(0)
	return e.clientset.CoreV1().Pods(action.Namespace).Delete(ctx, action.PodName, metav1.DeleteOptions{
		GracePeriodSeconds: &gracePeriod,
	})
}

func (e *Engine) isolateNetwork(ctx context.Context, action Action) error {
	pod, err := e.clientset.CoreV1().Pods(action.Namespace).Get(ctx, action.PodName, metav1.GetOptions{})
	if err != nil {
		return fmt.Errorf("get pod for labels: %w", err)
	}

	policyName := fmt.Sprintf("kubeshield-isolate-%s", action.PodName)
	protocol := corev1.ProtocolTCP
	dnsPort := intstr.FromInt32(53)

	policy := &networkingv1.NetworkPolicy{
		ObjectMeta: metav1.ObjectMeta{
			Name:      policyName,
			Namespace: action.Namespace,
			Labels: map[string]string{
				"app.kubernetes.io/managed-by": "kubeshield",
				"kubeshield.io/stage":          action.Stage,
			},
		},
		Spec: networkingv1.NetworkPolicySpec{
			PodSelector: metav1.LabelSelector{
				MatchLabels: pod.Labels,
			},
			PolicyTypes: []networkingv1.PolicyType{
				networkingv1.PolicyTypeEgress,
			},
			Egress: []networkingv1.NetworkPolicyEgressRule{
				{
					Ports: []networkingv1.NetworkPolicyPort{
						{Protocol: &protocol, Port: &dnsPort},
					},
				},
			},
		},
	}

	_, err = e.clientset.NetworkingV1().NetworkPolicies(action.Namespace).Create(ctx, policy, metav1.CreateOptions{})
	if err != nil {
		return fmt.Errorf("create network policy: %w", err)
	}

	return nil
}

func (e *Engine) recordResult(r Result) {
	e.mu.Lock()
	defer e.mu.Unlock()
	e.history = append(e.history, r)
}

func (e *Engine) History() []Result {
	e.mu.Lock()
	defer e.mu.Unlock()
	copied := make([]Result, len(e.history))
	copy(copied, e.history)
	return copied
}
