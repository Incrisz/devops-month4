# Secure Mesh Lab — standard Docker Hub → Kind → Istio workflow

An intentionally small teaching application, not a production store. All payments are simulated and nothing is persisted. Three separate services use Python standard-library HTTP servers (no dependencies), each with its own Dockerfile. Requests travel **browser → frontend → orders → payments**.

## 0. Prerequisites

Linux or WSL2 terminal, Docker daemon running, kubectl, Kind and curl. Install Istio CLI in phase 5. Budget roughly 6–8 GB of free RAM for the 3-node cluster, Calico and Istio (actual requirements vary). Use a personal lab environment.

## 1. Build Docker images and push

Create **three PUBLIC Docker Hub repositories** named `mesh-frontend`, `mesh-orders`, and `mesh-payments` in your account (or configure registry permissions). Sign in first.

```bash
export DOCKERHUB_USER=YOUR_DOCKERHUB_USERNAME
docker login
bash scripts/build-push.sh
```

Manual equivalents (repeat for orders and payments):

```bash
docker build -t "$DOCKERHUB_USER/mesh-frontend:v1" ./frontend
docker push "$DOCKERHUB_USER/mesh-frontend:v1"
```

## 2. Create a Kind cluster with Calico

**Important:** Kind's default CNI does *not* enforce Kubernetes NetworkPolicy. This lab intentionally disables it and installs Calico. Nodes can be `NotReady` until Calico starts.

```bash
kind create cluster --name mesh-lab --config kind-config.yaml
kubectl config use-context kind-mesh-lab
kubectl apply -f https://raw.githubusercontent.com/projectcalico/calico/v3.33.0/manifests/calico.yaml
kubectl wait --for=condition=Ready nodes --all --timeout=300s
kubectl get pods -A
```

This is Calico's documented manifest installation method. For a local cluster Kubernetes version not supported by the selected Calico version, consult https://docs.tigera.io/calico/latest/getting-started/kubernetes/kind . If Calico install reports API/resource errors, stop and fix CNI before proceeding.

## 3. Deploy images from Docker Hub

```bash
bash scripts/deploy.sh
kubectl -n mesh-lab port-forward svc/frontend 8080:8080
```

In browser, visit http://localhost:8080 and click **Place demo order**. Expect HTTP 200 with an approved *simulated* payment. Stop the forward using Ctrl-C. To diagnose issues: `kubectl get pods -n mesh-lab`, `kubectl describe pod -n mesh-lab -l app=orders`, `kubectl logs -n mesh-lab deployment/orders`.

If `ImagePullBackOff`, confirm the Docker Hub repos exist and are public, credentials were able to push, and the image tags match your username. No registry secret is necessary for public images.

### Access from another computer

The frontend Service exposes NodePort `30400`. `kind-config.yaml` maps that port to all interfaces on the host. Before enabling Istio strict mTLS in phase 5, visit `http://SERVER_PUBLIC_IP:30400/` (for this server, `http://13.222.205.50:30400/`). On EC2, allow inbound TCP `30400` in the instance security group from your client public IP (`/32`), and allow the same traffic through any host firewall.

Kind port mappings are applied only when the cluster is created. If your existing cluster was created with `listenAddress: "127.0.0.1"`, editing the file does not update it. To access that cluster immediately, run this **on the server** and leave it running:

```bash
kubectl -n mesh-lab port-forward --address 0.0.0.0 svc/frontend 30401:8080
```

Allow inbound TCP `30401` from your client public IP, then visit `http://13.222.205.50:30401/`. A separate port avoids conflicting with the existing Docker mapping on `30400`. This temporary forward also works after phase 5 enables strict mTLS; ordinary browser HTTP through NodePort does not satisfy strict mTLS. For permanent mesh ingress, configure an Istio ingress gateway.

To use the updated mapping on `30400`, recreate the disposable lab cluster and repeat phases 2–3. Deleting the cluster removes its workloads and any lab state; do this only when you are ready to rebuild it.

If access still fails, check on the server:

```bash
docker port mesh-lab-control-plane 30400/tcp
kubectl -n mesh-lab get pods,svc
kubectl -n mesh-lab get endpointslices -l kubernetes.io/service-name=frontend
curl -v --connect-timeout 5 http://127.0.0.1:30400/
```

The Docker mapping should show `0.0.0.0:30400`, and the frontend must have a ready pod and a Service endpoint. If local access works but public access fails, check the instance public IP, security group, and host firewall.

## 4. Learn Kubernetes Networking and RBAC

DNS and Service discovery: `orders.mesh-lab.svc.cluster.local` resolves within the cluster. The frontend calls `http://orders:8080`, and orders calls `http://payments:8080`.

Create Role and RoleBinding:

```bash
kubectl apply -f k8s/rbac/
kubectl auth can-i list pods -n mesh-lab --as=system:serviceaccount:mesh-lab:orders-sa   # yes
kubectl auth can-i delete pods -n mesh-lab --as=system:serviceaccount:mesh-lab:orders-sa # no
```

NetworkPolicy **before** testing Istio:

```bash
kubectl apply -f k8s/network-policy/
# Still works (orders is allowed to contact payments):
kubectl -n mesh-lab port-forward svc/frontend 8080:8080
```

Click Place demo order again. For a direct unauthorized network test in another terminal:

```bash
kubectl run outsider -n mesh-lab --image=busybox:1.36 --restart=Never -- sleep 3600
kubectl wait --for=condition=Ready pod/outsider -n mesh-lab --timeout=120s
kubectl exec -n mesh-lab outsider -- wget -T 3 -qO- http://payments:8080/health
```

The outsider request should time out because Calico enforces the NetworkPolicy. If it succeeds, verify Calico is healthy and the network policy exists.

## 5. Add Istio

Install the CLI (Linux/macOS), in a separate temporary directory so your project path stays the same:

```bash
mkdir -p /tmp/mesh-istio && cd /tmp/mesh-istio
curl -L https://istio.io/downloadIstio | sh -
export PATH="$(find "$PWD" -maxdepth 2 -type d -name bin | head -n 1):$PATH"
istioctl version --remote=false
cd -
```

Install Istio and inject proxies into the three deployments:

```bash
istioctl install --set profile=demo -y
kubectl label namespace mesh-lab istio-injection=enabled --overwrite
kubectl rollout restart deployment/frontend deployment/orders deployment/payments -n mesh-lab
kubectl rollout status deployment/frontend -n mesh-lab
kubectl rollout status deployment/orders -n mesh-lab
kubectl rollout status deployment/payments -n mesh-lab
kubectl get pods -n mesh-lab
```

Expected application pod READY column: `2/2` (app + proxy). `outsider` was created before injection and remains unmeshed. Delete it when done with the networking exercise: `kubectl delete pod outsider -n mesh-lab`.

Apply strict mTLS and identity-based authorization:

```bash
kubectl apply -f k8s/istio/
istioctl analyze -n mesh-lab
kubectl -n mesh-lab port-forward svc/frontend 8080:8080
```

Click Place demo order. It should still work because Orders has the authorized service-account identity. You can inspect identities and traffic with `istioctl proxy-config clusters deploy/orders -n mesh-lab` and `kubectl logs -n mesh-lab deploy/orders -c istio-proxy`.

**Important distinction:** NetworkPolicy blocks unapproved IP traffic *before* it reaches Istio. To separately demonstrate an Istio authorization `403`, temporarily remove `payments-accept-orders-only`, create a *meshed* client with a different service account, and make an HTTP call to Payments; then restore the NetworkPolicy. Do not interpret a timeout as proof of Istio authorization.

## 6. Cleanup

```bash
kind delete cluster --name mesh-lab
```

## Notes

- RBAC protects the Kubernetes API; NetworkPolicy protects pod traffic; Istio AuthorizationPolicy controls authenticated service-to-service requests. They are different layers.
- For this demo all images are public and tagged `v1`; production workflows should use immutable digests, CI, scans, registry access controls, resource budgets, monitoring, secrets and separate environments.
- Python standard-library server is deliberately minimal for learning, not a production web server.
# devops-month4
