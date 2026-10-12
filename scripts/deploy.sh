#!/usr/bin/env bash
set -euo pipefail
: "${DOCKERHUB_USER:?Set DOCKERHUB_USER first}"
kubectl config use-context kind-mesh-lab
kubectl apply -f k8s/base/00-namespace.yaml
for service in frontend orders payments; do
  sed "s#DOCKERHUB_USER#${DOCKERHUB_USER}#g" "k8s/base/${service}.yaml" | kubectl apply -f -
done
for service in frontend orders payments; do
  kubectl rollout status "deployment/${service}" -n mesh-lab --timeout=180s
done
kubectl get pods,svc -n mesh-lab
