param(
	[Parameter(Mandatory = $false)]
	[string]$SubscriptionId = "0dfc2b8f-9b5d-4835-997b-d82546b59d58",

	[Parameter(Mandatory = $false)]
	[string]$ResourceGroup = "CoPaDeploymentSwedon",

	[Parameter(Mandatory = $false)]
	[string]$Location = "swedencentral",

	[Parameter(Mandatory = $false)]
	[string]$AcrName = "aetheracrprod01",

	[Parameter(Mandatory = $false)]
	[string]$ContainerAppEnvironment = "aca-env-aetherdev",

	[Parameter(Mandatory = $false)]
	[string]$ContainerAppName = "aca-backend-aetherdev",

	[Parameter(Mandatory = $false)]
	[string]$ImageRepository = "aetherdev-backend",

	[Parameter(Mandatory = $false)]
	[string]$ImageTag = "v1",

	[Parameter(Mandatory = $false)]
	[string]$OpenAiResourceGroup = "CoPaDeploymentSwedon",

	[Parameter(Mandatory = $false)]
	[string]$OpenAiAccountName = "azureopenai-poc-10",

	[Parameter(Mandatory = $false)]
	[string]$StorageResourceGroup = "CoPaDeploymentSwedon",

	[Parameter(Mandatory = $false)]
	[string]$StorageAccountName = "aetherartifacts",

	[Parameter(Mandatory = $false)]
	[string]$AzureOpenAiEndpoint = "https://azureopenai-poc-10.cognitiveservices.azure.com/",

	[Parameter(Mandatory = $false)]
	[string]$AzureOpenAiDeploymentName = "gpt-4.1",

	[Parameter(Mandatory = $false)]
	[string]$StorageAccountUrl = "https://aetherartifacts.blob.core.windows.net",

	[Parameter(Mandatory = $false)]
	[string]$StorageContainerName = "artifacts",

	[Parameter(Mandatory = $true)]
	[string]$FrontendUrl,

	[Parameter(Mandatory = $false)]
	[string]$Port = "8000",

	[Parameter(Mandatory = $false)]
	[string]$AppDebug = "false"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Section {
	param([string]$Message)
	Write-Host "`n=== $Message ===" -ForegroundColor Cyan
}

function Ensure-RoleAssignment {
	param(
		[Parameter(Mandatory = $true)]
		[string]$AssigneeObjectId,
		[Parameter(Mandatory = $true)]
		[string]$Scope,
		[Parameter(Mandatory = $true)]
		[string]$RoleName
	)

	$existing = az role assignment list `
		--assignee $AssigneeObjectId `
		--scope $Scope `
		--query "[?roleDefinitionName=='$RoleName'] | length(@)" `
		-o tsv

	if ($existing -eq "0") {
		az role assignment create `
			--assignee $AssigneeObjectId `
			--role $RoleName `
			--scope $Scope | Out-Null
		Write-Host "Assigned role '$RoleName' on scope '$Scope'." -ForegroundColor Green
	}
	else {
		Write-Host "Role '$RoleName' already assigned on scope '$Scope'." -ForegroundColor Yellow
	}
}

if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
	throw "Azure CLI is not installed or not in PATH."
}

Write-Section "Selecting subscription"
az account show | Out-Null
az account set --subscription $SubscriptionId

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir

Write-Section "Ensuring resource group"
az group create --name $ResourceGroup --location $Location | Out-Null

Write-Section "Ensuring Azure Container Registry"
$acrExists = az acr list --resource-group $ResourceGroup --query "[?name=='$AcrName'] | length(@)" -o tsv
if ($acrExists -eq "0") {
	az acr create --resource-group $ResourceGroup --name $AcrName --sku Basic --location $Location | Out-Null
	Write-Host "Created ACR: $AcrName" -ForegroundColor Green
}
else {
	Write-Host "ACR already exists: $AcrName" -ForegroundColor Yellow
}

$acrLoginServer = az acr show --resource-group $ResourceGroup --name $AcrName --query loginServer -o tsv
$image = "$acrLoginServer/$ImageRepository`:$ImageTag"

Write-Section "Building and pushing backend image with ACR Tasks"
Push-Location $repoRoot
try {
	az acr build -r $AcrName -t "$ImageRepository`:$ImageTag" -f backend/Dockerfile backend
}
finally {
	Pop-Location
}

Write-Section "Ensuring Container Apps extension"
az extension add --name containerapp --upgrade | Out-Null

Write-Section "Ensuring Container Apps environment"
$envExists = az containerapp env list --resource-group $ResourceGroup --query "[?name=='$ContainerAppEnvironment'] | length(@)" -o tsv
if ($envExists -eq "0") {
	az containerapp env create `
		--name $ContainerAppEnvironment `
		--resource-group $ResourceGroup `
		--location $Location | Out-Null
	Write-Host "Created Container Apps environment: $ContainerAppEnvironment" -ForegroundColor Green
}
else {
	Write-Host "Container Apps environment already exists: $ContainerAppEnvironment" -ForegroundColor Yellow
}

Write-Section "Creating or updating Container App"
$appExists = az containerapp list --resource-group $ResourceGroup --query "[?name=='$ContainerAppName'] | length(@)" -o tsv

if ($appExists -eq "0") {
	az containerapp create `
		--name $ContainerAppName `
		--resource-group $ResourceGroup `
		--environment $ContainerAppEnvironment `
		--image $image `
		--target-port $Port `
		--ingress external `
		--min-replicas 1 `
		--max-replicas 3 `
		--cpu 1.0 `
		--memory 2.0Gi `
		--registry-server $acrLoginServer `
		--system-assigned `
		--env-vars `
			AZURE_OPENAI_ENDPOINT=$AzureOpenAiEndpoint `
			AZURE_OPENAI_DEPLOYMENT_NAME=$AzureOpenAiDeploymentName `
			FRONTEND_URL=$FrontendUrl `
			PORT=$Port `
			DEBUG=$AppDebug `
			AZURE_SUBSCRIPTION_ID=$SubscriptionId `
			AZURE_RESOURCE_GROUP=$ResourceGroup `
			AZURE_STORAGE_ACCOUNT_URL=$StorageAccountUrl `
			AZURE_STORAGE_CONTAINER_NAME=$StorageContainerName | Out-Null
	Write-Host "Created Container App: $ContainerAppName" -ForegroundColor Green
}
else {
	az containerapp update `
		--name $ContainerAppName `
		--resource-group $ResourceGroup `
		--image $image `
		--set-env-vars `
			AZURE_OPENAI_ENDPOINT=$AzureOpenAiEndpoint `
			AZURE_OPENAI_DEPLOYMENT_NAME=$AzureOpenAiDeploymentName `
			FRONTEND_URL=$FrontendUrl `
			PORT=$Port `
			DEBUG=$AppDebug `
			AZURE_SUBSCRIPTION_ID=$SubscriptionId `
			AZURE_RESOURCE_GROUP=$ResourceGroup `
			AZURE_STORAGE_ACCOUNT_URL=$StorageAccountUrl `
			AZURE_STORAGE_CONTAINER_NAME=$StorageContainerName | Out-Null

	$principalIdCheck = az containerapp show --name $ContainerAppName --resource-group $ResourceGroup --query identity.principalId -o tsv
	if (-not $principalIdCheck) {
		az containerapp update --name $ContainerAppName --resource-group $ResourceGroup --system-assigned | Out-Null
	}

	Write-Host "Updated Container App: $ContainerAppName" -ForegroundColor Green
}

Write-Section "Assigning RBAC roles"
$appPrincipalId = az containerapp show --name $ContainerAppName --resource-group $ResourceGroup --query identity.principalId -o tsv
if (-not $appPrincipalId) {
	throw "Could not resolve Container App managed identity principal ID."
}

$acrId = az acr show --resource-group $ResourceGroup --name $AcrName --query id -o tsv
$openAiId = az cognitiveservices account show --resource-group $OpenAiResourceGroup --name $OpenAiAccountName --query id -o tsv
$storageId = az storage account show --resource-group $StorageResourceGroup --name $StorageAccountName --query id -o tsv

Ensure-RoleAssignment -AssigneeObjectId $appPrincipalId -Scope $acrId -RoleName "AcrPull"
Ensure-RoleAssignment -AssigneeObjectId $appPrincipalId -Scope $openAiId -RoleName "Cognitive Services OpenAI User"
Ensure-RoleAssignment -AssigneeObjectId $appPrincipalId -Scope $storageId -RoleName "Storage Blob Data Contributor"

Write-Section "Deployment outputs"
$fqdn = az containerapp show --name $ContainerAppName --resource-group $ResourceGroup --query properties.configuration.ingress.fqdn -o tsv
Write-Host "Container App URL: https://$fqdn" -ForegroundColor Green
Write-Host "Health URL: https://$fqdn/health" -ForegroundColor Green
Write-Host "Image deployed: $image" -ForegroundColor Green

Write-Section "Done"
Write-Host "Deployment completed successfully." -ForegroundColor Green
