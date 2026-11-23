# Dynamo Snapshot Setup

One-time setup for [Recipe 3](../README.md#recipe-3-fast-scaling-w-dynamo-snapshot).

**Build the placeholder image (once).** Dynamo's vLLM runtime plus the CRIU and cuda-checkpoint tools that restores need.

```bash
# https://github.com/ai-dynamo/dynamo/blob/v1.2.1/deploy/snapshot/Makefile
git clone --depth 1 --branch v1.2.1 --filter=blob:none --sparse https://github.com/ai-dynamo/dynamo.git /tmp/dynamo-v1.2.1
git -C /tmp/dynamo-v1.2.1 sparse-checkout set deploy/snapshot
# --network host: Docker's build network can't reach archive.ubuntu.com from this host
make -C /tmp/dynamo-v1.2.1/deploy/snapshot docker-build-placeholder \
  PLACEHOLDER_BASE_IMG=nvcr.io/nvidia/ai-dynamo/vllm-runtime:1.2.1 \
  PLACEHOLDER_IMG=ghcr.io/dawnik17/dynamo-vllm-placeholder:1.2.1 \
  CRIU_BUILD_ARGS="--network host"
docker push ghcr.io/dawnik17/dynamo-vllm-placeholder:1.2.1   # then make the package public on GitHub
```

**Create the checkpoint (once per node and request).** Restores only find checkpoints in their own namespace, taken on the same kind of node.

```bash
kubectl apply -f k8s/dra/snapshot/checkpoint.yaml   
kubectl wait dckpt/gemma3-4b --for=jsonpath='{.status.phase}'=Ready --timeout=30m
```
