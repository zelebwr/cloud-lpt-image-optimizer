#!/bin/bash
set -e

RESOURCE_GROUP="rg-cloud-lpt"
REGION_1="centralindia"
REGION_2="indonesiacentral"

echo "=== 1. Checking Existing Resource Group ==="
if [ "$(az group exists --name $RESOURCE_GROUP)" = "true" ]; then
  echo "Resource Group '$RESOURCE_GROUP' already exists. Deleting..."
  az group delete --name $RESOURCE_GROUP --yes
  echo "Resource Group '$RESOURCE_GROUP' deleted successfully."
fi

echo "=== 2. Creating Main Resource Group ==="
az group create --name $RESOURCE_GROUP --location $REGION_1

echo "=== 3. Creating Regional Network Security Groups ==="
# NSG Region 1 (Central India - Host A)
az network nsg create \
  --resource-group $RESOURCE_GROUP \
  --name nsg-worker-r1 \
  --location $REGION_1

az network nsg rule create \
  --resource-group $RESOURCE_GROUP \
  --nsg-name nsg-worker-r1 \
  --name AllowHTTP8000 \
  --priority 1000 \
  --destination-port-ranges 8000 \
  --protocol Tcp \
  --access Allow

az network nsg rule create \
  --resource-group $RESOURCE_GROUP \
  --nsg-name nsg-worker-r1 \
  --name AllowSSH \
  --priority 1001 \
  --destination-port-ranges 22 \
  --protocol Tcp \
  --access Allow

# NSG Region 2 (Indonesia Central - Host B)
az network nsg create \
  --resource-group $RESOURCE_GROUP \
  --name nsg-worker-r2 \
  --location $REGION_2

az network nsg rule create \
  --resource-group $RESOURCE_GROUP \
  --nsg-name nsg-worker-r2 \
  --name AllowHTTP8000 \
  --priority 1000 \
  --destination-port-ranges 8000 \
  --protocol Tcp \
  --access Allow

az network nsg rule create \
  --resource-group $RESOURCE_GROUP \
  --nsg-name nsg-worker-r2 \
  --name AllowSSH \
  --priority 1001 \
  --destination-port-ranges 22 \
  --protocol Tcp \
  --access Allow

echo "=== 4. Creating VNets, Subnets, and Associating NSGs ==="
# VNet & Subnet Host A (Central India)
az network vnet create \
  --resource-group $RESOURCE_GROUP \
  --name vnet-host-a \
  --location $REGION_1 \
  --address-prefix 10.0.1.0/24 \
  --subnet-name subnet-host-a

az network vnet subnet update \
  --resource-group $RESOURCE_GROUP \
  --vnet-name vnet-host-a \
  --name subnet-host-a \
  --network-security-group nsg-worker-r1

# VNet & Subnet Host B (Indonesia Central)
az network vnet create \
  --resource-group $RESOURCE_GROUP \
  --name vnet-host-b \
  --location $REGION_2 \
  --address-prefix 10.0.2.0/24 \
  --subnet-name subnet-host-b

az network vnet subnet update \
  --resource-group $RESOURCE_GROUP \
  --vnet-name vnet-host-b \
  --name subnet-host-b \
  --network-security-group nsg-worker-r2

echo "=== 5. Establishing Global VNet Peering ==="
az network vnet peering create \
  --name Peering-HostA-to-HostB \
  --resource-group $RESOURCE_GROUP \
  --vnet-name vnet-host-a \
  --remote-vnet vnet-host-b \
  --allow-vnet-access

az network vnet peering create \
  --name Peering-HostB-to-HostA \
  --resource-group $RESOURCE_GROUP \
  --vnet-name vnet-host-b \
  --remote-vnet vnet-host-a \
  --allow-vnet-access

echo "=== Multi-Region Setup Completed Successfully! ==="
