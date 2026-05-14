# KubeShield-MVP

K8s Kill Chain 분산 자동 차단 플랫폼

## 구조

```
kubeshield-mvp/
├── attacker/         # 공격 시뮬레이터 (Python)
├── controller/       # Mitigation 컨트롤러 (Go)
├── manifests/        # K8s YAML 매니페스트
├── falco-rules/      # Falco 커스텀 룰
├── dashboards/       # Grafana 대시보드 JSON
├── docs/             # 보고서, 다이어그램
├── logs/             # 실행 로그
├── kind-cluster.yaml # kind 클러스터 설정
└── setup.sh          # 환경 셋업 스크립트
```

## 빠른 시작

```bash
./setup.sh
```

## 공격 시나리오

- S1: hostPath escape (Container Escape)
- S2: ServiceAccount 토큰 탈취 (Privilege Escalation)
- S3: RBAC 권한 상승 (Privilege Escalation)
- S4: Static Pod 지속성 (Persistence)
