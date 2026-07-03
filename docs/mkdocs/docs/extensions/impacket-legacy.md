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

## Guest credentials

Use shared credentials for the legacy templates:

```ini
[impacket_legacy_vsphere]
guest_username = Administrator
guest_password = TemplatePassword123!
```

If these credentials should be shared by every vSphere VM source, use the
global vSphere values:

```ini
[vsphere]
vsphere_guest_username = Administrator
vsphere_guest_password = TemplatePassword123!
```

The password is masked in provider command logs. The generated Ansible
inventory contains the values directly, so keep `~/.goad/goad.ini` and
workspace inventories private.

## Install

Enable the extension before vSphere install when possible:

```bash
./goad.sh -t install -l GOAD -p vsphere -e impacket-qa,impacket-legacy -ip 10.171.16.32/27
```

If GOAD is already deployed and your orchestrator VM cannot reach WinRM in the
lab, use the provider-only extension command on the orchestrator:

```bash
./goad.sh
load <instance>
provide_extension impacket-legacy
```

This enables the extension, regenerates the workspace files, skips existing VMs
when `vsphere_overwrite=false`, and creates the missing legacy VMs.

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
