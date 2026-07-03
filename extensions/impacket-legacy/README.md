# Impacket Legacy Extension

Optional vSphere-only targets for Impacket tests that still assume older
Windows behavior, SMB1, or NetBIOS-era defaults.

This extension is separate from `impacket-qa` on purpose. `impacket-qa`
configures the existing GOAD hosts; `impacket-legacy` adds extra VMs.

## vSphere configuration

Set the legacy template paths in `~/.goad/goad.ini`:

```ini
[impacket_legacy_vsphere]
dc2012r2_template = /Datacenter/vm/Templates/win2012r2
win2008r2_template = /Datacenter/vm/Templates/win2008r2
win7_template = /Datacenter/vm/Templates/win7

dc2012r2_guest_username_path = /secure/goad/dc2012r2.user
dc2012r2_guest_password_path = /secure/goad/dc2012r2.pass
win2008r2_guest_username_path = /secure/goad/win2008r2.user
win2008r2_guest_password_path = /secure/goad/win2008r2.pass
win7_guest_username_path = /secure/goad/win7.user
win7_guest_password_path = /secure/goad/win7.pass
```

If all legacy templates use the same bootstrap credentials, use the shared
paths in `[vsphere]` instead:

```ini
[vsphere]
vsphere_guest_username_path = /secure/goad/legacy.user
vsphere_guest_password_path = /secure/goad/legacy.pass
```

The files should contain only the username or password value. The provider
reads them on the orchestrator VM and masks the password in command logs.

## IPs

The extension uses legacy offsets `.40`, `.41`, and `.42`. GOAD renders those
through the selected `-ip` value, so a CIDR such as `10.171.16.32/27` is
handled by the same IP mapper as the rest of the lab.

## Current scope

This first pass creates and bootstraps the VMs, then applies compatibility
settings for firewall, RemoteRegistry, Spooler, NetBIOS, SMB1, and SMB signing.
Domain promotion or domain join policy depends on how the supplied templates
are built and should be finalized after the actual template baseline is known.
