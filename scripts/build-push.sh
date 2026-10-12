#!/usr/bin/env bash
set -euo pipefail
: "${DOCKERHUB_USER:?Set DOCKERHUB_USER, e.g. export DOCKERHUB_USER=myusername}"
for service in frontend orders payments; do
  docker build -t "${DOCKERHUB_USER}/mesh-${service}:v1" "${service}"
  docker push "${DOCKERHUB_USER}/mesh-${service}:v1"
done
