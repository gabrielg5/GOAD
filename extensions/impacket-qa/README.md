# impacket-qa

This extension configures an existing GOAD lab for Impacket regression testing.
It does not create new VMs.

## What it configures

- Stable QA users in each GOAD domain.
- A known machine account named `IMPACKETQA$` in each GOAD domain.
- LDAPS certificates on `dc01`, `dc02`, and `dc03`.
- DHCP Server on `dc01`, used by `tests/dcerpc/test_dhcpm.py`.
- RemoteRegistry and Print Spooler running on the main Windows targets.
- No-op provider templates so the extension can be enabled on any GOAD provider.

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

## Mimilib

The extension does not ship Mimikatz/Mimilib binaries. To run
`tests/dcerpc/test_mimilib.py`, place the required binary on the selected target
and enable the optional scheduled task variables before provisioning that part.
