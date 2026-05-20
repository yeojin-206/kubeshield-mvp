# KubeShield-MVP

K8s Kill Chain 분산 자동 차단 플랫폼

## 구조

```
kubeshield-mvp/
├── attacker/           # 공격 시뮬레이터 (Python)
│   └── run_attacks.py  # S1~S4 자동 공격 스크립트
├── controller/         # Mitigation 컨트롤러 (Go + Kubebuilder)
│   └── internal/
│       ├── webhook/    # Falco webhook 수신 핸들러
│       └── mitigation/ # 자동 차단 엔진 (Pod 삭제, NetworkPolicy)
├── manifests/          # K8s YAML 매니페스트
│   ├── vulnerable-pod.yaml    # S1 hostPath escape Pod
│   ├── weak-rbac.yaml         # 취약 RBAC 설정
│   ├── sa-token-pod.yaml      # S2 SA 토큰 탈취 Pod
│   └── controller-deploy.yaml # 컨트롤러 배포
├── falco-rules/        # Falco 커스텀 탐지 룰
├── falco-values.yaml   # Falco Helm values
├── dashboards/         # Grafana 대시보드 JSON
├── docs/               # 보고서, 다이어그램
├── logs/               # 실행 로그
├── kind-cluster.yaml   # kind 클러스터 설정 (1 master + 3 workers)
└── setup.sh            # 환경 셋업 스크립트
```

## 빠른 시작

```bash
# 1. 클러스터 + 취약 환경 셋업
./setup.sh

# 2. Falco DaemonSet 배포
helm install falco falcosecurity/falco -n falco -f falco-values.yaml

# 3. 컨트롤러 배포
kubectl apply -f manifests/controller-deploy.yaml

# 4. 공격 시뮬레이션
python3 attacker/run_attacks.py

# 5. 정리
python3 attacker/run_attacks.py --cleanup
```

## 아키텍처

```
[Attack Pod] → syscall → [Falco DaemonSet] → HTTP POST → [KubeShield Controller]
                              (eBPF 탐지)                    ↓
                                                    [Mitigation Engine]
                                                    ├── Pod 삭제
                                                    └── NetworkPolicy 차단
```

## 공격 시나리오

| Stage | 공격 | Kill Chain 단계 | 자동 차단 |
|-------|------|----------------|----------|
| S1 | hostPath escape | Container Escape | Pod 삭제 + 네트워크 격리 |
| S2 | SA 토큰 탈취 | Privilege Escalation | Pod 삭제 + 네트워크 격리 |
| S3 | RBAC 권한 상승 (bind) | Privilege Escalation | Alert (수동 검토) |
| S4 | Static Pod 삽입 | Persistence | Pod 삭제 |

## E2E 검증 결과

- S2 공격: Falco 탐지 → 컨트롤러 자동 차단 (NetworkPolicy + Pod 삭제) — **28ms**
