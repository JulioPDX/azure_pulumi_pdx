"""An Azure RM Python Pulumi program"""

import os
import pulumi
from pulumi_azure_native import resources, network, compute
from infra.vms import VM_DATA

rg_name = "juliopdx_rg_dev"
# from pulumi_azure_native.resources import resource

# Create an Azure Resource Group
# resource_group = resources.ResourceGroup("juliopdx_rg_dev")
resource_group = resources.ResourceGroup("juliopdx_rg_dev",resource_group_name=rg_name)

pulumi.export("resource_group_nm", resource_group.name)

VNETS = {
    "CoreServicesVnet": {
        "region": "westus",
        "vnet_address": "10.20.0.0/16",
        "subnets": [
            {"name": "GatewaySubnet", "subnet": "10.20.0.0/27"},
            {"name": "SharedServicesSubnet", "subnet": "10.20.10.0/24"},
            {"name": "DatabaseSubnet", "subnet": "10.20.20.0/24"},
            {"name": "PublicWebServiceSubnet", "subnet": "10.20.30.0/24"},
        ],
    },
    "ManufacturingVnet": {
        "region": "northeurope",
        "vnet_address": "10.30.0.0/16",
        "subnets": [
            {"name": "ManufacturingSystemSubnet", "subnet": "10.30.10.0/24"},
            {"name": "SensorSubnet1", "subnet": "10.30.20.0/24"},
            {"name": "SensorSubnet2", "subnet": "10.30.21.0/24"},
            {"name": "SensorSubnet3", "subnet": "10.30.22.0/24"},
        ],
    },
    "ResearchVnet": {
        "region": "westindia",
        "vnet_address": "10.40.0.0/16",
        "subnets": [
            {"name": "ResearchSystemSubnet", "subnet": "10.40.0.0/24"},
        ],
    },
}

# Create VNETs and Subnets
for vnet, values in VNETS.items():
    net = network.VirtualNetwork(
        vnet,
        address_space=network.AddressSpaceArgs(
            address_prefixes=[values["vnet_address"]]
        ),
        virtual_network_name=vnet,
        resource_group_name=resource_group.name,
        location=values["region"],
    )
# for vnet, values in VNETS.items():
    for subnet in values["subnets"]:
        sub = network.Subnet(
            subnet["name"],
            address_prefix=subnet["subnet"],
            resource_group_name=resource_group.name,
            subnet_name=subnet["name"],
            virtual_network_name=net.name,
        )

# Private DNS Zone
private_zone = network.PrivateZone(
    "privateZone",
    location="Global",
    private_zone_name="azure_pulumi.com",
    resource_group_name=resource_group.name,
)


# Virtual Network Links to Private DNS
# Having a serious issue using resource_group.name here
# ... very odd
for vnet, values in VNETS.items():
    virtual_network_link = network.VirtualNetworkLink(
        vnet,
        location="Global",
        private_zone_name="azure_pulumi.com",
        registration_enabled=True,
        resource_group_name=resource_group.name,
        virtual_network=network.SubResourceArgs(
            id=f"/subscriptions/{os.environ['SUB_ID']}/resourceGroups/{rg_name}/providers/Microsoft.Network/virtualNetworks/{vnet}"
        ),
        virtual_network_link_name=f"{vnet}-NetworkLink",
    )

for k, v in VM_DATA.items():
    public_ip_address = network.PublicIPAddress(
        f"{k}-publicIPAddress",
        location=v["location"],
        public_ip_address_name=f"{k}-pip",
        resource_group_name=rg_name,
    )

    network_interface = network.NetworkInterface(
        f"{k}-networkInterface",
        enable_accelerated_networking=True,
        ip_configurations=[
            network.NetworkInterfaceIPConfigurationArgs(
                name="ipconfig1",
                public_ip_address=network.PublicIPAddressArgs(
                    id=f"/subscriptions/{os.environ['SUB_ID']}/resourceGroups/{rg_name}/providers/Microsoft.Network/publicIPAddresses/{k}-pip",
                ),
                subnet=network.SubnetArgs(
                    id=f"/subscriptions/{os.environ['SUB_ID']}/resourceGroups/{rg_name}/providers/Microsoft.Network/virtualNetworks/{v['nic_vnet']}/subnets/{v['nic_subnet']}",
                ),
            )
        ],
        location=v["location"],
        network_interface_name=v["nic_name"],
        resource_group_name=rg_name,
    )

for k, v in VM_DATA.items():
    virtual_machine = compute.VirtualMachine(
        f"{v} virtualMachine build",
        hardware_profile=compute.HardwareProfileArgs(
            vm_size="Standard_D1_v2",
        ),
        location=v["location"],
        network_profile=compute.NetworkProfileArgs(
            network_interfaces=[
                compute.NetworkInterfaceReferenceArgs(
                    id=f"/subscriptions/{os.environ['SUB_ID']}/resourceGroups/{rg_name}/providers/Microsoft.Network/networkInterfaces/{v['nic_name']}",
                    primary=True,
                )
            ],
        ),
        os_profile=compute.OSProfileArgs(
            admin_password="JulioPDX789!@#",
            admin_username="juliopdx",
            computer_name=k,
        ),
        resource_group_name=rg_name,
        storage_profile=compute.StorageProfileArgs(
            image_reference=compute.ImageReferenceArgs(
                offer="WindowsServer",
                publisher="MicrosoftWindowsServer",
                sku="2016-Datacenter",
                version="latest",
            ),
            os_disk=compute.OSDiskArgs(
                caching="ReadWrite",
                create_option="FromImage",
                managed_disk=compute.ManagedDiskParametersArgs(
                    storage_account_type="Standard_LRS",
                ),
                name=f"{k}osdisk",
            ),
        ),
        vm_name=k,
    )
