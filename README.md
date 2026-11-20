# KAI Scheduler Recipes

## Setup (once)

```bash
kubectl config set-context --current --namespace=req-688
rm -rf train/ckpts  # start clean whenever the GPU count or batch size changes
```

Clean up each POC before starting the other, since both create a `train` Job and an `infer-burst` Deployment.

## Recipe 1: preemption inside one queue

* `train` runs on 4 GPUs at priority `train` (50).
* `infer-burst` starts a Deployment of 1-GPU vLLM servers at priority `inference` (non-preemptible).
* Scaling `infer-burst` to 4 replicas keeps the node fully occupied.
* Scaling `infer-burst` further from 4 to 8 replicas makes KAI evict `train`.
* Scaling back to 4 frees its GPUs, and `train` resumes from its last checkpoint.
* `kubectl scale` stands in for an autoscaler.

```bash
kubectl apply -f k8s/preemption/queues.yaml         # admin
kubectl get pods -w                                 # keep this open in a second terminal
kubectl apply -f k8s/preemption/train.yaml          # train on 4 GPUs
kubectl apply -f k8s/preemption/infer-burst.yaml    # 0 replicas
kubectl scale deployment infer-burst --replicas=4   # inference on the other 4 GPUs; node is full
kubectl logs -f -l job-name=train                   # wait for "Saving model checkpoint"
kubectl scale deployment infer-burst --replicas=8   # load spike: train pod is terminated, a new one waits in Pending
kubectl scale deployment infer-burst --replicas=4   # spike over: train resumes on the freed GPUs
kubectl logs -f -l job-name=train | grep -i resuming

# Clean up
kubectl delete -f k8s/preemption/infer-burst.yaml -f k8s/preemption/train.yaml
rm -rf train/ckpts  # POC 2 trains on 2 GPUs, so it can't resume this checkpoint
```

## Recipe 2: guaranteed GPUs and a shared surplus

* `poc2` owns the node's 8 GPUs. `poc2-batch` and `poc2-infer` are each guaranteed 2; the other 4 are surplus.
* `train` runs on 2 GPUs, both from `poc2-batch`'s guaranteed quota.
* `infer` starts 2 vLLM servers on `poc2-infer`'s 2 guaranteed GPUs, at priority `inference` (non-preemptible).
* `infer-burst` starts with 0 replicas and scales to 6 more inference pods on the surplus, at priority `build-preemptible` (75). KAI only lets preemptible workloads go over quota.
* KAI gives all 4 surplus GPUs to `infer-burst`. The last 2 pods stay `Pending`, because `train`'s 2 GPUs are within its guaranteed quota and can't be reclaimed.
* All 8 GPUs are in use, and `train` keeps its GPUs throughout.

```bash
kubectl apply -f k8s/queues-surplus/queues.yaml        # admin
kubectl get pods -o wide -w                            # keep this open in a second terminal
kubectl apply -f k8s/queues-surplus/train.yaml         # train on its 2 guaranteed GPUs
kubectl apply -f k8s/queues-surplus/infer.yaml         # infer gets 2 GPUs; train keeps running
kubectl apply -f k8s/queues-surplus/infer-burst.yaml   # 0 replicas
kubectl scale deployment infer-burst --replicas=6      # 4 start, 2 stay Pending; train keeps running
kubectl logs -f deployment/infer                       # vLLM server logs from one of the 2 replicas

# Clean up
kubectl delete -f k8s/queues-surplus/infer-burst.yaml -f k8s/queues-surplus/infer.yaml -f k8s/queues-surplus/train.yaml
rm -rf train/ckpts  # POC 1 trains on 4 GPUs, so it can't resume this checkpoint
```
