Connect to DB
kubectl exec -it yb-tserver-0 -n yugabyte -- /bin/bash

ysqlsh -h yb-tserver-service.yugabyte.svc.cluster.local -U yugabyte

\c yugabyte;
\dt

SELECT * FROM processed_data;