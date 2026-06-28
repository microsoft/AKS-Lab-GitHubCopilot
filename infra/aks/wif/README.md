# AKS Workload Identity and CSI Handoff

This handoff documents the Lab 05 identity and secret projection checks for the ZavaShop orchestrator on AKS.

## 1. Re-federate the UAMI

Lab 01 creates the UAMI and AKS OIDC issuer. Re-create or verify the federated credential for the orchestrator service account:

```bash
source .env.lab

az identity federated-credential create \
  --name aks-orchestrator \
  --identity-name "$UAMI" \
  --resource-group "$RG" \
  --issuer "$AKS_OIDC" \
  --subject system:serviceaccount:zavashop:orchestrator-sa \
  --audience api://AzureADTokenExchange
```

## 2. Install Secrets Store CSI Driver

Enable the AKS add-on or install the driver plus Azure provider according to your cluster baseline:

```bash
az aks enable-addons \
  -g "$RG" -n "$AKS" \
  --addons azure-keyvault-secrets-provider

kubectl get pods -n kube-system -l app=secrets-store-csi-driver
```

## 3. Seed `GITHUB-TOKEN` in Key Vault

For the lab, seed a GitHub Copilot-compatible token manually. Do not check it into the repo.

```bash
az keyvault secret set \
  --vault-name "$KV" \
  --name GITHUB-TOKEN \
  --value "$GITHUB_TOKEN"
```

The Helm chart projects this as Kubernetes secret `github-token` through `SecretProviderClass`, then maps it to the container as `GITHUB_TOKEN`.

## 4. Validate Entra ID and Azure RBAC

Human operators should authenticate through Microsoft Entra ID and Azure RBAC, not local admin kubeconfig.

```bash
az aks show -g "$RG" -n "$AKS" --query aadProfile -o yaml

az role assignment list --scope "$AKS_ID" \
  --query "[].{role:roleDefinitionName, principal:principalName}" \
  -o table
```

Do not request local admin kubeconfig credentials in CI.

## 5. Validate Defender, Policy, and Monitoring

```bash
az aks show -g "$RG" -n "$AKS" \
  --query addonProfiles.azurepolicy.enabled -o tsv

az aks show -g "$RG" -n "$AKS" \
  --query securityProfile.defender.securityMonitoring.enabled -o tsv

az security pricing show -n Containers --query pricingTier -o tsv
az security pricing show -n KeyVaults --query pricingTier -o tsv

az aks show -g "$RG" -n "$AKS" \
  --query addonProfiles.omsagent.config.logAnalyticsWorkspaceResourceID -o tsv
```

## 6. Production GitHub App Token Broker Stub

The lab uses a Key Vault-hosted `GITHUB-TOKEN`. For production, replace it with a GitHub App plus OIDC-backed token broker that issues short-lived Copilot SDK credentials to the orchestrator pod. Keep the same CSI and Workload Identity pattern, but rotate the credential source from static secret to broker endpoint.
