#!/usr/bin/env bash
set -euo pipefail

remote_config="${REMOTE_CONFIG:-tests/dcetests.cfg}"
log_file="${LOG_FILE:-impacket-goad-core-$(date +%F-%H%M).log}"
strict="${STRICT:-0}"

if [[ ! -f "$remote_config" ]]; then
  echo "Remote config not found: $remote_config" >&2
  echo "Run this from the Impacket repository root or set REMOTE_CONFIG." >&2
  exit 2
fi

pytest_args=(
  -m remote
  --remote-config "$remote_config"
  --ignore=tests/SMB_RPC/test_smb.py
  --ignore=tests/SMB_RPC/test_nmb.py
  --ignore=tests/SMB_RPC/test_rpch.py
  --ignore=tests/dcerpc/test_mimilib.py
  --deselect=tests/dcerpc/test_dhcpm.py::DHCPMTestsTCPTransport64::test_hDhcpEnumSubnetClientsV5
)

if [[ "$strict" != "1" ]]; then
  pytest_args+=(
    --deselect=tests/dcerpc/test_bkrp.py::BKRPTestsSMBTransport::test_BackuprKey_BACKUPKEY_RETRIEVE_BACKUP_KEY_GUID
    --deselect=tests/dcerpc/test_bkrp.py::BKRPTestsSMBTransport::test_hBackuprKey_BACKUPKEY_RETRIEVE_BACKUP_KEY_GUID
    --deselect=tests/dcerpc/test_bkrp.py::BKRPTestsSMBTransport64::test_BackuprKey_BACKUPKEY_RETRIEVE_BACKUP_KEY_GUID
    --deselect=tests/dcerpc/test_bkrp.py::BKRPTestsSMBTransport64::test_hBackuprKey_BACKUPKEY_RETRIEVE_BACKUP_KEY_GUID
    --deselect=tests/dcerpc/test_drsuapi.py::DRSRTestsSMBTransport::test_DRSBind
    --deselect=tests/dcerpc/test_drsuapi.py::DRSRTestsSMBTransport::test_DRSCrackNames
    --deselect=tests/dcerpc/test_drsuapi.py::DRSRTestsSMBTransport::test_DRSDomainControllerInfo
    --deselect=tests/dcerpc/test_drsuapi.py::DRSRTestsSMBTransport::test_DRSGetNT4ChangeLog
    --deselect=tests/dcerpc/test_drsuapi.py::DRSRTestsSMBTransport::test_DRSVerifyNames
    --deselect=tests/dcerpc/test_drsuapi.py::DRSRTestsSMBTransport::test_hDRSCrackNames
    --deselect=tests/dcerpc/test_drsuapi.py::DRSRTestsSMBTransport::test_hDRSDomainControllerInfo
    --deselect=tests/dcerpc/test_drsuapi.py::DRSRTestsSMBTransport64::test_DRSBind
    --deselect=tests/dcerpc/test_drsuapi.py::DRSRTestsSMBTransport64::test_DRSCrackNames
    --deselect=tests/dcerpc/test_drsuapi.py::DRSRTestsSMBTransport64::test_DRSDomainControllerInfo
    --deselect=tests/dcerpc/test_drsuapi.py::DRSRTestsSMBTransport64::test_DRSGetNT4ChangeLog
    --deselect=tests/dcerpc/test_drsuapi.py::DRSRTestsSMBTransport64::test_DRSVerifyNames
    --deselect=tests/dcerpc/test_drsuapi.py::DRSRTestsSMBTransport64::test_hDRSCrackNames
    --deselect=tests/dcerpc/test_drsuapi.py::DRSRTestsSMBTransport64::test_hDRSDomainControllerInfo
    --deselect=tests/dcerpc/test_even6.py::EVEN6TestsTCPTransport::test_hEvtRpcExportLog
    --deselect=tests/dcerpc/test_even6.py::EVEN6TestsTCPTransport64::test_hEvtRpcExportLog
    --deselect=tests/dcerpc/test_nrpc.py::NRPCTestsSMBTransport::test_NetrLogonSamLogonEx
    --deselect=tests/dcerpc/test_nrpc.py::NRPCTestsTCPTransport::test_DsrAddressToSiteNamesExW
    --deselect=tests/dcerpc/test_nrpc.py::NRPCTestsTCPTransport::test_DsrAddressToSiteNamesW
    --deselect=tests/dcerpc/test_nrpc.py::NRPCTestsTCPTransport::test_DsrGetDcName
    --deselect=tests/dcerpc/test_nrpc.py::NRPCTestsTCPTransport::test_DsrGetDcNameEx
    --deselect=tests/dcerpc/test_nrpc.py::NRPCTestsTCPTransport::test_DsrGetDcNameEx2
    --deselect=tests/dcerpc/test_nrpc.py::NRPCTestsTCPTransport::test_DsrGetDcSiteCoverageW
    --deselect=tests/dcerpc/test_nrpc.py::NRPCTestsTCPTransport::test_DsrGetSiteName
    --deselect=tests/dcerpc/test_nrpc.py::NRPCTestsTCPTransport::test_NetrGetAnyDCName
    --deselect=tests/dcerpc/test_nrpc.py::NRPCTestsTCPTransport::test_NetrGetDCName
    --deselect=tests/dcerpc/test_nrpc.py::NRPCTestsTCPTransport::test_NetrLogonSamLogonEx
    --deselect=tests/dcerpc/test_nrpc.py::NRPCTestsTCPTransport::test_hDsrAddressToSiteNamesW
    --deselect=tests/dcerpc/test_nrpc.py::NRPCTestsTCPTransport::test_hDsrGetDcName
    --deselect=tests/dcerpc/test_nrpc.py::NRPCTestsTCPTransport::test_hDsrGetDcNameEx
    --deselect=tests/dcerpc/test_nrpc.py::NRPCTestsTCPTransport::test_hDsrGetDcNameEx2
    --deselect=tests/dcerpc/test_nrpc.py::NRPCTestsTCPTransport::test_hDsrGetDcSiteCoverageW
    --deselect=tests/dcerpc/test_nrpc.py::NRPCTestsTCPTransport::test_hDsrGetSiteName
    --deselect=tests/dcerpc/test_nrpc.py::NRPCTestsTCPTransport::test_hNetrGetAnyDCName
    --deselect=tests/dcerpc/test_nrpc.py::NRPCTestsTCPTransport::test_hNetrGetDCName
    --deselect=tests/dcerpc/test_rrp.py::RRPTestsSMBTransport::test_BaseRegQueryMultipleValues
    --deselect=tests/dcerpc/test_rrp.py::RRPTestsSMBTransport::test_BaseRegQueryMultipleValues2
    --deselect=tests/dcerpc/test_rrp.py::RRPTestsSMBTransport64::test_BaseRegQueryMultipleValues
    --deselect=tests/dcerpc/test_rrp.py::RRPTestsSMBTransport64::test_BaseRegQueryMultipleValues2
    --deselect=tests/dcerpc/test_srvs.py::SRVSTestsSMBTransport::test_NetrServerStatisticsGet
    --deselect=tests/dcerpc/test_srvs.py::SRVSTestsSMBTransport::test_hNetrServerStatisticsGet
    --deselect=tests/dcerpc/test_srvs.py::SRVSTestsSMBTransport64::test_NetrServerStatisticsGet
    --deselect=tests/dcerpc/test_srvs.py::SRVSTestsSMBTransport64::test_hNetrServerStatisticsGet
    --deselect=tests/dcerpc/test_tsch.py::SASECTestsSMBTransport::test_SAGetNSAccountInformation
    --deselect=tests/dcerpc/test_tsch.py::SASECTestsSMBTransport::test_hSAGetNSAccountInformation
    --deselect=tests/dcerpc/test_tsch.py::SASECTestsSMBTransport64::test_SAGetNSAccountInformation
    --deselect=tests/dcerpc/test_tsch.py::SASECTestsSMBTransport64::test_hSAGetNSAccountInformation
  )
fi

python -m pytest "${pytest_args[@]}" -v | tee "$log_file"
