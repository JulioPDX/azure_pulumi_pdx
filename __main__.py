"""A Network Engineer trying to learn cloud and IaC"""

import pulumi
from pulumi import Output
from pulumi_azure_native import resources, network, compute
from infra.vms import VM_DATA, VM_DATA_NO_PIP
from infra.vnets import VNETS

config = pulumi.Config()
RG_NAME = config.require('rg_name')

# Create an Azure Resource Group
resource_group = resources.ResourceGroup(RG_NAME, resource_group_name=RG_NAME)

pulumi.export("resource_group_nm", resource_group.name)

# Private DNS Zone
private_zone = network.PrivateZone(
    "privateZone",
    location="Global",
    private_zone_name="azure_pulumi.com",
    resource_group_name=resource_group.name,
)

### NAT Gateway Practice ###
pip_prefix = network.PublicIPPrefix(
    "publicIPPrefix",
    location="westus",
    prefix_length=31,
    public_ip_address_version="IPv4",
    public_ip_prefix_name="test-ipprefix",
    resource_group_name=resource_group.name,
    sku=network.PublicIPPrefixSkuArgs(
        name="Standard",
        tier="Regional",
    ),
)

nat_gateway = network.NatGateway(
    "natGateway",
    location="westus",
    nat_gateway_name="natgateway",
    public_ip_prefixes=[
        network.SubResourceArgs(
            id=pip_prefix.id,
        )
    ],
    resource_group_name=resource_group.name,
    sku=network.NatGatewaySkuArgs(
        name="Standard",
    ),
)

subs = {}
local_vnets = {}

# Create VNETs
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
    local_vnets[vnet] = Output.concat(net.id)
    # Create virtual network links to get auto dns registration in private zone
    virtual_network_link = network.VirtualNetworkLink(
        f"{vnet}-link",
        location="Global",
        private_zone_name=private_zone.name,
        registration_enabled=True,
        resource_group_name=resource_group.name,
        virtual_network=network.SubResourceArgs(id=net.id),
        virtual_network_link_name=f"{vnet}-NetworkLink",
    )
    # Create subnets under each VNET
    for subnet in values["subnets"]:
        if subnet["name"] == "PublicWebServiceSubnet":
            sub = network.Subnet(
                subnet["name"],
                address_prefix=subnet["subnet"],
                resource_group_name=resource_group.name,
                subnet_name=subnet["name"],
                virtual_network_name=net.name,
                nat_gateway=network.SubResourceArgs(id=nat_gateway.id),
            )
        else:
            sub = network.Subnet(
                subnet["name"],
                address_prefix=subnet["subnet"],
                resource_group_name=resource_group.name,
                subnet_name=subnet["name"],
                virtual_network_name=net.name,
            )
        # Neat trick to grab the subnet IDs and add them to dict
        subs[subnet["name"]] = Output.concat(sub.id)

# VNET peering, fairly static
vnet_peering = network.VirtualNetworkPeering(
    "Test-VNET-peer",
    resource_group_name=resource_group.name,
    virtual_network_name="CoreServicesVnet",
    remote_virtual_network=network.SubResourceArgs(id=local_vnets["ResearchVnet"]),
    virtual_network_peering_name="peer",
)

second_vnet_peering = network.VirtualNetworkPeering(
    "Test-VNET-peer2",
    resource_group_name=resource_group.name,
    virtual_network_name="ResearchVnet",
    remote_virtual_network=network.SubResourceArgs(id=local_vnets["CoreServicesVnet"]),
    virtual_network_peering_name="peer",
)

# Create all the things for VM
for k, v in VM_DATA.items():
    pip = network.PublicIPAddress(
        f"{k}-pip",
        location=v["location"],
        public_ip_address_name=f"{k}-pip",
        resource_group_name=resource_group.name,
    )
    nic = network.NetworkInterface(
        f"{k}-nic",
        enable_accelerated_networking=True,
        ip_configurations=[
            network.NetworkInterfaceIPConfigurationArgs(
                name="ipconfig1",
                public_ip_address=network.PublicIPAddressArgs(id=pip.id),
                subnet=network.SubnetArgs(
                    id=subs[v["nic_subnet"]],
                ),
            )
        ],
        location=v["location"],
        network_interface_name=v["nic_name"],
        resource_group_name=resource_group.name,
    )
    virtual_machine = compute.VirtualMachine(
        f"{k} build",
        hardware_profile=compute.HardwareProfileArgs(
            vm_size="Standard_D1_v2",
        ),
        location=v["location"],
        network_profile=compute.NetworkProfileArgs(
            network_interfaces=[
                compute.NetworkInterfaceReferenceArgs(
                    id=nic.id,
                    primary=True,
                )
            ],
        ),
        os_profile=compute.OSProfileArgs(
            admin_password=config.require('passwd'),
            admin_username="juliopdx",
            computer_name=k,
        ),
        resource_group_name=resource_group.name,
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
                name=f"{k}osdisk1",
            ),
        ),
        vm_name=k,
    )

### Add two VMs with no public IP and test access
for k, v in VM_DATA_NO_PIP.items():
    nic = network.NetworkInterface(
        f"{k}-nic",
        enable_accelerated_networking=True,
        ip_configurations=[
            network.NetworkInterfaceIPConfigurationArgs(
                name="ipconfig1",
                subnet=network.SubnetArgs(
                    id=subs[v["nic_subnet"]],
                ),
            )
        ],
        location=v["location"],
        network_interface_name=v["nic_name"],
        resource_group_name=resource_group.name,
    )
    virtual_machine = compute.VirtualMachine(
        f"{k} build",
        hardware_profile=compute.HardwareProfileArgs(
            vm_size="Standard_D1_v2",
        ),
        location=v["location"],
        network_profile=compute.NetworkProfileArgs(
            network_interfaces=[
                compute.NetworkInterfaceReferenceArgs(
                    id=nic.id,
                    primary=True,
                )
            ],
        ),
        os_profile=compute.OSProfileArgs(
            admin_password=config.require('passwd'),
            admin_username="juliopdx",
            computer_name=k,
        ),
        resource_group_name=resource_group.name,
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
                name=f"{k}osdisk1",
            ),
        ),
        vm_name=k,
    )


# Virtual WAN Stuffs and VNET Gateways
# No more, it takes so long to build and destroy
# virtual_wan = network.VirtualWan(
#     "TestVirtualWan",
#     allow_branch_to_branch_traffic=True,
#     allow_vnet_to_vnet_traffic=True,
#     resource_group_name=resource_group.name,
#     location=resource_group.location,
#     type="Standard",
#     virtual_wan_name="wan1",
# )

# virtual_hub = network.VirtualHub(
#     "TestVirtualHub",
#     resource_group_name=resource_group.name,
#     location=resource_group.location,
#     virtual_wan=network.SubResourceArgs(id=virtual_wan.id),
#     sku="Standard",
#     virtual_hub_name="virtualHug0",
#     address_prefix="10.60.0.0/24",
# )

# vpn_gateway = network.VpnGateway(
#     "VPN Gateway",
#     gateway_name="myGate",
#     resource_group_name=resource_group.name,
#     virtual_hub=network.SubResourceArgs(id=virtual_hub.id),
#     vpn_gateway_scale_unit=1,
# )

# hub_virtual_network_connection = network.HubVirtualNetworkConnection(
#     "hubVirtualNetworkConnection",
#     connection_name="connection1",
#     enable_internet_security=False,
#     remote_virtual_network=network.SubResourceArgs(
#         id=local_vnets["ResearchVnet"],
#     ),
#     resource_group_name=resource_group.name,
#     virtual_hub_name=virtual_hub.name,
# )

vms_name = "juliopdx-vmss"

virtual_machine_scale_set = compute.VirtualMachineScaleSet("virtualMachineScaleSet",
    location="westus",
    overprovision=False,
    resource_group_name=resource_group.name,
    single_placement_group=False,
    platform_fault_domain_count=1,
    sku=compute.SkuArgs(
        capacity=3,
        name="Standard_B2s",
        tier="Standard",
    ),
    upgrade_policy=compute.UpgradePolicyArgs(
        mode="Manual",
    ),
    virtual_machine_profile=compute.VirtualMachineScaleSetVMProfileArgs(
        network_profile=compute.VirtualMachineScaleSetNetworkProfileArgs(
            network_interface_configurations=[compute.VirtualMachineScaleSetNetworkConfigurationArgs(
                enable_ip_forwarding=True,
                ip_configurations=[compute.VirtualMachineScaleSetIPConfigurationArgs(
                    name=vms_name,
                    subnet=compute.ApiEntityReferenceArgs(
                        id=subs["PublicWebServiceSubnet"],
                    ),
                )],
                name=vms_name,
                primary=True,
            )],
        ),
        os_profile=compute.VirtualMachineScaleSetOSProfileArgs(
            admin_password=config.require('passwd'),
            admin_username="juliopdx",
            computer_name_prefix="ado-ss",
        ),
        storage_profile=compute.VirtualMachineScaleSetStorageProfileArgs(
            image_reference=compute.ImageReferenceArgs(
                offer="UbuntuServer",
                publisher="Canonical",
                sku="18.04-LTS",
                version="latest",
            ),
            os_disk=compute.VirtualMachineScaleSetOSDiskArgs(
                caching="ReadWrite",
                create_option="FromImage",
                managed_disk=compute.VirtualMachineScaleSetManagedDiskParametersArgs(
                    storage_account_type="Premium_LRS",
                ),
            ),
        ),
    ),
    vm_scale_set_name=vms_name)
