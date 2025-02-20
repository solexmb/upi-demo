# Kubernetes Deployment for Microservices with APISIX, Dapr, Kafka, KEDA, OPA, and YugabyteDB

This repository contains the Kubernetes deployment for a microservices-based architecture using:
- **APISIX** (API Gateway)
- **Dapr** (Service-to-Service Invocation & Pub/Sub)
- **Kafka** (Message Broker)
- **KEDA** (Autoscaling)
- **OPA (Gatekeeper)** (Policy Enforcement)
- **YugabyteDB** (Distributed SQL Database)

---

## Task 1 architectural diagram
```text
+-----------------+         +-----------------+
|   Client        |         |   APISIX        |
| (External User) | ------> | (API Gateway)   |
+-----------------+         +--------+--------+
                                     |
                                     | Routes traffic
                                     v
+-------------------------------+-------------------------------+
|                               |                               |
|  +----------------------+     |     +----------------------+  |
|  |   Service-1          |     |     |   Service-2          |  |
|  | (Flask + Dapr)       |     |     | (Flask + Dapr)       |  |
|  +-----------+-----------+     |     +-----------+-----------+  |
|              |                 |                 |              |
|              | Direct Call     |                 |              |
|              | (Blocked by OPA)|                 |              |
|              v                 |                 |              |
|  +-----------+-----------+     |                 |              |
|  |       OPA             |     |                 |              |
|  | (Time-based Policies) |     |                 |              |
|  +-----------+-----------+     |                 |              |
|              |                 |                 |              |
|              | Allow/Deny      |                 |              |
|              v                 v                 v              |
|  +----------------------+     |     +----------------------+  |
|  |      Kafka           |     |     |   YugabyteDB         |  |
|  | (Message Broker)     +<----+---->| (Distributed SQL DB) |  |
|  +----------------------+     |     +----------------------+  |
|                               |                               |
+-------------------------------+-------------------------------+
```

## Task 2 architectural diagram

```text
+-----------------+         +-----------------+
|   Client        |         |   APISIX        |
| (External User) | ------> | (API Gateway)   |
+-----------------+         +--------+--------+
                                     |
                                     | Routes traffic
                                     v
+-------------------------------+-------------------------------+
|                               |                               |
|  +----------------------+     |     +----------------------+  |
|  |   Service-1          |     |     |   Service-2          |  |
|  | (Flask)              |     |     | (Flask)              |  |
|  +-----------+-----------+     |     +-----------+-----------+  |
|              |                 |                 |              |
|              | Direct Call     |                 |              |
|              | (Blocked by OPA)|                 |              |
|              v                 |                 |              |
|  +-----------+-----------+     |                 |              |
|  |       OPA             |     |                 |              |
|  | (Time-based Policies) |     |                 |              |
|  +-----------+-----------+     |                 |              |
|              |                 |                 |              |
|              | Allow/Deny      |                 |              |
|              v                 v                 v              |
|  +----------------------+     |     +----------------------+  |
|  |      KEDA            |     |     |   YugabyteDB         |  |
|  | (Autoscaler)         +     |     | (Distributed SQL DB) |  |
|  +----------------------+     |     +----------------------+  |
|                               |                               |
+-------------------------------+-------------------------------+
``` 



---

## 🚀 Helm Installation of Components

The following Helm commands install each required component. The **values.yaml** files are located in their respective directories.

### 🟢 APISIX (API Gateway)
```sh
helm repo add apisix https://charts.apiseven.com
helm repo update 
kubectl create ns apisix-2
helm upgrade --install apisix apisix/apisix -n apisix-2 -f apisix/values.yml
```


### DAPR (Pub/Sub)
```sh
helm repo add dapr https://dapr.github.io/helm-charts/
helm repo update 
kubectl create ns dapr-system
helm install dapr dapr/dapr --namespace dapr-system -f dapr/values.yml
```

### KAFKA (Message Broker)
```sh
helm repo add bitnami https://charts.bitnami.com/bitnami 
helm repo update 
kubectl create ns kafka
helm upgrade --install kafka bitnami/kafka -f kafka/values.yml -n kafka
```

### KEDA (Autoscaler)
```sh
helm repo add kedacore https://kedacore.github.io/charts
helm repo update
helm install keda kedacore/keda --namespace keda --create-namespace -f keda/values.yml
```

### OPA (Gatekeeper for Policy Enforcement)
```sh
helm repo add gatekeeper https://open-policy-agent.github.io/gatekeeper/charts
helm repo update
helm upgrade --install gatekeeper gatekeeper/gatekeeper --namespace opa --create-namespace -f opa/values.yml
```
