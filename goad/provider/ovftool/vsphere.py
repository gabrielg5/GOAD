import json
import getpass
import os
import shlex
import ipaddress
import re
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import quote

from goad.provider.provider import Provider
from goad.log import Log
from goad.utils import *
from goad.ip_range import IpRange, IpRangeError


class VsphereProvider(Provider):
    provider_name = VSPHERE
    default_provisioner = PROVISIONING_LOCAL
    allowed_provisioners = [PROVISIONING_LOCAL, PROVISIONING_RUNNER, PROVISIONING_DOCKER]

    def __init__(self, lab_name, config):
        super().__init__(lab_name)
        self.server = config.get_value('vsphere', 'vsphere_server', config.get_value('vmware_esxi', 'esxi_hostname', ''))
        self.username = config.get_value('vsphere', 'vsphere_user', config.get_value('vmware_esxi', 'esxi_username', ''))
        self.password = config.get_value('vsphere', 'vsphere_password', config.get_value('vmware_esxi', 'esxi_password', ''))
        self.datastore = config.get_value('vsphere', 'vsphere_datastore', config.get_value('vmware_esxi', 'esxi_datastore', ''))
        self.network = config.get_value('vsphere', 'vsphere_network', config.get_value('vmware_esxi', 'esxi_net_domain', ''))
        self.ovftool_target = config.get_value('vsphere', 'vsphere_ovftool_target', '')
        self.vm_folder = config.get_value('vsphere', 'vsphere_folder', '')
        self.resource_pool = config.get_value('vsphere', 'vsphere_resource_pool', '')
        self.disk_mode = config.get_value('vsphere', 'vsphere_disk_mode', 'thin')
        self.no_ssl_verify = config.get_value('vsphere', 'vsphere_allow_unverified_ssl', 'true').lower() == 'true'
        self.overwrite = config.get_value('vsphere', 'vsphere_overwrite', 'false').lower() == 'true'
        self.box_provider = config.get_value('vsphere', 'vsphere_box_provider', 'vmware_desktop')
        self.vm_name_prefix = config.get_value('vsphere', 'vsphere_vm_name_prefix', '')
        self.ovftool_bin = config.get_value('vsphere', 'vsphere_ovftool_bin', 'ovftool')
        self.govc_bin = config.get_value('vsphere', 'vsphere_govc_bin', 'govc')
        self.network_adapter = config.get_value('vsphere', 'vsphere_network_adapter', 'e1000')
        self.bootstrap_guest_network = config.get_value('vsphere', 'vsphere_bootstrap_guest_network', 'true').lower() == 'true'
        self.guest_username = config.get_value('vsphere', 'vsphere_guest_username', 'vagrant')
        self.guest_password = config.get_value('vsphere', 'vsphere_guest_password', 'vagrant')
        self.guest_username_path = config.get_value('vsphere', 'vsphere_guest_username_path', '')
        self.guest_password_path = config.get_value('vsphere', 'vsphere_guest_password_path', '')
        self.ipv4_prefix_length = config.get_value('vsphere', 'vsphere_ipv4_prefix_length', '')
        self.ipv4_gateway = config.get_value('vsphere', 'vsphere_ipv4_gateway', '')
        self.dns_server = config.get_value('vsphere', 'vsphere_dns_server', '')
        self._secret_values = set()
        self._credential_file_cache = {}
        self._add_secret(self.password)
        self._add_secret(self.guest_password)
        self.guest_operations_timeout = self._int_value(
            config.get_value('vsphere', 'vsphere_guest_operations_timeout', '1800'),
            1800
        )
        self.guest_operations_delay = self._int_value(
            config.get_value('vsphere', 'vsphere_guest_operations_delay', '10'),
            10
        )
        self.network_bootstrap_timeout = self._int_value(
            config.get_value('vsphere', 'vsphere_network_bootstrap_timeout', '600'),
            600
        )

    def check(self):
        checks = [
            self.command.check_vagrant(),
            self.command.check_ovftool(),
            self.command.check_govc(),
            self.command.check_ansible()
        ]
        return all(checks)

    @staticmethod
    def _url_quote(value):
        return quote(value, safe='')

    @staticmethod
    def _int_value(value, default):
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return default

    def _add_secret(self, value):
        if value is None:
            return
        value = str(value)
        if value:
            self._secret_values.add(value)

    def _password_needs_prompt(self):
        if self.password is None:
            return True
        return self.password.strip() == '' or self.password == 'password'

    def _ensure_password(self):
        if not self._password_needs_prompt():
            return self.password

        env_password = os.environ.get('VSPHERE_PASSWORD') or os.environ.get('GOVC_PASSWORD')
        if env_password:
            self.password = env_password
            self._add_secret(self.password)
            return self.password

        self.password = getpass.getpass(f'Enter vSphere password for {self.username}@{self.server}: ')
        self._add_secret(self.password)
        return self.password

    @staticmethod
    def _sanitize_vi_locator(value):
        if not value.startswith('vi://'):
            return value

        body = value[len('vi://'):]
        authority, separator, path = body.partition('/')
        if '@' not in authority:
            return value

        host = authority.rsplit('@', 1)[1]
        return f'vi://***@{host}{separator}{path}'

    def _sanitize_command(self, command):
        sanitized = []
        for arg in command:
            for secret in self._secret_values:
                arg = arg.replace(secret, '***')
                arg = arg.replace(self._url_quote(secret), '***')
            if self.username:
                arg = arg.replace(self._url_quote(self.username), '***')
            arg = self._sanitize_vi_locator(arg)
            sanitized.append(arg)
        return sanitized

    def _log_command(self, command):
        sanitized = self._sanitize_command(command)
        Log.info('CWD: ' + Utils.get_relative_path(str(self.path)))
        Log.cmd(' '.join(shlex.quote(arg) for arg in sanitized))

    def _run(self, command, env=None):
        self._log_command(command)
        result = subprocess.run(command, cwd=self.path, env=env)
        return result.returncode == 0

    def _capture(self, command, env=None):
        self._log_command(command)
        result = subprocess.run(command, cwd=self.path, env=env, capture_output=True, text=True)
        if result.returncode != 0:
            if result.stdout:
                Log.basic(result.stdout.strip())
            if result.stderr:
                Log.error(result.stderr.strip())
            return None
        return result.stdout

    def _govc_env(self):
        password = self._ensure_password()
        env = os.environ.copy()
        env['GOVC_URL'] = self.server
        env['GOVC_USERNAME'] = self.username
        env['GOVC_PASSWORD'] = password
        env['GOVC_INSECURE'] = '1' if self.no_ssl_verify else '0'
        if self.datastore:
            env['GOVC_DATASTORE'] = self.datastore
        if self.network:
            env['GOVC_NETWORK'] = self.network
        if self.resource_pool:
            env['GOVC_RESOURCE_POOL'] = self.resource_pool
        if self.vm_folder:
            env['GOVC_FOLDER'] = self.vm_folder
        return env

    def _run_govc(self, args):
        return self._run([self.govc_bin] + args, self._govc_env())

    def _capture_govc(self, args):
        return self._capture([self.govc_bin] + args, self._govc_env())

    def _run_govc_retry(self, args, tries=30, delay=10):
        for attempt in range(1, tries + 1):
            if self._run_govc(args):
                return True
            if attempt < tries:
                Log.info(f'govc command failed, retry in {delay}s ({attempt}/{tries})')
                time.sleep(delay)
        return False

    def _vm_exists(self, vm_name):
        command = [self.govc_bin, 'vm.info', vm_name]
        self._log_command(command)
        result = subprocess.run(
            command,
            cwd=self.path,
            env=self._govc_env(),
            capture_output=True,
            text=True
        )
        return result.returncode == 0

    def _run_govc_guest_retry(self, args, timeout=None, delay=None):
        timeout = self.guest_operations_timeout if timeout is None else timeout
        delay = self.guest_operations_delay if delay is None else delay
        deadline = time.time() + timeout
        attempt = 0
        last_output = ''

        self._log_command([self.govc_bin] + args)
        while True:
            result = subprocess.run(
                [self.govc_bin] + args,
                cwd=self.path,
                env=self._govc_env(),
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                return True

            last_output = '\n'.join(
                output.strip()
                for output in (result.stdout, result.stderr)
                if output and output.strip()
            )
            lower_output = last_output.lower()
            if any(error in lower_output for error in (
                'cannot complete login',
                'incorrect user name or password',
                'authentication failed'
            )):
                Log.error(last_output)
                return False

            if time.time() >= deadline:
                break

            attempt += 1
            if attempt == 1 or attempt % 6 == 0:
                Log.info(f'VMware Tools guest operations are not ready yet; retry in {delay}s')
            time.sleep(delay)

        Log.error(f'VMware Tools guest operations did not become ready after {timeout}s')
        if last_output:
            Log.error(last_output)
        return False

    def _instance_id(self):
        return Path(self.path).parent.name

    def _vm_prefix(self):
        if self.vm_name_prefix:
            return self.vm_name_prefix
        return self._instance_id()

    def _vm_name(self, box):
        return f'{self._vm_prefix()}-{box["name"]}'

    def _target_url(self):
        password = self._ensure_password()
        if self.ovftool_target:
            if self.ovftool_target.startswith('vi://'):
                return self.ovftool_target
            target = self.ovftool_target.strip('/')
            return f'vi://{self._url_quote(self.username)}:{self._url_quote(password)}@{self.server}/{target}'
        return f'vi://{self._url_quote(self.username)}:{self._url_quote(password)}@{self.server}/'

    @staticmethod
    def _range_from_ip(ip):
        parts = ip.split('.')
        if len(parts) == 4:
            return '.'.join(parts[:3])
        return ''

    def _instance_ip_plan(self):
        instance_file = Path(self.path).parent / 'instance.json'
        if not instance_file.is_file():
            return None
        try:
            with open(instance_file, 'r') as instance_info_openfile:
                instance_info = json.load(instance_info_openfile)
            return IpRange(instance_info['ip_range'])
        except (KeyError, OSError, json.JSONDecodeError, IpRangeError):
            return None

    def _prefix_length(self):
        ip_plan = self._instance_ip_plan()
        if ip_plan is not None and '/' in str(ip_plan.raw_value):
            return ip_plan.prefixlen
        if str(self.ipv4_prefix_length).strip():
            return int(self.ipv4_prefix_length)
        if ip_plan is not None:
            return ip_plan.prefixlen
        return 24

    def _gateway_for_box(self, box):
        if self.ipv4_gateway:
            return self.ipv4_gateway
        ip_plan = self._instance_ip_plan()
        if ip_plan is not None:
            return ip_plan.gateway
        ip_range = self._range_from_ip(box['ip'])
        if ip_range:
            return ip_range + '.1'
        return ''

    def _dns_for_box(self, box):
        if self.dns_server:
            return self.dns_server
        return self._gateway_for_box(box)

    @staticmethod
    def _first_configured_value(*values):
        for value in values:
            if value is None:
                continue
            value = str(value).strip()
            if value:
                return value
        return ''

    def _read_guest_credential_file(self, path, label):
        resolved_path = os.path.expandvars(os.path.expanduser(path))
        if resolved_path in self._credential_file_cache:
            return self._credential_file_cache[resolved_path]
        if not os.path.isfile(resolved_path):
            Log.error(f'{label} file not found: {resolved_path}')
            self._credential_file_cache[resolved_path] = None
            return None
        try:
            with open(resolved_path, 'r', encoding='utf-8') as credential_file:
                value = credential_file.read().strip()
                self._credential_file_cache[resolved_path] = value
                return value
        except OSError as exc:
            Log.error(f'Unable to read {label} file {resolved_path}: {exc}')
            self._credential_file_cache[resolved_path] = None
            return None

    def _guest_value(self, box, key, default_value, default_path):
        if box is None:
            box = {}
        path = self._first_configured_value(
            box.get(f'{key}_path'),
            box.get(f'{key}_file'),
            default_path
        )
        if path:
            value = self._read_guest_credential_file(path, key)
            if value is None:
                return None
        else:
            value = self._first_configured_value(box.get(key), default_value)

        if key == 'guest_password':
            self._add_secret(value)
        return value

    def _guest_login(self, box=None):
        username = self._guest_value(box, 'guest_username', self.guest_username, self.guest_username_path)
        password = self._guest_value(box, 'guest_password', self.guest_password, self.guest_password_path)
        if not username or not password:
            vm_name = box.get('name') if box else 'guest'
            Log.error(f'Missing guest bootstrap credentials for {vm_name}')
            return None
        return f'{username}:{password}'

    @staticmethod
    def _netmask_from_prefix(prefix_length):
        return str(ipaddress.IPv4Network(f'0.0.0.0/{prefix_length}').netmask)

    @staticmethod
    def _windows_network_script(ip_address, prefix_length, gateway, dns_server):
        return r'''
$ErrorActionPreference = "Stop"
$ipAddress = "__IP_ADDRESS__"
$prefixLength = __PREFIX_LENGTH__
$netmask = "__NETMASK__"
$gateway = "__GATEWAY__"
$dnsServer = "__DNS_SERVER__"

$adapter = $null
for ($attempt = 0; $attempt -lt 60; $attempt++) {
    $adapter = Get-NetAdapter |
        Where-Object { $_.Status -eq "Up" -and $_.Name -notlike "*Loopback*" } |
        Sort-Object -Property ifIndex |
        Select-Object -First 1
    if ($adapter) {
        break
    }
    Start-Sleep -Seconds 5
}

if (-not $adapter) {
    throw "No connected network adapter found"
}

Write-Output "Configure IPv4 on $($adapter.Name) with netsh"
& netsh.exe interface ipv4 set address name="$($adapter.Name)" static $ipAddress $netmask $gateway 1
if ($LASTEXITCODE -ne 0) {
    throw "netsh address configuration failed with exit code $LASTEXITCODE"
}
& netsh.exe interface ipv4 set dnsservers name="$($adapter.Name)" static $dnsServer primary
if ($LASTEXITCODE -ne 0) {
    throw "netsh DNS configuration failed with exit code $LASTEXITCODE"
}

$assigned = $false
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    $assignedAddress = Get-NetIPAddress -InterfaceIndex $adapter.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -eq $ipAddress } |
        Select-Object -First 1
    if ($assignedAddress) {
        $assigned = $true
        break
    }
    Start-Sleep -Seconds 2
}

if (-not $assigned) {
    throw "Static IPv4 address $ipAddress was not assigned"
}
'''.replace('__IP_ADDRESS__', ip_address) \
            .replace('__PREFIX_LENGTH__', str(prefix_length)) \
            .replace('__NETMASK__', VsphereProvider._netmask_from_prefix(prefix_length)) \
            .replace('__GATEWAY__', gateway) \
            .replace('__DNS_SERVER__', dns_server)

    def _start_guest_program(self, vm_name, program, args=None, tries=None, delay=None, box=None):
        if args is None:
            args = []
        guest_login = self._guest_login(box)
        if guest_login is None:
            return False
        command = [
            'guest.start',
            '-vm', vm_name,
            '-l', guest_login,
            program,
        ] + args
        if tries is not None:
            return self._run_govc_retry(command, tries=tries, delay=delay or 10)
        return self._run_govc_guest_retry(command, delay=delay)

    def _upload_file_to_guest(self, vm_name, local_path, remote_path, tries=None, delay=None, box=None):
        guest_login = self._guest_login(box)
        if guest_login is None:
            return False
        command = [
            'guest.upload',
            '-vm', vm_name,
            '-l', guest_login,
            local_path,
            remote_path
        ]
        if tries is not None:
            return self._run_govc_retry(command, tries=tries, delay=delay or 10)
        return self._run_govc_guest_retry(command, delay=delay)

    def _wait_for_guest_operations(self, vm_name, probe_path, box=None):
        guest_login = self._guest_login(box)
        if guest_login is None:
            return False
        Log.info(f'Wait for VMware Tools guest operations on {vm_name}')
        return self._run_govc_guest_retry([
            'guest.ls',
            '-vm', vm_name,
            '-l', guest_login,
            probe_path
        ])

    def _download_guest_file_silent(self, vm_name, remote_path, local_path, box=None):
        guest_login = self._guest_login(box)
        if guest_login is None:
            return False
        result = subprocess.run(
            [
                self.govc_bin,
                'guest.download',
                '-f',
                '-vm', vm_name,
                '-l', guest_login,
                remote_path,
                local_path
            ],
            cwd=self.path,
            env=self._govc_env(),
            capture_output=True,
            text=True
        )
        return result.returncode == 0

    @staticmethod
    def _powershell_quote(value):
        return "'" + str(value).replace("'", "''") + "'"

    def _upload_and_start_windows_script(self, vm_name, script_content, remote_script, box=None):
        local_script = None
        try:
            with tempfile.NamedTemporaryFile('w', suffix='.ps1', delete=False, encoding='utf-8') as script_file:
                script_file.write(script_content)
                local_script = script_file.name

            if not self._upload_file_to_guest(vm_name, local_script, remote_script, box=box):
                return False

            return self._start_guest_program(
                vm_name,
                'C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe',
                [
                    '-NoProfile',
                    '-ExecutionPolicy', 'Bypass',
                    '-File', remote_script
                ],
                box=box
            )
        finally:
            if local_script and os.path.isfile(local_script):
                os.unlink(local_script)

    def _upload_start_and_wait_windows_script(self, vm_name, script_content, remote_script, task_name, timeout=900, box=None):
        run_id = uuid.uuid4().hex
        remote_wrapper_script = f'C:\\Windows\\Temp\\GOAD-{task_name}-{run_id}.ps1'
        success_marker = f'C:\\Windows\\Temp\\GOAD-{task_name}-{run_id}.done'
        error_marker = f'C:\\Windows\\Temp\\GOAD-{task_name}-{run_id}.err'
        log_file = f'C:\\Windows\\Temp\\GOAD-{task_name}-{run_id}.log'
        wrapper_content = f'''
$ErrorActionPreference = "Stop"
$script = {self._powershell_quote(remote_script)}
$successMarker = {self._powershell_quote(success_marker)}
$errorMarker = {self._powershell_quote(error_marker)}
$logFile = {self._powershell_quote(log_file)}

Remove-Item -LiteralPath $successMarker -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $errorMarker -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $logFile -Force -ErrorAction SilentlyContinue

try {{
    & $script 4>&1 3>&1 2>&1 | Out-File -LiteralPath $logFile -Encoding UTF8
    "ok" | Set-Content -LiteralPath $successMarker -Encoding ASCII
}} catch {{
    $_ | Out-String | Set-Content -LiteralPath $errorMarker -Encoding UTF8
    if (Test-Path -LiteralPath $logFile) {{
        Get-Content -LiteralPath $logFile | Add-Content -LiteralPath $errorMarker
    }}
}}
'''
        local_script = None
        local_wrapper_script = None
        try:
            with tempfile.NamedTemporaryFile('w', suffix='.ps1', delete=False, encoding='utf-8') as script_file:
                script_file.write(script_content)
                local_script = script_file.name
            with tempfile.NamedTemporaryFile('w', suffix='.ps1', delete=False, encoding='utf-8') as wrapper_file:
                wrapper_file.write(wrapper_content)
                local_wrapper_script = wrapper_file.name

            if not self._upload_file_to_guest(vm_name, local_script, remote_script, box=box):
                return False
            if not self._upload_file_to_guest(vm_name, local_wrapper_script, remote_wrapper_script, box=box):
                return False
            if not self._start_guest_program(
                vm_name,
                'C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe',
                [
                    '-NoProfile',
                    '-ExecutionPolicy', 'Bypass',
                    '-File', remote_wrapper_script
                ],
                box=box
            ):
                return False
            return self._wait_for_guest_marker(vm_name, success_marker, error_marker, timeout=timeout, box=box)
        finally:
            for script_file in (local_script, local_wrapper_script):
                if script_file and os.path.isfile(script_file):
                    os.unlink(script_file)

    @staticmethod
    def _ipv4_addresses(output):
        if not output:
            return []
        seen = set()
        addresses = []
        for address in re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', output):
            if address not in seen:
                seen.add(address)
                addresses.append(address)
        return addresses

    def _wait_for_guest_ip(self, vm_name, expected_ip, tries=30, delay=10):
        Log.info(f'Wait for {vm_name} to report {expected_ip}')
        last_addresses = []
        for attempt in range(1, tries + 1):
            output = self._capture_govc(['vm.ip', '-a', '-v4', '-wait', '20s', vm_name])
            addresses = self._ipv4_addresses(output)
            if addresses:
                last_addresses = addresses
            if expected_ip in addresses:
                Log.success(f'{vm_name} reported {expected_ip}')
                return True
            if attempt < tries:
                reported = ', '.join(last_addresses) if last_addresses else 'no IPv4 address'
                Log.info(f'{vm_name} reports {reported}; retry in {delay}s ({attempt}/{tries})')
                time.sleep(delay)

        reported = ', '.join(last_addresses) if last_addresses else 'no IPv4 address'
        Log.error(f'{vm_name} did not report expected IP {expected_ip}; last reported: {reported}')
        return False

    def _wait_for_guest_marker(self, vm_name, success_marker, error_marker, timeout=900, delay=10, box=None):
        Log.info(f'Wait for guest-side bootstrap on {vm_name}')
        deadline = time.time() + timeout
        success_file = None
        error_file = None
        attempt = 0
        try:
            with tempfile.NamedTemporaryFile(delete=False) as marker_file:
                success_file = marker_file.name
            with tempfile.NamedTemporaryFile(delete=False) as marker_file:
                error_file = marker_file.name

            while time.time() < deadline:
                attempt += 1
                if self._download_guest_file_silent(vm_name, success_marker, success_file, box=box):
                    Log.success(f'Guest-side bootstrap completed on {vm_name}')
                    return True
                if self._download_guest_file_silent(vm_name, error_marker, error_file, box=box):
                    with open(error_file, 'r', encoding='utf-8', errors='replace') as error_openfile:
                        error_text = error_openfile.read().strip()
                    Log.error(f'Guest-side bootstrap failed on {vm_name}: {error_text}')
                    return False
                if attempt == 1 or attempt % 6 == 0:
                    Log.info(f'Guest-side bootstrap still running on {vm_name}')
                time.sleep(delay)
        finally:
            for marker_file in (success_file, error_file):
                if marker_file and os.path.isfile(marker_file):
                    os.unlink(marker_file)

        Log.error(f'Guest-side bootstrap timed out on {vm_name}')
        return False

    def _start_windows_netsh_fallback(self, vm_name, box):
        gateway = self._gateway_for_box(box)
        dns_server = self._dns_for_box(box)
        netmask = self._netmask_from_prefix(self._prefix_length())
        command = (
            'for /f "skip=3 tokens=1,2,3,*" %a in ('
            "'netsh interface show interface'"
            ') do if /I "%b"=="Connected" ('
            f'netsh interface ipv4 set address name="%d" static {box["ip"]} {netmask} {gateway} 1 && '
            f'netsh interface ipv4 set dnsservers name="%d" static {dns_server} primary && '
            'exit /b 0'
            ') & exit /b 1'
        )
        Log.info(f'Try netsh IP bootstrap for {vm_name}')
        return self._start_guest_program(
            vm_name,
            'C:\\Windows\\System32\\cmd.exe',
            ['/c', command],
            box=box
        )

    def _start_windows_remoting(self, vm_name, box=None):
        configure_script = Path(project_path) / 'vagrant' / 'ConfigureRemotingForAnsible.ps1'
        remote_configure_script = 'C:\\Windows\\Temp\\ConfigureRemotingForAnsible.ps1'
        run_id = uuid.uuid4().hex
        remote_wrapper_script = f'C:\\Windows\\Temp\\GOAD-ConfigureRemoting-{run_id}.ps1'
        success_marker = f'C:\\Windows\\Temp\\GOAD-ConfigureRemoting-{run_id}.done'
        error_marker = f'C:\\Windows\\Temp\\GOAD-ConfigureRemoting-{run_id}.err'
        log_file = f'C:\\Windows\\Temp\\GOAD-ConfigureRemoting-{run_id}.log'
        wrapper_content = f'''
$ErrorActionPreference = "Stop"
$script = {self._powershell_quote(remote_configure_script)}
$successMarker = {self._powershell_quote(success_marker)}
$errorMarker = {self._powershell_quote(error_marker)}
$logFile = {self._powershell_quote(log_file)}

Remove-Item -LiteralPath $successMarker -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $errorMarker -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $logFile -Force -ErrorAction SilentlyContinue

try {{
    & $script -SkipNetworkProfileCheck -Verbose 4>&1 3>&1 2>&1 |
        Out-File -LiteralPath $logFile -Encoding UTF8

    $service = Get-Service -Name WinRM -ErrorAction Stop
    if ($service.Status -ne "Running") {{
        throw "WinRM service status is $($service.Status)"
    }}

    $listeners = winrm enumerate winrm/config/listener
    if (-not ($listeners | Select-String -Pattern "Transport = HTTPS")) {{
        throw "WinRM HTTPS listener is missing"
    }}

    $listening = netstat -ano | Select-String -Pattern "(:5986\\s+.*LISTENING)"
    if (-not $listening) {{
        throw "WinRM HTTPS port 5986 is not listening inside the guest"
    }}

    $sessionOptions = New-PSSessionOption -SkipCACheck -SkipCNCheck -SkipRevocationCheck
    $session = New-PSSession -UseSSL -ComputerName localhost -SessionOption $sessionOptions -ErrorAction Stop
    if ($session) {{
        Remove-PSSession $session
    }}

    "ok" | Set-Content -LiteralPath $successMarker -Encoding ASCII
}} catch {{
    $_ | Out-String | Set-Content -LiteralPath $errorMarker -Encoding UTF8
    if (Test-Path -LiteralPath $logFile) {{
        Get-Content -LiteralPath $logFile | Add-Content -LiteralPath $errorMarker
    }}
}}
'''
        local_wrapper_script = None
        try:
            with tempfile.NamedTemporaryFile('w', suffix='.ps1', delete=False, encoding='utf-8') as script_file:
                script_file.write(wrapper_content)
                local_wrapper_script = script_file.name

            if not self._upload_file_to_guest(vm_name, str(configure_script), remote_configure_script, box=box):
                return False
            if not self._upload_file_to_guest(vm_name, local_wrapper_script, remote_wrapper_script, box=box):
                return False

            if not self._start_guest_program(
                vm_name,
                'C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe',
                [
                    '-NoProfile',
                    '-ExecutionPolicy', 'Bypass',
                    '-File', remote_wrapper_script
                ],
                box=box
            ):
                return False

            return self._wait_for_guest_marker(vm_name, success_marker, error_marker, box=box)
        finally:
            if local_wrapper_script and os.path.isfile(local_wrapper_script):
                os.unlink(local_wrapper_script)

    def _bootstrap_windows_guest(self, vm_name, box):
        gateway = self._gateway_for_box(box)
        dns_server = self._dns_for_box(box)
        prefix_length = self._prefix_length()

        if self._start_windows_netsh_fallback(vm_name, box):
            if self._wait_for_guest_ip(vm_name, box['ip']):
                if not self._start_windows_remoting(vm_name, box=box):
                    return False
                return True
            Log.warning(f'{vm_name} kept an APIPA or unexpected IP after netsh bootstrap')
        else:
            Log.warning(f'netsh IP bootstrap did not start for {vm_name}')

        network_script = self._windows_network_script(
            box['ip'],
            prefix_length,
            gateway,
            dns_server
        )
        if not self._upload_start_and_wait_windows_script(
            vm_name,
            network_script,
            'C:\\Windows\\Temp\\GOAD-BootstrapNetwork.ps1',
            'BootstrapNetwork',
            timeout=self.network_bootstrap_timeout,
            box=box
        ):
            return False

        if not self._wait_for_guest_ip(vm_name, box['ip']):
            return False

        if not self._start_windows_remoting(vm_name, box=box):
            return False
        return True

    def _bootstrap_linux_guest(self, vm_name, box):
        gateway = self._gateway_for_box(box)
        dns_server = self._dns_for_box(box)
        prefix_length = self._prefix_length()
        script = (
            "set -e; "
            "iface=$(ip -o link show | awk -F': ' '$2 != \"lo\" {print $2; exit}'); "
            f"sudo ip addr flush dev \"$iface\"; "
            f"sudo ip addr add {box['ip']}/{prefix_length} dev \"$iface\"; "
            "sudo ip link set \"$iface\" up; "
            f"sudo ip route replace default via {gateway}; "
            f"echo nameserver {dns_server} | sudo tee /etc/resolv.conf >/dev/null"
        )
        if not self._start_guest_program(vm_name, '/bin/bash', ['-lc', script], tries=30, delay=10, box=box):
            return False

        return self._wait_for_guest_ip(vm_name, box['ip'])

    def _bootstrap_guest(self, vm_name, box):
        if not self.bootstrap_guest_network:
            return True
        os_name = box.get('os', '').lower()
        Log.info(f'Bootstrap guest network for {vm_name} ({box["ip"]}/{self._prefix_length()})')
        if os_name == 'windows':
            if not self._wait_for_guest_operations(vm_name, 'C:\\Windows\\Temp', box=box):
                return False
            return self._bootstrap_windows_guest(vm_name, box)
        if not self._wait_for_guest_operations(vm_name, '/tmp', box=box):
            return False
        return self._bootstrap_linux_guest(vm_name, box)

    def _network_devices(self, vm_name):
        output = self._capture_govc(['device.ls', '-vm', vm_name])
        if output is None:
            return []

        devices = []
        for line in output.splitlines():
            fields = line.split()
            if not fields:
                continue
            device = fields[0]
            if device.lower().startswith('ethernet-') and device not in devices:
                devices.append(device)
        return devices

    def _add_network_device(self, vm_name):
        if not self.network:
            Log.error(f'No ethernet devices found on {vm_name} and vsphere_network is empty')
            return False

        Log.info(f'Add network adapter to {vm_name} on {self.network}')
        args = ['vm.network.add', '-vm', vm_name, '-net', self.network]
        if self.network_adapter:
            args += ['-net.adapter', self.network_adapter]
        return self._run_govc(args)

    def _connect_network_devices(self, vm_name):
        devices = self._network_devices(vm_name)
        if not devices:
            Log.warning(f'No ethernet devices found on {vm_name}; creating one')
            if not self._add_network_device(vm_name):
                return False
            devices = self._network_devices(vm_name)
            if not devices:
                Log.error(f'No ethernet devices found on {vm_name} after adding one')
                return False

        result = True
        for device in devices:
            if self.network:
                Log.info(f'Set {vm_name} {device} network to {self.network}')
                result = self._run_govc(['vm.network.change', '-vm', vm_name, '-net', self.network, device]) and result
            Log.info(f'Connect {vm_name} {device}')
            result = self._run_govc(['device.connect', '-vm', vm_name, device]) and result
        return result

    def _get_boxes(self):
        boxes_file = Path(self.path) / 'boxes.json'
        if not boxes_file.is_file():
            Log.error(f'boxes manifest not found: {boxes_file}')
            return []
        with open(boxes_file, 'r') as box_file:
            return json.load(box_file)

    def _vagrant_box_root(self, box):
        box_root_name = box['box'].replace('/', '-VAGRANTSLASH-')
        return Path.home() / '.vagrant.d' / 'boxes' / box_root_name

    def _find_box_provider_dir(self, box):
        box_root = self._vagrant_box_root(box)
        version = str(box.get('box_version', '')).strip()
        candidates = []
        if version:
            candidates.append(box_root / version / self.box_provider)
        if box_root.is_dir():
            for provider_dir in box_root.glob(f'*/{self.box_provider}'):
                candidates.append(provider_dir)
            for provider_dir in box_root.glob('*/vmware*'):
                candidates.append(provider_dir)

        for candidate in candidates:
            if candidate.is_dir():
                return candidate
        return None

    def _ensure_box(self, box):
        provider_dir = self._find_box_provider_dir(box)
        if provider_dir is not None:
            return provider_dir

        command = [self.command.vagrant_bin, 'box', 'add', box['box'], '--provider', self.box_provider]
        if box.get('box_version'):
            command += ['--box-version', str(box['box_version'])]
        if not self._run(command):
            return None
        return self._find_box_provider_dir(box)

    @staticmethod
    def _find_box_source(provider_dir):
        for extension in ('*.ovf', '*.ova', '*.vmx'):
            matches = list(provider_dir.rglob(extension))
            if matches:
                return matches[0]
        return None

    def _deploy_box(self, box):
        vm_name = self._vm_name(box)
        if self._vm_exists(vm_name) and not self.overwrite:
            Log.info(f'Skip existing VM {vm_name}; remove this VM or use another vm_name_prefix to recreate it')
            return True

        provider_dir = self._ensure_box(box)
        if provider_dir is None:
            Log.error(f'Unable to find or download vagrant box {box["box"]}')
            return False

        source = self._find_box_source(provider_dir)
        if source is None:
            Log.error(f'No OVF/OVA/VMX source found in {provider_dir}')
            return False

        command = [
            self.ovftool_bin,
            '--acceptAllEulas',
            '--allowExtraConfig',
            f'--name={vm_name}',
            f'--datastore={self.datastore}',
            f'--diskMode={self.disk_mode}',
            f'--network={self.network}',
        ]
        if self.no_ssl_verify:
            command.append('--noSSLVerify')
        if self.overwrite:
            command += ['--overwrite', '--powerOffTarget']
        if self.vm_folder:
            command.append(f'--vmFolder={self.vm_folder}')
        command += [str(source), self._target_url()]

        if not self._run(command):
            return False

        if box.get('cpus') or box.get('mem'):
            args = ['vm.change', '-vm', vm_name]
            if box.get('cpus'):
                args += ['-c', str(box['cpus'])]
            if box.get('mem'):
                args += ['-m', str(box['mem'])]
            if not self._run_govc(args):
                return False

        if not self._connect_network_devices(vm_name):
            return False

        if not self._run_govc(['vm.power', '-on', vm_name]):
            return False
        if not self._connect_network_devices(vm_name):
            return False
        return self._bootstrap_guest(vm_name, box)

    def _deploy_template(self, box):
        template = str(box.get('template', '')).strip()
        if not template:
            Log.error(f'Missing vSphere template path for {box["name"]}')
            return False

        vm_name = self._vm_name(box)
        if self._vm_exists(vm_name) and not self.overwrite:
            Log.info(f'Skip existing VM {vm_name}; remove this VM or use another vm_name_prefix to recreate it')
            return True

        if self.overwrite:
            self._run_govc(['vm.power', '-off', vm_name])
            self._run_govc(['vm.destroy', vm_name])

        command = ['vm.clone', f'-vm={template}', '-on=false']
        if self.datastore:
            command.append(f'-ds={self.datastore}')
        if self.vm_folder:
            command.append(f'-folder={self.vm_folder}')
        if self.resource_pool:
            command.append(f'-pool={self.resource_pool}')
        if self.network:
            command.append(f'-net={self.network}')
        if self.network_adapter:
            command.append(f'-net.adapter={self.network_adapter}')
        if box.get('cpus'):
            command.append(f'-c={box["cpus"]}')
        if box.get('mem'):
            command.append(f'-m={box["mem"]}')
        if box.get('annotation'):
            command.append(f'-annotation={box["annotation"]}')
        command.append(vm_name)

        if not self._run_govc(command):
            return False

        if not self._connect_network_devices(vm_name):
            return False

        if not self._run_govc(['vm.power', '-on', vm_name]):
            return False
        if not self._connect_network_devices(vm_name):
            return False
        return self._bootstrap_guest(vm_name, box)

    @staticmethod
    def _box_source_label(box):
        return box.get('template') or box.get('box') or '<missing source>'

    def _deploy_vm(self, box):
        if box.get('template') is not None:
            return self._deploy_template(box)
        if box.get('box') is not None:
            return self._deploy_box(box)
        Log.error(f'Missing VM source for {box.get("name", "<unnamed>")}')
        return False

    def install(self):
        boxes = self._get_boxes()
        if not boxes:
            Log.error('No VM to deploy')
            return False
        if not self.ovftool_target:
            Log.warning(
                'vsphere_ovftool_target is empty; this only works when vsphere_server '
                'is a direct ESXi host. For vCenter, set the datacenter/host/cluster path.'
            )
        for box in boxes:
            Log.info(f'Deploy {box["name"]} from {self._box_source_label(box)}')
            if not self._deploy_vm(box):
                return False
        return True

    def destroy(self):
        result = True
        for box in self._get_boxes():
            vm_name = self._vm_name(box)
            self._run_govc(['vm.power', '-off', vm_name])
            result = self._run_govc(['vm.destroy', vm_name]) and result
        return result

    def start(self):
        result = True
        for box in self._get_boxes():
            result = self._run_govc(['vm.power', '-on', self._vm_name(box)]) and result
        return result

    def stop(self):
        result = True
        for box in self._get_boxes():
            result = self._run_govc(['vm.power', '-off', self._vm_name(box)]) and result
        return result

    def status(self):
        result = True
        for box in self._get_boxes():
            result = self._run_govc(['vm.info', self._vm_name(box)]) and result
        return result

    def start_vm(self, vm_name):
        return self._run_govc(['vm.power', '-on', vm_name])

    def stop_vm(self, vm_name):
        return self._run_govc(['vm.power', '-off', vm_name])

    def destroy_vm(self, vm_name):
        self.stop_vm(vm_name)
        return self._run_govc(['vm.destroy', vm_name])

    def get_jumpbox_ip(self, ip_range=''):
        return IpRange(ip_range).host(3)
