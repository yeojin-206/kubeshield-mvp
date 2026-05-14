#!/bin/bash
set -e

LOG_DIR="logs"
mkdir -p "$LOG_DIR"

echo "=== [1/4] kind 클러스터 생성 ==="
if kind get clusters 2>/dev/null | grep -q kubeshield; then
  echo "클러스터 'kubeshield' 이미 존재. 스킵."
else
  kind create cluster --name kubeshield --config kind-cluster.yaml 2>&1 | tee "$LOG_DIR/01-kind-cluster-create.log"
fi

echo ""
echo "=== [2/4] 클러스터 노드 확인 ==="
kubectl get nodes -o wide 2>&1 | tee "$LOG_DIR/02-nodes.log"

echo ""
echo "=== [3/4] attack-lab namespace + S1 hostPath escape Pod 배포 ==="
kubectl apply -f manifests/vulnerable-pod.yaml 2>&1 | tee "$LOG_DIR/03-vulnerable-pod.log"

echo ""
echo "=== [4/4] 취약 RBAC 설정 ==="
kubectl apply -f manifests/weak-rbac.yaml 2>&1 | tee "$LOG_DIR/04-rbac-setup.log"

echo ""
echo "=== 셋업 완료 ==="
echo "Pod 상태 확인: kubectl get pods -n attack-lab"
echo "공격 테스트: kubectl exec -n attack-lab hostpath-escape -- cat /host/etc/shadow"
