## Task 1 architectural diagram

+-----------------+         +-----------------+
|    Client       |         |    APISIX       |
| (External User) | ------> | (API Gateway &  |
+-----------------+         |  Load Balancer) |
                            +--------+--------+
                                     |
                                     | Routes traffic
                                     v
+-------------------------------+-------------------------------+
|                               |                               |
|  +----------------------+     |     +----------------------+  |
|  |    Service-1          |     |     |    Service-2          |  |
|  | (Flask + Dapr Sidecar)|     |     | (Flask + Dapr Sidecar)|  |
|  +-----------+-----------+     |     +-----------+-----------+  |
|              |                 |                 |              |
|              | Direct Service  |                 |              |
|              | Invocation      |                 |              |
|              | (Blocked by OPA |                 |              |
|              | during time X)  |                 |              |
|              |                 |                 |              |
|  +-----------v-----------+     |     +-----------v-----------+  |
|  |       Dapr            |     |     |       Dapr            |  |
|  | (Service Invocation   |     |     | (Service Invocation   |  |
|  |  & Pub/Sub)           |     |     |  & Pub/Sub)           |  |
|  +-----------+-----------+     |     +-----------+-----------+  |
|              |                 |                                |
|              | Pub/Sub (Kafka) |                                |
|              v                 v                                |
|  +----------------------+     |     +----------------------+   |
|  |       Kafka           +                   OPA            |  |
|  | (Message Broker)      |     |     | (Time-based Policies)|  |
|  +-----------+-----------+     |     +----------------------+  |
|              |                 |                               |
|              | Data Storage    |                               |
|              v                 |                               |
|  +----------------------+      |                               |
|  |    YugabyteDB        |      |                               |
|  | (Distributed SQL DB) |      |                               |
|  +----------------------+      |                               |
|                                |                               |
|                                |                               |
|                                |                               |
|                                |                               |
|                                |                               |
|  +----------------------+      +-------------------------------+ 



## Task 2 architectural diagram

+-----------------+         +-----------------+
|    Client       |         |    APISIX       |
| (External User) | ------> | (API Gateway &  |
+-----------------+         |  Load Balancer) |
                            +--------+--------+
                                     |
                                     | Routes traffic
                                     v
+-------------------------------+-------------------------------+
|                               |                                |
|  +----------------------+     |     +----------------------+   |
|  |    Service-1          |     |     |    Service-2          | |
|  | (Flask                |     |     | (Flask                | |
|  +-----------+-----------+     |     +-----------+-----------+ |
|              |                 |                 |             |
|              | Direct Service  |                 |             |
|              | Invocation      |                 |             |
|              | (Blocked by OPA |                 |             |
|              | during time X)  |                 |             |
|              |                 |                 |             |
|                                                  |             |
|              |                 |                 |             |
|              | Data Storage    |                 |             |
|              v                 |                 |             |
|  +----------------------+      |                 |             |
|  |    YugabyteDB        |      |<----------------|             |
|  | (Distributed SQL DB) |      |                               |
|  +----------------------+      |                               |
|                                |                               |
|  +----------------------+      |                               |
|  |       KEDA           |      |                               |
|  | (Autoscaling based   |      |                               |
|  |  on Kafka metrics)   |      |                               |
|  +----------------------+      +-------------------------------+ 


## Using helm chart to install all the needed components and the values.yml files are in each folder of the components
### APISIX
helm repo add apisix https://charts.apiseven.com
helm repo update 
kubectl create ns apisix-2
#helm upgrade --install apisix apisix/apisix -n apisix-2 -f apisix/values.yml

### DAPR
helm repo add dapr https://dapr.github.io/helm-charts/
helm repo update 
kubectl create ns dapr-system
helm install dapr dapr/dapr --namespace dapr-system -f dapr/values.yml

### KAFKA
helm repo add bitnami https://charts.bitnami.com/bitnami 
helm repo update 
kubectl create ns kafka
helm upgrade --install kafka bitnami/kafka -f kafka/values.yml -n kafka

### KEDA
helm repo add kedacore https://kedacore.github.io/charts
helm repo update
helm install keda kedacore/keda --namespace keda --create-namespace -f keda/values.yml

### OPA
helm repo add gatekeeper https://open-policy-agent.github.io/gatekeeper/charts
helm repo update
helm upgrade --install gatekeeper gatekeeper/gatekeeper --namespace opa --create-namespace -f opa/values.yml