// Finder on Azure: one Linux VM running Docker Compose (Finder + Caddy for HTTPS).
// The image is built on the VM itself from sources that deploy.ps1 copies over SSH — no registry
// (cloud builds, ACR Tasks, are not offered in every region or on every subscription type).
//
// Why a VM and not Container Apps / App Service: Finder and Hermes keep state in SQLite databases
// and per-user profile folders (needs a real disk, not an SMB file share), the server must run as
// exactly one instance (agent processes and sign-in sessions live in memory), and it spawns
// child processes (Hermes, MCP tools, headless Chrome).

@description('Azure region for all resources.')
param location string = resourceGroup().location

@description('Short lowercase name used as a prefix for resources and the public DNS label.')
@minLength(3)
@maxLength(12)
param namePrefix string = 'finder'

@description('VM size. 8 GB RAM (B2ms) is comfortable for ~10 concurrent users; B2s (4 GB) works for a demo.')
param vmSize string = 'Standard_B2ms'

@description('Admin user on the VM.')
param adminUsername string = 'azureuser'

@description('SSH public key for the admin user (contents of the .pub file).')
param adminSshPublicKey string

@description('Source address/CIDR allowed to reach SSH (port 22): the machine that deploys. deploy.ps1 passes your current public IP.')
param sshSourceAddress string = ''

@description('Custom domain pointing at the VM (optional). Empty = the Azure name <label>.<region>.cloudapp.azure.com.')
param customDomain string = ''

var suffix = uniqueString(resourceGroup().id)
var dnsLabel = toLower('${namePrefix}-${suffix}')
var vmName = '${namePrefix}-vm'

var baseRules = [
  {
    name: 'allow-http'
    properties: {
      priority: 100
      direction: 'Inbound'
      access: 'Allow'
      protocol: 'Tcp'
      sourceAddressPrefix: '*'
      sourcePortRange: '*'
      destinationAddressPrefix: '*'
      destinationPortRange: '80'
    }
  }
  {
    name: 'allow-https'
    properties: {
      priority: 110
      direction: 'Inbound'
      access: 'Allow'
      protocol: '*'
      sourceAddressPrefix: '*'
      sourcePortRange: '*'
      destinationAddressPrefix: '*'
      destinationPortRange: '443'
    }
  }
]
var sshRule = [
  {
    name: 'allow-ssh'
    properties: {
      priority: 120
      direction: 'Inbound'
      access: 'Allow'
      protocol: 'Tcp'
      sourceAddressPrefix: sshSourceAddress
      sourcePortRange: '*'
      destinationAddressPrefix: '*'
      destinationPortRange: '22'
    }
  }
]

resource nsg 'Microsoft.Network/networkSecurityGroups@2023-11-01' = {
  name: '${namePrefix}-nsg'
  location: location
  properties: {
    securityRules: empty(sshSourceAddress) ? baseRules : concat(baseRules, sshRule)
  }
}

resource vnet 'Microsoft.Network/virtualNetworks@2023-11-01' = {
  name: '${namePrefix}-vnet'
  location: location
  properties: {
    addressSpace: {
      addressPrefixes: [
        '10.20.0.0/16'
      ]
    }
    subnets: [
      {
        name: 'default'
        properties: {
          addressPrefix: '10.20.0.0/24'
          networkSecurityGroup: {
            id: nsg.id
          }
        }
      }
    ]
  }
}

resource publicIp 'Microsoft.Network/publicIPAddresses@2023-11-01' = {
  name: '${namePrefix}-ip'
  location: location
  sku: {
    name: 'Standard'
  }
  properties: {
    publicIPAllocationMethod: 'Static'
    dnsSettings: {
      domainNameLabel: dnsLabel
    }
  }
}

resource nic 'Microsoft.Network/networkInterfaces@2023-11-01' = {
  name: '${namePrefix}-nic'
  location: location
  properties: {
    ipConfigurations: [
      {
        name: 'ipconfig1'
        properties: {
          privateIPAllocationMethod: 'Dynamic'
          subnet: {
            id: vnet.properties.subnets[0].id
          }
          publicIPAddress: {
            id: publicIp.id
          }
        }
      }
    ]
  }
}

var siteHost = empty(customDomain) ? publicIp.properties.dnsSettings.fqdn : customDomain
var cloudInit = replace(loadTextContent('cloud-init.yaml'), '__SITE_HOST__', siteHost)

resource vm 'Microsoft.Compute/virtualMachines@2024-03-01' = {
  name: vmName
  location: location
  properties: {
    hardwareProfile: {
      vmSize: vmSize
    }
    osProfile: {
      computerName: vmName
      adminUsername: adminUsername
      customData: base64(cloudInit)
      linuxConfiguration: {
        disablePasswordAuthentication: true
        ssh: {
          publicKeys: [
            {
              path: '/home/${adminUsername}/.ssh/authorized_keys'
              keyData: adminSshPublicKey
            }
          ]
        }
      }
    }
    storageProfile: {
      imageReference: {
        publisher: 'Canonical'
        offer: 'ubuntu-24_04-lts'
        sku: 'server'
        version: 'latest'
      }
      osDisk: {
        createOption: 'FromImage'
        diskSizeGB: 64
        managedDisk: {
          storageAccountType: 'Premium_LRS'
        }
      }
    }
    networkProfile: {
      networkInterfaces: [
        {
          id: nic.id
        }
      ]
    }
  }
}

output siteUrl string = 'https://${siteHost}'
output azureFqdn string = publicIp.properties.dnsSettings.fqdn
output publicIpAddress string = publicIp.properties.ipAddress
output vmName string = vm.name
output adminUsername string = adminUsername
