# Secure Mesh Lab — standard Docker Hub → Kind → Istio workflow

An intentionally small teaching application, not a production store. All payments are simulated and nothing is persisted. Three separate services use Python standard-library HTTP servers (no dependencies), each with its own Dockerfile. Requests travel **browser → frontend → orders → payments**.

## 0. Prerequisites

Linux or WSL2 terminal, Docker daemon running, kubectl, Kind and curl. Install Istio CLI in phase 5. Budget roughly 6–8 GB of free RAM for the 3-node cluster and Istio (actual requirements vary). Use a personal lab environment.

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

## 2. Create a Kind cluster

New clusters use Kind's default networking. No separate Calico installation is needed for this RBAC and Istio lab.

```bash
kind create cluster --name mesh-lab --config kind-config.yaml
kubectl config use-context kind-mesh-lab
kubectl wait --for=condition=Ready nodes --all --timeout=300s
kubectl get pods -A
```

If you already have a working cluster with Calico, keep it; no networking migration or cluster recreation is needed. Remove the previous lab policy and test pod **on your server** so they do not interfere with the Istio exercise:

```bash
kubectl delete networkpolicy payments-accept-orders-only -n mesh-lab --ignore-not-found
kubectl delete pod outsider -n mesh-lab --ignore-not-found
```

If an older cluster has its default CNI disabled but Calico was never installed, it still needs a working CNI before continuing. The updated Kind configuration only applies to newly created clusters.

## 3. Deploy images from Docker Hub

```bash
bash scripts/deploy.sh
```

In your browser, visit **http://13.222.205.50:30400/** and click **Place demo order**. Expect HTTP 200 with an approved *simulated* payment. Use this same URL throughout the lab. To diagnose issues: `kubectl get pods -n mesh-lab`, `kubectl describe pod -n mesh-lab -l app=orders`, `kubectl logs -n mesh-lab deployment/orders`.

If `ImagePullBackOff`, confirm the Docker Hub repos exist and are public, credentials were able to push, and the image tags match your username. No registry secret is necessary for public images.

### Access from another computer

The frontend Service exposes NodePort `30400`. `kind-config.yaml` maps that port to all interfaces on the host. Your browser connects to **http://13.222.205.50:30400/**. Port `8080` is the internal application port; the browser uses `30400`. On EC2, allow inbound TCP `30400` in the instance security group from your client public IP (`/32`), and allow the same traffic through any host firewall.

Kind port mappings are applied only when the cluster is created. If your existing cluster was created with `listenAddress: "127.0.0.1"`, editing the file does not update it. To use the updated mapping on `30400`, recreate the disposable lab cluster and repeat phases 2–3. Deleting the cluster removes its workloads and any lab state; do this only when you are ready to rebuild it. If browser access on `30400` already works, continue with the lab.

If access still fails, check on the server:

```bash
docker port mesh-lab-control-plane 30400/tcp
kubectl -n mesh-lab get pods,svc
kubectl -n mesh-lab get endpointslices -l kubernetes.io/service-name=frontend
curl -v --connect-timeout 5 http://127.0.0.1:30400/
```

The Docker mapping should show `0.0.0.0:30400`, and the frontend must have a ready pod and a Service endpoint. If local access works but public access fails, check the instance public IP, security group, and host firewall.

## 4. Learn Kubernetes RBAC

DNS and Service discovery: `orders.mesh-lab.svc.cluster.local` resolves within the cluster. The frontend calls `http://orders:8080`, and orders calls `http://payments:8080`.

Orders uses `orders-sa` as its service-account identity, including for Istio. The application does not call the Kubernetes API, so it does not require pod-reader permissions. RBAC is a separate Kubernetes API exercise; removing its RoleBinding does not block HTTP calls to payments.

Create Role and RoleBinding and check permissions:

```bash
kubectl apply -f k8s/rbac/
kubectl auth can-i list pods -n mesh-lab --as=system:serviceaccount:mesh-lab:orders-sa   # yes
kubectl auth can-i delete pods -n mesh-lab --as=system:serviceaccount:mesh-lab:orders-sa # no
```

Remove the grant and check again (assuming no other binding grants access):

```bash
kubectl delete rolebinding orders-pod-reader -n mesh-lab
kubectl auth can-i list pods -n mesh-lab --as=system:serviceaccount:mesh-lab:orders-sa   # no
kubectl apply -f k8s/rbac/
```

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

Expected application pod READY column: `2/2` (app + proxy). Orders must use `orders-sa`; the base manifest creates and assigns it. If upgrading an older deployment, run `bash scripts/deploy.sh` before continuing.

Apply strict mTLS and identity-based authorization, with an HTTP exception for the browser-facing frontend:

```bash
kubectl apply -f k8s/istio/
istioctl analyze -n mesh-lab
```

Open **http://13.222.205.50:30400/** and click **Place demo order**. It should still work because Orders has the authorized service-account identity.

`frontend-browser-http.yaml` allows plaintext HTTP only on the frontend workload’s port `8080`, reached through NodePort `30400`. Orders and payments retain strict mTLS. This exception keeps direct browser access working in this lab; browsers cannot supply Istio mesh mTLS. See [Istio PeerAuthentication](https://istio.io/latest/docs/reference/config/security/peer_authentication/) for port-level policy behavior.

You can inspect identities and traffic with `istioctl proxy-config clusters deploy/orders -n mesh-lab` and `kubectl logs -n mesh-lab deploy/orders -c istio-proxy`.

### Browser exercise: deny and allow payments with Istio

Start with the policies above applied. At **http://13.222.205.50:30400/**, click **Place demo order** and confirm HTTP 200.

Temporarily remove all allow rules from the payments authorization policy:

```bash
kubectl patch authorizationpolicy payments-orders-only -n mesh-lab \
  --type=merge -p '{"spec":{"rules":[]}}'
```

After the proxies receive the update, click again. Istio rejects the request to payments with HTTP 403. The current app wraps downstream failures, so **the browser shows HTTP 502**, not the original 403.

To see the actual Istio response from the orders pod:

```bash
kubectl exec -n mesh-lab deploy/orders -c orders -- python -c 'import urllib.request; urllib.request.urlopen("http://payments:8080/health", timeout=5)'
```

Expected while blocked: `HTTP Error 403: Forbidden`. This command runs a diagnostic in the existing container; it does not modify application code.

Restore orders access:

```bash
kubectl apply -f k8s/istio/payments-authorization.yaml
```

Wait briefly for propagation and click **Place demo order** again. Expect HTTP 200. No image rebuilds or pod restarts are needed for these policy changes.

An ALLOW policy with no rules permits no requests, assuming no other matching ALLOW policy grants access. Deleting the policy entirely removes that authorization restriction; it does not block orders. See [Istio AuthorizationPolicy](https://istio.io/latest/docs/reference/config/security/authorization-policy/).

RBAC controls Kubernetes API actions; Istio authorization controls which service identity can call payments. Removing the RBAC RoleBinding will not stop orders, because this app does not use the Kubernetes API. Use the Istio exercise to demonstrate application access being denied and restored.

## 6. Cleanup

```bash
kind delete cluster --name mesh-lab
```

## Notes

- RBAC protects the Kubernetes API; Istio mTLS secures mesh traffic; Istio AuthorizationPolicy controls authenticated service-to-service requests.
- For this demo all images are public and tagged `v1`; production workflows should use immutable digests, CI, scans, registry access controls, resource budgets, monitoring, secrets and separate environments.
- Python standard-library server is deliberately minimal for learning, not a production web server.
# devops-month4
