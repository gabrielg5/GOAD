# impacket-qa

- Extension name : `impacket-qa`
- Description : Configure existing GOAD hosts for Impacket regression testing
- Compatibility : GOAD
- Providers : virtualbox/azure/vmware/vmware_esxi/vsphere/aws/ludus/proxmox
- Add a machine : none

## What it configures

- Stable `impacket.*` QA users in every GOAD domain.
- A known `IMPACKETQA$` machine account in every GOAD domain.
- LDAPS certificates on `dc01`, `dc02`, and `dc03`.
- DHCP Server on `dc01`.
- RemoteRegistry, Print Spooler, WMI, and firewall state on the main Windows targets.
- Optional Mimilib scheduled task support. The extension does not ship Mimikatz/Mimilib binaries.
- `dcetests-*.cfg` templates with fixed-password hashes and AES keys.

## Default target

Use `dc01` / `kingslanding.sevenkingdoms.local` for the default Impacket remote pytest profile. Some current LDAP tests derive `baseDN` from only the first two DNS labels, so `sevenkingdoms.local` is safer than the child domain `north.sevenkingdoms.local` for the canonical profile.

## Installation

- select your instance
```
load <instance_id>
```

- install the impacket-qa extension
```
install_extension impacket-qa
```

## Test config templates

Copy a template from `extensions/impacket-qa/files/` into the Impacket `tests` directory and replace `{{ip_range}}` with the lab subnet prefix.
