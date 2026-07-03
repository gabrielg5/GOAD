# impacket-legacy

The `impacket-legacy` extension adds optional Windows legacy targets for
Impacket regression tests that depend on older operating-system behavior.

This extension is currently vSphere-only.

## Targets

| Host | Offset | Purpose |
| --- | --- | --- |
| `dc2012r2` | `.40` | Windows Server 2012 R2 target for old DC behavior. |
| `win2008r2` | `.41` | Windows Server 2008 R2 SMB1/NetBIOS target. |
| `win7` | `.42` | Windows 7 SMB1, SMB2.0/2.1, Unicode, and NetBIOS target. |

Offsets are rendered through GOAD's selected `-ip` value. For example, a
`/27` CIDR is remapped automatically instead of assuming a full `/24`.

## vSphere template settings

Set vCenter template inventory paths in `~/.goad/goad.ini`:

```ini
[impacket_legacy_vsphere]
dc2012r2_template = /Datacenter/vm/Templates/win2012r2
win2008r2_template = /Datacenter/vm/Templates/win2008r2
win7_template = /Datacenter/vm/Templates/win7
```

The provider clones these with `govc vm.clone`, then applies the same VMware
Tools bootstrap used by the GOAD vSphere provider.

## Guest credential files

Use per-template credential files when the templates do not share the same
local Administrator credentials:

```ini
[impacket_legacy_vsphere]
dc2012r2_guest_username_path = /secure/goad/dc2012r2.user
dc2012r2_guest_password_path = /secure/goad/dc2012r2.pass
win2008r2_guest_username_path = /secure/goad/win2008r2.user
win2008r2_guest_password_path = /secure/goad/win2008r2.pass
win7_guest_username_path = /secure/goad/win7.user
win7_guest_password_path = /secure/goad/win7.pass
```

If all legacy templates share credentials, use the shared vSphere paths:

```ini
[vsphere]
vsphere_guest_username_path = /secure/goad/legacy.user
vsphere_guest_password_path = /secure/goad/legacy.pass
```

The files are read by the orchestrator VM. The password is masked in provider
command logs. The generated Ansible inventory keeps file lookups instead of
writing the password value directly.

## Install

Enable the extension before vSphere install when possible:

```bash
./goad.sh -t install -l GOAD -p vsphere -e impacket-qa,impacket-legacy -ip 10.171.16.32/27
```

If GOAD is already deployed, enabling the extension and running install again
will skip existing VMs when `vsphere_overwrite=false` and create the missing
legacy VMs.

Then apply the extension configuration:

```bash
ansible -i ad/GOAD/data/inventory \
  -i workspaces/<instance>/inventory \
  -i workspaces/<instance>/globalsettings.ini \
  -i workspaces/<instance>/impacket-legacy_inventory \
  impacket_legacy_windows -m win_ping

ansible-playbook -i ad/GOAD/data/inventory \
  -i workspaces/<instance>/inventory \
  -i workspaces/<instance>/globalsettings.ini \
  -i workspaces/<instance>/impacket-legacy_inventory \
  extensions/impacket-legacy/ansible/install.yml
```

## Scope

This first pass creates and bootstraps the VMs and applies compatibility
settings: firewall off, RemoteRegistry, Spooler, NetBIOS over TCP/IP, SMB1 on
legacy SMB targets, and SMB signing-off registry values.

Domain promotion and domain-join policy are intentionally left for the next
step because they depend on the actual template baseline: base OS templates,
already-domain-joined templates, or prebuilt legacy-domain snapshots.
