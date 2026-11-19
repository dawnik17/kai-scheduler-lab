# KAI Scheduler Queue POC

`k8s/` uses default-queue, a work around missing queue permissions. 
`k8s/queues/` shows the standard way, with queues that a cluster admin creates.

## Setup (once)

```bash
kubectl config set-context --current --namespace=req-688
rm -rf train/ckpts  # start clean whenever the GPU count or batch size changes
```

Clean up the `k8s/` POCs, and each queue POC before starting the other, since they share the names `train` and `infer`.

## POC 1: preemption inside one queue

* `poc1` is capped at 1 GPU, so `train` and `infer` compete for it inside one queue.
* `train` runs on 1 GPU at priority `train` (50).
* `infer` is a 1-GPU vLLM Job at priority `inference` (non-preemptible). KAI allows it because it fits within the queue's quota.
* `infer` makes KAI evict `train`. The moment `infer` is complete, `train` resumes from its last checkpoint.

```bash
kubectl apply -f k8s/queues/poc1-preemption/queues.yaml   # admin
kubectl get pods -w                                       # keep this open in a second terminal
kubectl apply -f k8s/queues/poc1-preemption/train.yaml
kubectl logs -f -l job-name=train                         # wait for "Saving model checkpoint"
kubectl apply -f k8s/queues/poc1-preemption/infer.yaml    # train pod is terminated, a new one waits in Pending
kubectl logs -f job/infer                                 # prompts and replies; then infer Completes
kubectl logs -f -l job-name=train | grep -i resuming

# Clean up
kubectl delete -f k8s/queues/poc1-preemption/infer.yaml -f k8s/queues/poc1-preemption/train.yaml
```

## POC 2: guaranteed GPUs and a shared surplus

* `poc2` owns the node's 8 GPUs. `poc2-train` and `poc2-infer` are each guaranteed 1; the other 6 are surplus.
* `train` runs on its 1 guaranteed GPU and is limited to it.
* `infer` runs on inference's guaranteed GPU at priority `inference` (non-preemptible).
* `infer-burst` is 6 more 1-GPU inference pods on the surplus, at priority `build-preemptible` (75). KAI only lets preemptible workloads go over quota.
* All 8 pods run at once, and `train` keeps its GPU throughout.

```bash
kubectl apply -f k8s/queues/poc2-queues-surplus/queues.yaml   # admin
kubectl get pods -o wide -w                                   # keep this open in a second terminal
kubectl apply -f k8s/queues/poc2-queues-surplus/train.yaml    # train on its guaranteed GPU
kubectl apply -f k8s/queues/poc2-queues-surplus/infer.yaml    # infer and 6 infer-burst pods; train keeps running
kubectl logs -f job/infer                                     # prompts and replies; then the inference Jobs Complete

# Clean up
kubectl delete -f k8s/queues/poc2-queues-surplus/infer.yaml -f k8s/queues/poc2-queues-surplus/train.yaml
```
