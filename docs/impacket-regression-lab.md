# Impacket Regression Lab Definition

## Objective

Build a repeatable lab that can run the Impacket test suite under `C:\dev\impacket\tests`, following `C:\dev\impacket\TESTING.md`, and that can also exercise the Impacket example tools against real Windows and Active Directory services.

The lab should be snapshot-driven. Impacket remote tests are not fully idempotent: SAMR, SCMR, RRP, TSCH, secretsdump, SMB file operations, and account-management flows can leave state behind after failures.

## Baseline Decision

Use full `GOAD` as the base lab, then add a small Impacket QA overlay and optional coverage packs.

Full GOAD is the right base because it already provides:

- Three AD domains across two forests.
- Windows Server 2019 and Windows Server 2016 targets.
- Domain controllers, member servers, trusts, LAPS, gMSA, SPNs, ACL test data, IIS, WebDAV, MSSQL, SMB shares, and ADCS.
- Existing extensions for a Windows workstation (`ws01`) and Exchange (`exchange`).

GOAD is not sufficient by itself for full Impacket coverage. The required deltas are:

- LDAPS certificates on each DC used by LDAP tests.
- DHCP service on the DC used by DHCPM RPC tests.
- Mimilib/Mimikatz RPC server on one controlled target.
- Stable test users, hashes, Kerberos AES keys, and machine account hashes for `dcetests.cfg`.
- Separate SMB dialect targets, especially SMB1/NetBIOS/Unicode and SMB3.
- Optional Exchange/RPC-over-HTTP target.
- Optional RODC and legacy Windows targets for old protocol and OS-specific behavior.

## Lab Tiers

### Tier 1: Current Impacket Regression Core

This tier should be built first. It is enough for most current remote pytest coverage except Exchange/RPC-over-HTTP and old SMB dialect edge cases.

| VM | OS | Domain | IP offset | Role |
| --- | --- | --- | --- | --- |
| `runner` | Ubuntu 22.04, Kali, or the Windows host | none | static in lab VLAN | Runs pytest/tox and Impacket examples. Must resolve AD DNS and reach every target. |
| `dc01` / `kingslanding` | Windows Server 2019 DC | `sevenkingdoms.local` | `{{ip_range}}.10` | Canonical remote pytest target. Add LDAPS, DHCP, RemoteRegistry, Print Spooler, optional Mimilib, firewall off. |
| `dc02` / `winterfell` | Windows Server 2019 DC | `north.sevenkingdoms.local` | `{{ip_range}}.11` | Child-domain and trust coverage. Add LDAPS and Windows service settings, but do not use as the default LDAP profile without fixing the test baseDN assumption. |
| `srv02` / `castelblack` | Windows Server 2019 member server | `north.sevenkingdoms.local` | `{{ip_range}}.22` | SMB3 target, MSSQL, IIS, WebDAV, writable admin shares. |
| `dc03` / `meereen` | Windows Server 2016 DC | `essos.local` | `{{ip_range}}.12` | Server 2016 DC variant and ADCS template coverage. Add LDAPS if used by tests. |
| `srv03` / `braavos` | Windows Server 2016/2019 member server, provider-dependent | `essos.local` | `{{ip_range}}.23` | MSSQL, SMB, LAPS-enabled host, second ADCS/MSSQL path. |

Use `dc01` as the main remote test target. Current Impacket LDAP regression tests derive `baseDN` from only the first two DNS labels, so `sevenkingdoms.local` is a safer default than the child domain `north.sevenkingdoms.local`. The QA overlay creates a known `IMPACKETQA$` machine account in each domain, so Netlogon tests do not need a real member-server computer password.

### Tier 2: Full Modern Feature Coverage

Install existing GOAD extensions:

| Extension | VM | OS | IP offset | Why |
| --- | --- | --- | --- | --- |
| `ws01` | `casterlyrock.sevenkingdoms.local` | Windows 10, or Server 2019 on AWS | `{{ip_range}}.31` | Workstation/client behavior, SMB3 client/server checks, WMI/exec target, NTLM relay client, same-domain machine account for `sevenkingdoms.local`. |
| `exchange` | `the-eyrie.sevenkingdoms.local` | Windows Server with Exchange | `{{ip_range}}.21` | `exchanger.py`, Exchange-specific auth paths, RPC-over-HTTP/RPCH testing. Heavy: plan for at least 12 GB RAM. |

Add a small RODC VM if read-only DC behavior must be covered:

| VM | OS | Domain | IP offset | Why |
| --- | --- | --- | --- | --- |
| `rodc01` | Windows Server 2019 RODC | `sevenkingdoms.local` or `north.sevenkingdoms.local` | `{{ip_range}}.13` | RODC secretsdump behavior, replication edge cases, denied password replication groups, RODC-specific Kerberos/Netlogon paths. |

### Tier 3: Legacy Compatibility Coverage

This is only needed for old protocol behavior and parity with the previous QA lab.

| VM | OS | Domain | IP offset | Required configuration |
| --- | --- | --- | --- | --- |
| `dc2012r2` | Windows Server 2012 R2 DC | `legacy.local` or separate GOAD-compatible test domain | `{{ip_range}}.40` | Mirrors Impacket's historical documented DC baseline. AD DS, DNS, DHCP, LDAPS, RemoteRegistry, ADCS web enrollment, Mimilib. |
| `win2008r2` | Windows Server 2008 R2 member | legacy domain | `{{ip_range}}.41` | SMB1 enabled, SMB signing disabled, admin shares available. |
| `win7` | Windows 7 SP1 member | legacy domain | `{{ip_range}}.42` | Preferred target for SMB1, SMB2.0, SMB2.1, NetBIOS session port, Unicode SMB tests. SMB signing disabled. |
| `win10` | Windows 10 21H2/22H2 member | legacy or GOAD domain | `{{ip_range}}.43` | Modern SMB3 and workstation behavior. |
| `winxp` | Windows XP SP3 member/workgroup | isolated legacy segment | `{{ip_range}}.44` | Optional only. SMB1/NetBIOS/NTLMv1 archaeology and regression triage. |

Do not make these old hosts part of the default regression run. Use them for targeted SMB and legacy protocol jobs.

## Required Configuration

### Network and DNS

- Put every VM on one isolated lab VLAN/subnet.
- Use the GOAD provider offsets: DC01 `.10`, DC02 `.11`, DC03 `.12`, SRV02 `.22`, SRV03 `.23`, Exchange `.21`, WS01 `.31`.
- The runner must use AD DNS, or have static records for every NetBIOS name, FQDN, and Kerberos realm name used in config files. This is a test-runner prerequisite, not GOAD lab state.
- Time on the runner and DCs must be synchronized for Kerberos.
- Disable the Windows firewall on lab-facing interfaces for regression targets, matching the existing GOAD vulnerability style.

### Test Identities

Create these in every domain used as a pytest target:

- `impacket.admin`: Domain Admin, AES128/AES256 enabled, stable password.
- `impacket.operator`: Account Operators and Backup Operators, for lower-privileged examples.
- `impacket.user1` through `impacket.user9`: normal users for account-management tests and examples.
- One Unicode user, equivalent to the old lab's `无名氏`, to keep Unicode account handling testable.
- One Protected Users member, equivalent to the old `protegido` account.
- One group equivalent to the old `Grupo de prueba`.

After provisioning, extract and store only in local/private test config:

- `impacket.admin` LM:NT hash.
- `impacket.admin` AES128 and AES256 keys.
- A same-domain machine account LM:NT hash, normally `IMPACKETQA$` in the target domain.

### DC Services

On each DC used for remote pytest:

- AD DS, DNS, LDAP, Kerberos, SMB, Netlogon, SAMR, LSA, DRSUAPI.
- LDAPS on 636 with a certificate whose SAN covers NetBIOS and FQDN names used by tests.
- DHCP Server installed, authorized, and running for `test_dhcpm.py`. The default `impacket-qa` state keeps the same-subnet scope absent because current DHCPM tests assert non-present-subnet edge-case responses.
- RemoteRegistry installed/enabled/running; RRP tests can start it, but it should be available at snapshot time.
- Print Spooler running for RPRN tests. For the QA profile, patched Windows targets should lower `RpcAuthnLevelPrivacyEnabled` to `0` so older RPRN regression expectations still exercise Impacket behavior instead of stopping on spooler hardening.
- TCP/IP NetBIOS enabled for diagnostic/name-query coverage. Impacket NBSTAT node-status tests in `tests/SMB_RPC/test_nmb.py` may still require a legacy SMB/NetBIOS target even when a modern DC is listening on UDP/137.
- Task Scheduler, Event Log, Service Control Manager, WMI/DCOM available.
- Mimilib RPC server running only on the designated Mimilib target, preferably `dc01`.

GOAD already has reusable pieces:

- `ansible/adcs.yml` installs ADCS and web enrollment by default.
- `ansible/dhcp.yml` installs and authorizes DHCP on the `dc` group.
- `ansible/roles/security/ldaps` can import PFX certificates into `LocalMachine\My` and `Root`.
- `ansible/roles/vulns/smbv1` can enable SMB1 where needed.

### Mimilib

`test_mimilib.py` requires the Mimikatz/Mimilib RPC server. Treat this as a controlled test-only service:

- Use a dedicated target, preferably `dc01` in Tier 1 or `dc2012` in Tier 3.
- Disable Defender on that target or add explicit exclusions before copying binaries.
- Start the server at boot with a scheduled task or service running elevated.
- Snapshot immediately after verifying the endpoint is registered through RPC endpoint mapper.

### SMB Dialect Targets

Do not run all `tests/SMB_RPC/test_smb.py` classes against one host. The test file explicitly notes dialect switching issues.

Use profiles:

- SMB1, NetBIOS, Unicode: `win7` or `win2008r2`.
- SMB2.0/2.1: `win7`.
- SMB3: `srv02`, `srv03`, `win10`, or `ws01`.

Keep SMB signing disabled only on the legacy/relay targets. Keep at least one modern signing-enabled target for negative/compatibility checks.

### Example Tool Coverage

The lab should support smoke tests for:

- SMB: `smbclient.py`, `psexec.py`, `smbexec.py`, `wmiexec.py`, `atexec.py`.
- Secrets and registry: `secretsdump.py`, `reg.py`, `registry-read.py`, `regsecrets.py`.
- Kerberos: `getTGT.py`, `getST.py`, `ticketer.py`, `ticketConverter.py`, `GetUserSPNs.py`, `GetNPUsers.py`, `findDelegation.py`.
- LDAP/ACL: `GetADUsers.py`, `GetADComputers.py`, `dacledit.py`, `owneredit.py`, `rbcd.py`, `addcomputer.py`, `GetLAPSPassword.py`.
- MSSQL: `mssqlclient.py`, `mssqlinstance.py`, `checkMSSQLStatus.py` against `srv02` and `srv03`.
- Relay: `ntlmrelayx.py` with WebDAV/IIS/workstation clients and at least one no-signing SMB target.
- Exchange/RPCH: `exchanger.py` and `test_rpch.py` against the `exchange` extension.

## Remote Config Profiles

Store one config per target. Do not reuse a single `dcetests.cfg` for every suite.

Canonical DC profile:

```ini
[TCPTransport]
servername = KINGSLANDING
machine = {{ip_range}}.10
username = impacket.admin
password = <password>
hashes = <lmhash:nthash>
aesKey256 = <aes256>
aesKey128 = <aes128>
domain = sevenkingdoms.local
machineuser = IMPACKETQA$
machineuserhashes = <lmhash:nthash>
```

Recommended profiles:

- `tests/dcetests-goad-dc01.cfg`: default DCE/RPC, LDAP, LDAPS, DHCP, DRSUAPI, secretsdump, WMI/DCOM, RRP, SCMR, TSCH.
- `tests/dcetests-goad-dc02.cfg`: child-domain, trust, and north-domain checks. Avoid it for LDAP tests unless the Impacket test baseDN handling is adjusted for three-label domains.
- `tests/dcetests-goad-dc03.cfg`: Server 2016/Essos variant and trust/forest checks.
- `tests/dcetests-smb1-win7.cfg`: SMB1, NetBIOS, Unicode.
- `tests/dcetests-smb21-win7.cfg`: SMB2.0/2.1.
- `tests/dcetests-smb3-srv02.cfg`: SMB3.
- `tests/dcetests-exchange.cfg`: RPCH/Exchange.
- `tests/dcetests-rodc.cfg`: RODC-specific manual and example testing.

## Snapshot Strategy

Every VM should have these snapshots:

- `base-os`: OS installed, tools/guest additions installed, not domain joined.
- `domain-ready`: joined/promoted, AD data loaded, no Impacket-specific services.
- `impacket-ready`: LDAPS/DHCP/RemoteRegistry/Mimilib/users/hashes verified.
- `pre-run`: clean state immediately before a regression session.

Rollback to `pre-run` after each full remote run. Refresh `pre-run` only after a clean pass.

## Test Execution Matrix

| Coverage | Target profile | Required tier |
| --- | --- | --- |
| Local unit tests, parsers, packet structures, SMB server unit tests | none | host/runner only |
| Windows-only local DPAPI tests | Windows host or Windows runner | host/runner only |
| General DCE/RPC remote tests | `dcetests-goad-dc01.cfg`; pytest command policy belongs in Impacket | Tier 1 |
| LDAP and LDAPS | `dcetests-goad-dc01.cfg` | Tier 1 with LDAPS |
| DHCPM RPC | `dcetests-goad-dc01.cfg` | Tier 1 with DHCP |
| Mimilib RPC | `dcetests-goad-dc01.cfg` | Tier 1 with Mimilib |
| Secretsdump DRSUAPI/VSS | `dcetests-goad-dc01.cfg`; validate with a domain-qualified account such as `SEVENKINGDOMS/krbtgt` | Tier 1 |
| MSSQL examples | `srv02`, `srv03` | Tier 1 |
| ADCS and web enrollment examples | `dc01`, `srv03` | Tier 1 |
| NMB node-status, SMB1, NetBIOS, Unicode pytest | `dcetests-smb1-win7.cfg` | Tier 3 |
| SMB2.0/2.1 pytest | `dcetests-smb21-win7.cfg` | Tier 3 |
| SMB3 pytest | `dcetests-smb3-srv02.cfg` | Tier 1 |
| RPCH and Exchange examples | `dcetests-exchange.cfg` | Tier 2 |
| RODC behavior | `dcetests-rodc.cfg` | Tier 2 add-on |
| NTLM relay | WebDAV/IIS client plus no-signing SMB target | Tier 2 or Tier 3 |

Validation against the GOAD Windows Server 2019 `dc01` target exposed deltas
from Impacket's historical Windows Server 2012 R2 test baseline. Track these
from the Impacket side as old-OS assumptions, modern hardening differences, or
potential Impacket bugs:

- BKRP retrieve-backup-key certificate parsing.
- DRSUAPI pytest calls over `\PIPE\lsass`; DRSUAPI itself is validated with `secretsdump.py`.
- EVEN6 `EvtRpcExportLog`.
- NRPC discovery and `NetrLogonSamLogonEx` hardening paths.
- RRP `BaseRegQueryMultipleValues` fixed-buffer cases.
- SRVS `NetrServerStatisticsGet` with a null service name.
- TSCH SASEC `SAGetNSAccountInformation` fixed-buffer cases.

## Impacket Test Command Groups

Run these from the Impacket repository on the test runner:

```bash
cd ~/impacket
. .venv/bin/activate
RC=tests/dcetests.cfg
```

Broad local and remote groups:

```bash
python -m pytest -m "not remote" -v
python -m pytest -m remote --remote-config "$RC" -v
```

Modern GOAD remote run without optional or legacy-only target families:

```bash
python -m pytest -m remote --remote-config "$RC" \
  --ignore=tests/SMB_RPC/test_smb.py \
  --ignore=tests/SMB_RPC/test_nmb.py \
  --ignore=tests/SMB_RPC/test_rpch.py \
  --ignore=tests/dcerpc/test_mimilib.py \
  -v
```

Validated GOAD core areas:

```bash
python -m pytest tests/dcerpc/test_samr.py --remote-config "$RC" -v
python -m pytest tests/SMB_RPC/test_ldap.py --remote-config "$RC" -v
python -m pytest tests/dcerpc/test_rprn.py --remote-config "$RC" -v
python -m pytest tests/dcerpc/test_dhcpm.py --remote-config "$RC" -v
```

Strict groups that currently look like old OS assumptions or modern Windows
hardening differences:

```bash
python -m pytest tests/dcerpc/test_drsuapi.py --remote-config "$RC" -v
python -m pytest tests/dcerpc/test_nrpc.py --remote-config "$RC" -v
python -m pytest tests/dcerpc/test_srvs.py --remote-config "$RC" -k "NetrServerStatisticsGet" -v
```

Strict groups that currently look like Impacket implementation or test-suite
issues:

```bash
python -m pytest tests/dcerpc/test_bkrp.py -k "RETRIEVE_BACKUP_KEY" --remote-config "$RC" -v
python -m pytest tests/dcerpc/test_even6.py -k "EvtRpcExportLog" --remote-config "$RC" -v
python -m pytest tests/dcerpc/test_rrp.py -k "BaseRegQueryMultipleValues" --remote-config "$RC" -v
python -m pytest tests/dcerpc/test_tsch.py -k "SAGetNSAccountInformation" --remote-config "$RC" -v
```

Known NDR64 candidate:

```bash
python -m pytest tests/dcerpc/test_dhcpm.py::DHCPMTestsTCPTransport64::test_hDhcpEnumSubnetClientsV5 --remote-config "$RC" -v
```

Optional or separate-target groups:

```bash
python -m pytest tests/SMB_RPC/test_nmb.py --remote-config tests/dcetests-smb1-win7.cfg -v
python -m pytest tests/SMB_RPC/test_smb.py --remote-config tests/dcetests-smb1-win7.cfg -v
python -m pytest tests/SMB_RPC/test_rpch.py --remote-config tests/dcetests-exchange.cfg -v
python -m pytest tests/dcerpc/test_mimilib.py --remote-config "$RC" -v
```

These commands are documentation examples for operating the lab. Durable pytest
profiles, deselection policy, and xfail decisions should live in the Impacket
repository.

## Implementation Shape in GOAD

Add one GOAD extension for the automated core and keep legacy coverage in a separate extension:

1. `extensions/impacket-qa`
   - No new VMs.
   - Adds Impacket test users/groups to selected domains.
   - Creates a known `IMPACKETQA$` machine account in each selected domain.
   - Adds self-signed LDAPS certificates on selected DCs.
   - Runs DHCP setup on `dc01`.
   - Configures RemoteRegistry, Print Spooler, WMI, and firewall state on selected Windows targets.
   - Prepares an optional Mimilib target but does not ship Mimikatz/Mimilib binaries.
   - Templates `dcetests-*.cfg` files with fixed-password hashes/keys and a provider IP-range placeholder.

2. `extensions/impacket-legacy`
   - vSphere-only first pass.
   - Adds `dc2012r2`, `win2008r2`, and `win7` from configurable vCenter template paths.
   - Uses shared guest username/password file paths for the legacy templates, with `[vsphere]` paths as fallback.
   - Renders offsets through the selected GOAD CIDR, so `.40`, `.41`, and `.42` do not assume a `/24`.
   - Enables SMB1 and SMB signing-off policies only on legacy targets.
   - Domain promotion/join policy is the next decision point after the actual template baseline is known.

Use existing extensions for:

- `ws01`: workstation and same-domain machine account in `sevenkingdoms.local`.
- `exchange`: Exchange/RPCH coverage.

## Definition of Done

The lab is ready when:

- `pytest -m "not remote"` runs on the runner and on a Windows runner/host for Windows-only local tests.
- DCE/RPC, LDAP/LDAPS, DHCPM, DRSUAPI, RRP, SCMR, TSCH, WMI/DCOM, SRVS/WKST, NRPC, and secretsdump coverage can be run against `dc01` using Impacket-owned command profiles.
- SMB tests pass through separate SMB1, SMB2.1, and SMB3 profiles.
- RPCH tests either pass against Exchange or are explicitly excluded from the core run.
- Example smoke tests cover SMB exec, WMI exec, secretsdump, Kerberos, LDAP/ACL, MSSQL, ADCS, relay, and Exchange where installed.
- A clean `pre-run` snapshot exists for every VM used by the automated run.
