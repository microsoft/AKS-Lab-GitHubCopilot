#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

source .env.lab

: "${RG:?missing RG}"
: "${ACR:?missing ACR}"
: "${CAE:?missing CAE}"
: "${KV:?missing KV}"
: "${UAMI_RESOURCE_ID:?missing UAMI_RESOURCE_ID}"
: "${UAMI_CLIENT_ID:?missing UAMI_CLIENT_ID}"

GIT_SHA="${GIT_SHA:-$(git rev-parse --short HEAD)}"
ACR_LOGIN_SERVER="${ACR}.azurecr.io"
CAE_ID="$(az containerapp env show -g "$RG" -n "$CAE" --query id -o tsv)"
ENV_FILE=".env.fqdns"

deploy_app() {
  local name="$1"
  local image_name="$2"
  local target_port="$3"
  local mcp_json="${4:-{}}"
  local image="${ACR_LOGIN_SERVER}/zavashop/${image_name}:${GIT_SHA}"

  az deployment group create \
    -g "$RG" \
    -f infra/aca/agent.bicep \
    -p name="$name" \
    -p envId="$CAE_ID" \
    -p image="$image" \
    -p registryServer="$ACR_LOGIN_SERVER" \
    -p uamiId="$UAMI_RESOURCE_ID" \
    -p uamiClientId="$UAMI_CLIENT_ID" \
    -p keyVaultName="$KV" \
    -p targetPort="$target_port" \
    -p mcpEndpoints="$mcp_json" \
    -p exposeIngress=false \
    -o none

  local fqdn
  fqdn="$(az containerapp show -g "$RG" -n "$name" --query properties.configuration.ingress.fqdn -o tsv)"
  printf 'ZAVA_%s_URL=https://%s/invoke\n' "$(echo "$name" | tr '[:lower:]-' '[:upper:]_')" "$fqdn" >> "$ENV_FILE"
}

rm -f "$ENV_FILE"

deploy_app inventory-mcp inventory-mcp 8080
deploy_app supplier-mcp supplier-mcp 8080
deploy_app shipping-mcp shipping-mcp 8080
deploy_app pricing-mcp pricing-mcp 8080

INVENTORY_MCP_URL="https://$(az containerapp show -g "$RG" -n inventory-mcp --query properties.configuration.ingress.fqdn -o tsv)/mcp"
SUPPLIER_MCP_URL="https://$(az containerapp show -g "$RG" -n supplier-mcp --query properties.configuration.ingress.fqdn -o tsv)/mcp"
SHIPPING_MCP_URL="https://$(az containerapp show -g "$RG" -n shipping-mcp --query properties.configuration.ingress.fqdn -o tsv)/mcp"
PRICING_MCP_URL="https://$(az containerapp show -g "$RG" -n pricing-mcp --query properties.configuration.ingress.fqdn -o tsv)/mcp"

deploy_app inventory inventory 8000 "{\"ZAVA_INVENTORY_MCP_URL\":\"$INVENTORY_MCP_URL\"}"
deploy_app supplier supplier 8000 "{\"ZAVA_SUPPLIER_MCP_URL\":\"$SUPPLIER_MCP_URL\"}"
deploy_app logistics logistics 8000 "{\"ZAVA_SHIPPING_MCP_URL\":\"$SHIPPING_MCP_URL\"}"
deploy_app pricing pricing 8000 "{\"ZAVA_PRICING_MCP_URL\":\"$PRICING_MCP_URL\"}"

cat >> "$ENV_FILE" <<EOF
ZAVA_INVENTORY_MCP_URL=$INVENTORY_MCP_URL
ZAVA_SUPPLIER_MCP_URL=$SUPPLIER_MCP_URL
ZAVA_SHIPPING_MCP_URL=$SHIPPING_MCP_URL
ZAVA_PRICING_MCP_URL=$PRICING_MCP_URL
EOF

printf 'Wrote %s\n' "$ENV_FILE"
