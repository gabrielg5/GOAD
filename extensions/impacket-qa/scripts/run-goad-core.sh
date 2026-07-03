#!/usr/bin/env bash
set -euo pipefail

remote_config="${REMOTE_CONFIG:-tests/dcetests.cfg}"
log_file="${LOG_FILE:-impacket-goad-core-$(date +%F-%H%M).log}"

if [[ ! -f "$remote_config" ]]; then
  echo "Remote config not found: $remote_config" >&2
  echo "Run this from the Impacket repository root or set REMOTE_CONFIG." >&2
  exit 2
fi

python -m pytest -m remote \
  --remote-config "$remote_config" \
  --ignore=tests/SMB_RPC/test_smb.py \
  --ignore=tests/SMB_RPC/test_nmb.py \
  --ignore=tests/SMB_RPC/test_rpch.py \
  --ignore=tests/dcerpc/test_mimilib.py \
  --deselect=tests/dcerpc/test_dhcpm.py::DHCPMTestsTCPTransport64::test_hDhcpEnumSubnetClientsV5 \
  -v | tee "$log_file"
