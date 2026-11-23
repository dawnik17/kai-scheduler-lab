"""
python3 utils.py   # asks for the request ID and node, updates the YAMLs in that node's folder and prints the folder
"""

import json
import re
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def kubectl(*args, stdin=None):
    return subprocess.run(
        ["kubectl", *args], input=stdin, capture_output=True, text=True, check=True
    ).stdout


def gpu_folder(node, namespace):
    """k8s/dra if KAI places a pod that claims a GPU through DRA on the node, else k8s/device-plugin.

    Node labels look the same either way, so a short-lived pause pod is the only way to tell.
    """
    claim = {"name": "gpu", "resourceClaimTemplateName": "gpu-probe"}
    probe = json.dumps(
        {
            "apiVersion": "v1",
            "kind": "List",
            "items": [
                {
                    "apiVersion": "resource.k8s.io/v1",
                    "kind": "ResourceClaimTemplate",
                    "metadata": {"name": "gpu-probe"},
                    "spec": {
                        "spec": {
                            "devices": {
                                "requests": [
                                    {
                                        "name": "gpu",
                                        "exactly": {
                                            "deviceClassName": "gpu.nvidia.com"
                                        },
                                    }
                                ]
                            }
                        }
                    },
                },
                {
                    "apiVersion": "v1",
                    "kind": "Pod",
                    "metadata": {
                        "name": "gpu-probe",
                        "labels": {"kai.scheduler/queue": "poc1"},
                    },
                    "spec": {
                        "schedulerName": "kai-scheduler",
                        "nodeSelector": {"kubernetes.io/hostname": node},
                        "resourceClaims": [claim],
                        "containers": [
                            {
                                "name": "pause",
                                "image": "registry.k8s.io/pause:3.10",
                                "resources": {"claims": [{"name": "gpu"}]},
                            }
                        ],
                    },
                },
            ],
        }
    )
    kubectl("create", "-n", namespace, "-f", "-", stdin=probe)
    try:
        for _ in range(15):
            if kubectl(
                "get",
                "pod",
                "gpu-probe",
                "-n",
                namespace,
                "-o",
                "jsonpath={.spec.nodeName}",
            ):
                return "k8s/dra"
            time.sleep(1)
        return "k8s/device-plugin"
    finally:
        kubectl("delete", "-n", namespace, "-f", "-", "--wait=false", stdin=probe)


def update_yamls(request_id, node):
    """Point every YAML in the node's folder at req-<request_id>'s PVC and the node."""
    namespace = f"req-{request_id}"
    folder = gpu_folder(node, namespace)
    for path in (ROOT / folder).rglob("*.yaml"):
        text = re.sub(
            r"req-\d+-(\w+)-sadata-pvc", rf"{namespace}-\1-sadata-pvc", path.read_text()
        )
        text = re.sub(r"(kubernetes\.io/hostname: )\S+", rf"\g<1>{node}", text)
        path.write_text(text)
    return folder


if __name__ == "__main__":
    print(update_yamls(input("Request ID: "), input("Node: ")))
