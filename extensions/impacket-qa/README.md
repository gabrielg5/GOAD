# impacket-qa

This extension configures an existing GOAD lab for Impacket regression testing.
It does not create new VMs.

## What it configures

- Stable QA users in each GOAD domain.
- A known machine account named `IMPACKETQA$` in each GOAD domain.
- LDAPS certificates on `dc01`, `dc02`, and `dc03`.
- DHCP Server on `dc01`, used by `tests/dcerpc/test_dhcpm.py`.
- RemoteRegistry, Print Spooler, WMI, and TCP/IP NetBIOS services on the main Windows targets.
- Spooler RPC privacy relaxed for legacy RPRN regression expectations.
- No-op provider templates so the extension can be enabled on any GOAD provider.

The DHCP service is installed and authorized, but the default QA state removes
the same-subnet DHCP scope. Current DHCPM tests assert specific edge-case error
codes for a non-present subnet. Set `impacket_qa_dhcp_scope_state=present` only
if you need a real lease scope instead of matching those regression tests.

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

## Default pytest target

Use `dc01` / `kingslanding.sevenkingdoms.local` as the default remote target.
Several Impacket LDAP tests derive the base DN from only the first two DNS labels,
so `sevenkingdoms.local` and `essos.local` are safer default targets than the
child domain `north.sevenkingdoms.local`.

## Accounts

The extension creates these accounts in every GOAD domain:

- `impacket.admin` / `Imp@cket-Admin123!`
- `impacket.operator` / `Imp@cket-Operator123!`
- `impacket.user1` through `impacket.user9` / `Imp@cket-User123!`
- `impacket.protected` / `Imp@cket-Protected123!`
- Unicode sAMAccountName built from `U+65E0 U+540D U+6C0F` / `Imp@cket-Unicode123!`
- `IMPACKETQA$` machine account / `Imp@cket-Machine123!`

## Remote config templates

Copy one of the templates from `extensions/impacket-qa/files/` into
`C:\dev\impacket\tests` and replace `{{ip_range}}`.

The templates include hashes and AES keys for the fixed passwords above. If you
change those passwords, recompute the values from the Impacket checkout. For
example, to recompute the machine account hash:

```powershell
py -3 -c "from impacket.ntlm import compute_lmhash, compute_nthash; p='Imp@cket-Machine123!'; print(compute_lmhash(p).hex()+':'+compute_nthash(p).hex())"
```

The user hash and AES keys can be obtained with `secretsdump.py` against the
configured DC, or computed/collected with your existing Impacket test workflow.

## Core pytest profile

From the Impacket repository root on the test runner, use the helper script to
avoid shell line-continuation mistakes. By default this runs the expected-green
GOAD modern profile:

```bash
bash ~/GOAD/extensions/impacket-qa/scripts/run-goad-core.sh
```

Set `REMOTE_CONFIG` or `LOG_FILE` if needed:

```bash
REMOTE_CONFIG=tests/dcetests.cfg LOG_FILE=goad-core.log bash ~/GOAD/extensions/impacket-qa/scripts/run-goad-core.sh
```

This profile excludes SMB dialect, NMB, RPCH, Mimilib, the known DHCPM NDR64
edge-case test, and the currently classified GOAD/Server 2019 deltas:

- BKRP retrieve-backup-key certificate parsing.
- DRSUAPI pytest calls over `\PIPE\lsass`; DRSUAPI itself is validated with
  `secretsdump.py`.
- EVEN6 `EvtRpcExportLog`.
- NRPC discovery and `NetrLogonSamLogonEx` hardening paths.
- RRP `BaseRegQueryMultipleValues` fixed-buffer cases.
- SRVS `NetrServerStatisticsGet` with a null service name.
- TSCH SASEC `SAGetNSAccountInformation` fixed-buffer cases.

Run strict mode to include those deltas for investigation:

```bash
STRICT=1 bash ~/GOAD/extensions/impacket-qa/scripts/run-goad-core.sh
```

Validate DRSUAPI with:

```bash
python examples/secretsdump.py -just-dc-user 'SEVENKINGDOMS/krbtgt' -dc-ip 10.171.16.42 'sevenkingdoms.local/impacket.admin:Imp@cket-Admin123!@10.171.16.42'
```

## Runner prerequisites

Kerberos tests need the runner to resolve AD realm names such as
`SEVENKINGDOMS.LOCAL`. Configure the test runner to use AD DNS, or add static
records before running the Impacket remote suite. A minimal `/etc/hosts` entry
for the default profile is:

```bash
10.171.16.42 sevenkingdoms.local SEVENKINGDOMS.LOCAL kingslanding kingslanding.sevenkingdoms.local KINGSLANDING dc01
```

Use the actual `dc01` IP for your lab.

## Mimilib

The extension does not ship Mimikatz/Mimilib binaries. To run
`tests/dcerpc/test_mimilib.py`, place the required binary on the selected target
and enable the optional scheduled task variables before provisioning that part.
