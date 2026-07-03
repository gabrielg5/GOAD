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
- RemoteRegistry, Print Spooler, WMI, TCP/IP NetBIOS, and firewall state on the main Windows targets.
- Spooler RPC privacy relaxed for legacy RPRN regression expectations.
- Optional Mimilib scheduled task support. The extension does not ship Mimikatz/Mimilib binaries.
- `dcetests-*.cfg` templates with fixed-password hashes and AES keys.

By default the DHCP service is installed and authorized, but the same-subnet
scope is absent. This matches the current DHCPM regression tests, which assert
specific non-present-subnet error codes.

The extension disables the default domain account lockout threshold and unlocks
the built-in `Administrator` account. This keeps repeated negative-password SAMR
tests from poisoning later runs.

The spooler RPC privacy setting is intentionally lowered on QA targets. This is
for regression compatibility with older RPRN test expectations on patched
Windows servers, not a production recommendation. NetBIOS and spooler RPC
compatibility changes reboot affected hosts when they first change.

Current Windows Server 2019 targets can have UDP/137 listening and NetBIOS names
registered while still not satisfying Impacket's NBSTAT node-status tests. Keep
`tests/SMB_RPC/test_nmb.py` in the legacy SMB/NetBIOS profile unless it is
validated in the specific provider network.

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

## Core pytest profile

From the Impacket repository root on the test runner, use the helper script to
avoid shell line-continuation mistakes:

```
bash ~/GOAD/extensions/impacket-qa/scripts/run-goad-core.sh
```

Set `REMOTE_CONFIG` or `LOG_FILE` if needed:

```
REMOTE_CONFIG=tests/dcetests.cfg LOG_FILE=goad-core.log bash ~/GOAD/extensions/impacket-qa/scripts/run-goad-core.sh
```

This core profile excludes SMB dialect, NMB, RPCH, Mimilib, and the known DHCPM
NDR64 edge-case test.

## Runner prerequisites

Kerberos tests need the runner to resolve AD realm names such as
`SEVENKINGDOMS.LOCAL`. Configure the test runner to use AD DNS, or add static
records before running the Impacket remote suite. For the default profile, the
runner must resolve `sevenkingdoms.local` / `SEVENKINGDOMS.LOCAL` to `dc01`.

```
getent hosts SEVENKINGDOMS.LOCAL
nc -vz SEVENKINGDOMS.LOCAL 88
```
