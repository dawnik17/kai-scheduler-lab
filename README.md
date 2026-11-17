# KAI Scheduler Preemption POC

## Setup (once)

```bash
kubectl config set-context --current --namespace=req-688
rm -rf train/ckpts  # start clean whenever the GPU count or batch size changes
```

## POC 1

* `train` runs on 8 GPUs at priority `train` (50). 
* `infer` is a Deployment of 1-GPU vLLM servers at priority `build-preemptible` (75).
* `infer` pod deployment makes KAI evict `train`. 
* The moment `infer` is complete, `train` resumes from its last checkpoint.

```bash
kubectl apply -f k8s/train.yaml
kubectl get pods -w                             # keep this open in a second terminal
kubectl logs -f -l job-name=train               # wait for "Saving model checkpoint"
kubectl apply -f k8s/infer.yaml                 # train pod is terminated, a new one waits in Pending
kubectl logs -f job/infer                       # prompts and replies; then infer Completes
kubectl logs -f -l job-name=train | grep -i resuming

# Clean up
kubectl delete -f k8s/infer.yaml -f k8s/train.yaml
```

## POC 2

* `train` runs on 4 GPUs at priority `train` (50). 
* `infer-burst` is a Deployment of 1-GPU vLLM servers at priority `build-preemptible` (75).
* Scaling `infer-burst` from 4 to 8 replicas makes KAI evict `train`. Scaling back to 4 frees its GPUs, and `train` resumes from its last checkpoint.
* `kubectl scale` stands in for an autoscaler.

```bash
kubectl get pods -w                                 # keep this open in a second terminal
kubectl apply -f k8s/train.yaml                     # train on 4 GPUs
kubectl apply -f k8s/infer-burst.yaml               # 0 replicas
kubectl scale deployment infer-burst --replicas=4   # inference on the other 4 GPUs; node is full
kubectl logs -f -l job-name=train                   # wait for "Saving model checkpoint"
kubectl scale deployment infer-burst --replicas=8   # load spike: train pod is terminated, a new one waits in Pending
kubectl scale deployment infer-burst --replicas=4   # spike over: train resumes on the freed GPUs
kubectl logs -f -l job-name=train | grep -i resuming

# Clean up
kubectl delete -f k8s/infer-burst.yaml -f k8s/train.yaml
```
