#!/bin/bash
set -e

RESOURCE_GROUP="rg-cloud-lpt"
LOCATION="centralindia"           # Updated to Central India
VNET_NAME="vnet-datacenter"
NSG_NAME="nsg-worker"

echo "=== 1. Creating Resource Group & VNet ==="
az group create --name $RESOURCE_GROUP --location $LOCATION

az network vnet create \
  --resource-group $RESOURCE_GROUP \
  --name $VNET_NAME \
  --address-prefix 10.0.0.0/16

echo "=== 2. Creating Subnets (Host A & Host B) ==="
az network vnet subnet create \
  --resource-group $RESOURCE_GROUP \
  --vnet-name $VNET_NAME \
  --name subnet-host-a \
  --address-prefix 10.0.1.0/24

az network vnet subnet create \
  --resource-group $RESOURCE_GROUP \
  --vnet-name $VNET_NAME \
  --name subnet-host-b \
  --address-prefix 10.0.2.0/24

echo "=== 3. Creating Network Security Group & Rules ==="
az network nsg create --resource-group $RESOURCE_GROUP --name $NSG_NAME

az network nsg rule create \
  --resource-group $RESOURCE_GROUP \
  --nsg-name $NSG_NAME \
  --name AllowHTTP8000 \
  --priority 1000 \
  --destination-port-ranges 8000 \
  --protocol Tcp \
  --access Allow

az network nsg rule create \
  --resource-group $RESOURCE_GROUP \
  --nsg-name $NSG_NAME \
  --name AllowSSH \
  --priority 1001 \
  --destination-port-ranges 22 \
  --protocol Tcp \
  --access Allow
