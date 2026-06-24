# :simple-vmware: vSphere

The `vsphere` provider creates the lab VMs from the same Vagrant box definitions used by the VMware providers, but it does not run `vagrant up` and does not use the `vagrant-vmware-esxi` plugin.

The provider uses:

- `vagrant box add` to download/cache the VMware Vagrant boxes locally
- `ovftool` to import the VMX/OVF/OVA to vSphere over TCP/443
- `govc` to power, inspect, resize, and destroy VMs over TCP/443
- the existing GOAD Ansible inventories for lab provisioning

Ansible provisioning is unchanged. The host running GOAD still needs network access to the created guest IPs on WinRM/SSH.

## Prerequisites

- [Vagrant](https://developer.hashicorp.com/vagrant/install)
- [OVF Tool](https://developer.broadcom.com/tools/open-virtualization-format-ovf-tool/latest)
- [govc](https://github.com/vmware/govmomi/releases)
- vCenter or ESXi reachable on TCP/443
- VMware Tools installed and running in each Vagrant box
- Vagrant boxes with VMware provider artifacts, usually `vmware_desktop`
- Guest credentials for first boot bootstrap, default `vagrant` / `vagrant`

## Configuration

Add or update the vSphere settings in `~/.goad/goad.ini`.

```ini
[vsphere]
vsphere_server = vcenter.example.local
vsphere_user = administrator@vsphere.local
vsphere_password = password
vsphere_allow_unverified_ssl = true
vsphere_datastore = datastore1
vsphere_network = GOAD-LAN
vsphere_ovftool_target =
vsphere_folder =
vsphere_resource_pool =
vsphere_disk_mode = thin
vsphere_box_provider = vmware_desktop
vsphere_bootstrap_guest_network = true
vsphere_guest_username = vagrant
vsphere_guest_password = vagrant
vsphere_ipv4_gateway =
vsphere_ipv4_prefix_length = 27
vsphere_dns_server =
vsphere_vm_name_prefix =
vsphere_overwrite = false
vsphere_ovftool_bin = ovftool
vsphere_govc_bin = govc
```

If `vsphere_ipv4_gateway` or `vsphere_dns_server` is empty, GOAD derives it from `-ip` as `<ip_range>.1`.

For a direct ESXi target, leave `vsphere_ovftool_target` empty. For vCenter, set the inventory path after the server, for example:

```ini
vsphere_ovftool_target = Datacenter/host/Cluster/esxi.example.local
```

VM names are prefixed with the GOAD instance id by default to avoid collisions.

## Installation

```bash
# check prerequisites
./goad.sh -t check -l GOAD -p vsphere -ip 192.168.56

# install
./goad.sh -t install -l GOAD -p vsphere -ip 192.168.56
```

The `-ip` value is still the first three octets used by GOAD inventories. The subnet mask used during vSphere guest customization is controlled by `vsphere_ipv4_prefix_length`.

The first-boot network bootstrap uses VMware Tools guest operations. If that is disabled, the imported boxes must already be reachable at the inventory IPs before Ansible starts.
