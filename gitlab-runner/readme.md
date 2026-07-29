# AKS Workload Identity Module

Provisions Azure workload identity federation for AKS so that GitLab CI jobs
can assume a scoped Azure identity per team/pipeline, instead of sharing one
broadly-permissioned identity.

Pattern implemented, per identity:

```
K8s ServiceAccount -> Federated Identity Credential -> User Assigned Managed Identity -> Role Assignment(s)
```

**Scope of this module:** Azure-side resources only (UAMI, federated
credential, role assignments). It does **not** create the Kubernetes
ServiceAccount objects — those are owned by each application team via their
own manifests/Helm/GitOps, using the `client_id` this module outputs.

---

## Module files

### `modules/workload-identity/variables.tf`

```hcl
variable "resource_group_name" {
  type = string
}

variable "location" {
  type = string
}

variable "oidc_issuer_url" {
  description = "OIDC issuer URL of the AKS cluster"
  type        = string
}

variable "workload_identities" {
  description = "One entry per team/pipeline identity"
  type = map(object({
    service_account_name = string
    namespace             = string
    role_assignments = list(object({
      role  = string
      scope = string
    }))
  }))
}
```

### `modules/workload-identity/main.tf`

```hcl
# One User Assigned Managed Identity (UAMI) per logical workload identity
resource "azurerm_user_assigned_identity" "this" {
  for_each            = var.workload_identities
  name                = "aks-${each.key}-identity"
  location            = var.location
  resource_group_name = var.resource_group_name
}

# One federated identity credential per UAMI, tied to its own K8s service account
resource "azurerm_federated_identity_credential" "this" {
  for_each            = var.workload_identities
  name                = "aks-${each.key}-fic"
  resource_group_name = var.resource_group_name
  parent_id           = azurerm_user_assigned_identity.this[each.key].id
  audience            = ["api://AzureADTokenExchange"]
  issuer              = var.oidc_issuer_url
  subject             = "system:serviceaccount:${each.value.namespace}:${each.value.service_account_name}"
}

# Flatten role_assignments so each identity can have multiple roles/scopes
locals {
  role_assignments_flat = merge([
    for id_key, id_val in var.workload_identities : {
      for ra in id_val.role_assignments :
      "${id_key}-${ra.role}-${replace(ra.scope, "/", "-")}" => {
        identity_key = id_key
        role         = ra.role
        scope        = ra.scope
      }
    }
  ]...)
}

resource "azurerm_role_assignment" "this" {
  for_each             = local.role_assignments_flat
  principal_id         = azurerm_user_assigned_identity.this[each.value.identity_key].principal_id
  role_definition_name = each.value.role
  scope                = each.value.scope
}
```

### `modules/workload-identity/outputs.tf`

```hcl
output "client_ids" {
  description = "Client ID of each UAMI, keyed by workload identity name"
  value = {
    for k, v in azurerm_user_assigned_identity.this : k => v.client_id
  }
}

output "principal_ids" {
  description = "Principal (object) ID of each UAMI, keyed by workload identity name"
  value = {
    for k, v in azurerm_user_assigned_identity.this : k => v.principal_id
  }
}

output "identity_ids" {
  description = "Full Azure resource ID of each UAMI, keyed by workload identity name"
  value = {
    for k, v in azurerm_user_assigned_identity.this : k => v.id
  }
}

output "expected_service_accounts" {
  description = "Namespace + service account name each identity expects to be federated with"
  value = {
    for k, v in var.workload_identities : k => {
      namespace       = v.namespace
      service_account = v.service_account_name
    }
  }
}
```

---

## Example root-module call site

Adjust `source` to wherever this module lives relative to your root config.

```hcl
module "workload_identity" {
  source = "./modules/workload-identity"

  resource_group_name = azurerm_resource_group.rg.name
  location             = azurerm_resource_group.rg.location
  oidc_issuer_url        = azurerm_kubernetes_cluster.aks.oidc_issuer_url

  workload_identities = {
    container_apps = {
      service_account_name = "container-app-deployer"
      namespace             = "gitlab-runner"
      role_assignments = [
        {
          role  = "AcrPush"
          scope = azurerm_container_registry.acr.id
        },
        {
          role  = "Contributor"
          scope = azurerm_resource_group.container_apps.id
        },
        {
          role  = "Key Vault Secrets User"
          scope = azurerm_key_vault.kv.id
        },
      ]
    }
    power_platform = {
      service_account_name = "power-platform-deployer"
      namespace             = "gitlab-runner"
      role_assignments = [
        {
          role  = "Reader"
          scope = azurerm_resource_group.dataverse.id
        },
        {
          role  = "Key Vault Secrets User"
          scope = azurerm_key_vault.kv.id
        },
      ]
    }
  }
}

output "workload_identity_client_ids" {
  value = module.workload_identity.client_ids
}

output "workload_identity_expected_service_accounts" {
  value = module.workload_identity.expected_service_accounts
}
```

---

## How teams consume this

1. Terraform creates the UAMI + federated credential + role assignments for a
   given `workload_identities` key (e.g. `container_apps`).
2. The team creates their own K8s ServiceAccount (outside Terraform) matching
   exactly the `namespace` / `service_account_name` declared for their key,
   annotated with the `client_id` from the `client_ids` output:

   ```yaml
   apiVersion: v1
   kind: ServiceAccount
   metadata:
     name: container-app-deployer
     namespace: gitlab-runner
     annotations:
       azure.workload.identity/client-id: "<client_id from output>"
     labels:
       azure.workload.identity/use: "true"
   ```

3. In their `.gitlab-ci.yml` (Kubernetes executor), they point the runner pod
   at that service account, e.g.:

   ```yaml
   variables:
     KUBERNETES_SERVICE_ACCOUNT_OVERWRITE: "container-app-deployer"
   ```

If the ServiceAccount name/namespace in the manifest doesn't exactly match
what's registered in the federated credential's `subject`, federation fails
silently (token exchange rejected) with no Terraform-side error — worth
validating with CI lint / OPA / admission policy if drift is a concern.

## Open design decisions

- Whether `workload_identities` is defined per-environment or in a shared
  source-of-truth file across environments.
- Whether to enforce (via policy/CI) that K8s ServiceAccount manifests match
  the `expected_service_accounts` output exactly.

---

## Required GitLab Runner Helm chart changes

By default, the GitLab Runner Helm chart runs every job pod under one fixed
service account and blocks arbitrary overrides. To support per-team service
account selection via `KUBERNETES_SERVICE_ACCOUNT_OVERWRITE`, the following
changes are needed.

### 1. Allow the service account override (required)

In the runner's `values.yaml` (or `config.toml` if not using the chart),
overriding must be explicitly allowed via a regex — otherwise
`KUBERNETES_SERVICE_ACCOUNT_OVERWRITE` is silently ignored:

```yaml
runners:
  config: |
    [[runners]]
      [runners.kubernetes]
        service_account_overwrite_allowed = "^(container-app-deployer|power-platform-deployer|terraform-deployer)$"
```

The regex should match the **allowed set of service account names** being
handed out — don't leave it as `.*`, or teams could specify any service
account in the cluster, including ones with far more privilege than intended.

### 2. Allow namespace override too, if teams' service accounts live in different namespaces

```toml
[runners.kubernetes]
  namespace_overwrite_allowed = "^(gitlab-runner|team-a|team-b)$"
```

If everything lives in one shared namespace (e.g. `gitlab-runner`, as in the
example above), this may not be needed — but if teams have their own
namespaces, it's required the same way as (1).

### 3. Pod label for Azure Workload Identity webhook (easy to miss)

Azure's workload identity mutating webhook injects the projected token volume
and env vars into a pod **only if the pod itself carries the label**
`azure.workload.identity/use: "true"` — the annotation on the ServiceAccount
alone is not enough. Job pods spun up by the runner need that label too:

```yaml
runners:
  config: |
    [[runners]]
      [runners.kubernetes]
        pod_labels = { "azure.workload.identity/use" = "true" }
```

Or set per-job via `KUBERNETES_POD_LABELS_*` CI/CD variables if you want it
opt-in rather than global.

### 4. RBAC — runner's own ServiceAccount may need permission to use other ServiceAccounts

If Pod Security Admission, OPA/Gatekeeper, or Kyverno policies restrict which
ServiceAccounts a pod can run as, add a `Role`/`RoleBinding` (or policy
exception) permitting the GitLab Runner's controller/manager to create pods
using each team ServiceAccount, e.g.:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: gitlab-runner-use-serviceaccounts
  namespace: gitlab-runner
rules:
  - apiGroups: [""]
    resources: ["serviceaccounts"]
    resourceNames:
      - container-app-deployer
      - power-platform-deployer
      - terraform-deployer
    verbs: ["get", "list"]
```

Plain Kubernetes RBAC does not gate "which SA can a pod use" out of the box —
this step is only needed if admission control in the cluster enforces that
restriction.

### Things to confirm for your setup

- Which **executor mode** is in use — the standard Kubernetes executor vs. the
  newer autoscaler — since config key names differ slightly between chart
  versions.
- Whether the cluster has **any admission control** (OPA/Gatekeeper, Kyverno,
  PSA) restricting pod-to-serviceaccount binding. If not, step 4 is
  unnecessary.
