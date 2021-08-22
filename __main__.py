"""A Network Engineer trying to learn cloud and IaC"""

import pulumi
from pulumi import Output
from pulumi_azure_native import resources, network, compute
from infra.vms import VM_DATA
from infra.vnets import VNETS

RG_NAME = "juliopdx_rg_dev"

# Create an Azure Resource Group
resource_group = resources.ResourceGroup("juliopdx_rg_dev", resource_group_name=RG_NAME)

pulumi.export("resource_group_nm", resource_group.name)

# Private DNS Zone
private_zone = network.PrivateZone(
    "privateZone",
    location="Global",
    private_zone_name="azure_pulumi.com",
    resource_group_name=resource_group.name,
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
        f"{k}-publicIPAddress",
        location=v["location"],
        public_ip_address_name=f"{k}-pip",
        resource_group_name=resource_group.name,
    )
    nic = network.NetworkInterface(
        f"{k}-networkInterface",
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
        f"{k}-virtualMachine build",
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
            admin_password="JulioPDX789!@#",  # Dont do this in prod... or ever, dont be me.
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


### NAT Gateeway Practice ###
pip_prefix = network.PublicIPPrefix("publicIPPrefix",
    location="westus",
    prefix_length=31,
    public_ip_address_version="IPv4",
    public_ip_prefix_name="test-ipprefix",
    resource_group_name=resource_group.name,
    sku=network.PublicIPPrefixSkuArgs(
        name="Standard",
        tier="Regional",
    ))

# pulumi.export("pip_prefix", pip_prefix)

# nat_pip = network.PublicIPAddress(
#     "nat-publicIPAddress",
#     location="westus",
#     public_ip_allocation_method="Static",
#     public_ip_address_name="nat-pip",
#     public_ip_prefix=network.SubResourceArgs(id=pip_prefix.id),
#     resource_group_name=resource_group.name,
#     sku=network.PublicIPAddressSkuArgs(
#         name="Standard",
#     ),
# )

# pulumi.export("nat_pip", nat_pip.public_ip_prefix)

nat_gateway = network.NatGateway(
    "natGateway",
    location="westus",
    nat_gateway_name="natgateway",
    # public_ip_addresses=[network.PublicIPAddressArgs(id=nat_pip.id)],
    public_ip_prefixes=[network.SubResourceArgs(
        id=pip_prefix.id,
    )],
    resource_group_name=resource_group.name,
    sku=network.NatGatewaySkuArgs(
        name="Standard",
    ),
)
