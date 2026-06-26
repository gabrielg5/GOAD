import ipaddress
import re


class IpRangeError(ValueError):
    pass


class IpRange:
    TEMPLATE_MARKER = '__GOAD_IP_RANGE__'
    _LEGACY_IP_RE = re.compile(
        re.escape(TEMPLATE_MARKER) + r'\.(?P<offset>\d+)(?:/(?P<prefix>\d+))?'
    )

    def __init__(self, value):
        self.raw_value = value
        self.network = self._parse_network(value)
        self._host_offset_map = {}
        self._allocated_offsets = set()
        self._legacy_subnets = []
        self.remapped_offsets = {}
        self._reserve_infrastructure_offsets()

    @classmethod
    def _parse_network(cls, value):
        if not isinstance(value, str):
            raise IpRangeError('IP range must be a string')

        value = value.strip()
        if not value:
            raise IpRangeError('IP range cannot be empty')

        try:
            if '/' in value:
                return ipaddress.IPv4Network(value, strict=False)

            parts = value.split('.')
            if len(parts) >= 3:
                first_three = [int(parts[i]) for i in range(3)]
                if all(0 <= part < 256 for part in first_three):
                    return ipaddress.IPv4Network(f'{parts[0]}.{parts[1]}.{parts[2]}.0/24')
        except (ipaddress.AddressValueError, ipaddress.NetmaskValueError, ValueError, IndexError):
            pass

        raise IpRangeError(f'Invalid IP range: {value}')

    @classmethod
    def normalize(cls, value):
        parsed = cls(value)
        if '/' not in value and parsed.network.prefixlen == 24:
            return parsed.legacy_prefix
        return parsed.cidr

    @classmethod
    def display(cls, value):
        return cls(value).cidr

    @property
    def cidr(self):
        return self.network.with_prefixlen

    @property
    def legacy_prefix(self):
        parts = str(self.network.network_address).split('.')
        return '.'.join(parts[:3])

    @property
    def prefixlen(self):
        return self.network.prefixlen

    @property
    def gateway(self):
        return self.host(1)

    def _usable_offsets(self):
        if self.network.prefixlen >= 31:
            return set(range(self.network.num_addresses))
        return set(range(1, self.network.num_addresses - 1))

    def _reserve_infrastructure_offsets(self):
        usable_offsets = self._usable_offsets()
        for offset in (1, 3):
            if offset in usable_offsets:
                self._allocated_offsets.add(offset)

    @staticmethod
    def _subnet_usable_offsets(network, reserved_offsets=None):
        if reserved_offsets is None:
            reserved_offsets = set()
        if network.prefixlen >= 31:
            usable_offsets = set(range(network.num_addresses))
        else:
            usable_offsets = set(range(1, network.num_addresses - 1))
        return usable_offsets - set(reserved_offsets)

    def _reserve_direct_offsets(self, offsets):
        usable_offsets = self._usable_offsets()
        for offset in offsets:
            if offset not in (1, 3) and any(
                legacy_subnet['old_start'] <= offset < legacy_subnet['old_end']
                for legacy_subnet in self._legacy_subnets
            ):
                continue
            if offset in usable_offsets:
                self._allocated_offsets.add(offset)

    def _next_free_offset(self):
        usable_offsets = self._usable_offsets()
        for offset in sorted(usable_offsets, reverse=True):
            if offset not in self._allocated_offsets:
                return offset
        raise IpRangeError(f'No usable IP left in {self.cidr}')

    def _subnet_network(self, offset, old_prefix):
        offset = int(offset)
        old_prefix = int(old_prefix)
        if old_prefix < 0 or old_prefix > 32:
            raise IpRangeError(f'Invalid prefix length: {old_prefix}')

        if old_prefix == 24:
            new_prefix = self.prefixlen
        else:
            new_prefix = max(old_prefix, self.prefixlen + 1)
            if new_prefix > 32:
                new_prefix = 32

        old_subnet_size = 2 ** (32 - old_prefix)
        subnet_index = offset // old_subnet_size
        subnets = list(self.network.subnets(new_prefix=new_prefix))
        if subnet_index >= len(subnets):
            raise IpRangeError(
                f'Legacy subnet offset .{offset}/{old_prefix} does not fit in {self.cidr}'
            )
        return subnets[subnet_index]

    def register_legacy_subnet(self, offset, old_prefix, reserved_offsets=None):
        old_subnet_size = 2 ** (32 - int(old_prefix))
        mapped_network = self._subnet_network(offset, old_prefix)
        self._legacy_subnets.append({
            'old_start': int(offset),
            'old_end': int(offset) + old_subnet_size,
            'mapped_network': mapped_network,
            'host_map': {},
            'allocated_offsets': set(),
            'reserved_offsets': set(reserved_offsets or []),
        })

    @staticmethod
    def _next_free_subnet_offset(legacy_subnet):
        usable_offsets = IpRange._subnet_usable_offsets(
            legacy_subnet['mapped_network'],
            legacy_subnet['reserved_offsets'],
        )
        for offset in sorted(usable_offsets, reverse=True):
            if offset not in legacy_subnet['allocated_offsets']:
                return offset
        raise IpRangeError(f'No usable IP left in {legacy_subnet["mapped_network"].with_prefixlen}')

    def _map_registered_subnet_offset(self, offset):
        if offset in (1, 3):
            return None

        for legacy_subnet in self._legacy_subnets:
            if not legacy_subnet['old_start'] <= offset < legacy_subnet['old_end']:
                continue

            if offset in legacy_subnet['host_map']:
                return legacy_subnet['host_map'][offset]

            relative_offset = offset - legacy_subnet['old_start']
            usable_offsets = self._subnet_usable_offsets(
                legacy_subnet['mapped_network'],
                legacy_subnet['reserved_offsets'],
            )
            if relative_offset in usable_offsets:
                mapped_offset = relative_offset
            else:
                mapped_offset = self._next_free_subnet_offset(legacy_subnet)
                self.remapped_offsets[offset] = int(
                    int(legacy_subnet['mapped_network'].network_address)
                    + mapped_offset
                    - int(self.network.network_address)
                )

            legacy_subnet['allocated_offsets'].add(mapped_offset)
            mapped_host_offset = int(
                int(legacy_subnet['mapped_network'].network_address)
                + mapped_offset
                - int(self.network.network_address)
            )
            legacy_subnet['host_map'][offset] = mapped_host_offset
            self._allocated_offsets.add(mapped_host_offset)
            return mapped_host_offset

        return None

    def _map_host_offset(self, offset):
        if offset in self._host_offset_map:
            return self._host_offset_map[offset]

        registered_offset = self._map_registered_subnet_offset(offset)
        if registered_offset is not None:
            self._host_offset_map[offset] = registered_offset
            return registered_offset

        usable_offsets = self._usable_offsets()
        if offset in usable_offsets:
            mapped_offset = offset
        else:
            mapped_offset = self._next_free_offset()
            self.remapped_offsets[offset] = mapped_offset

        self._allocated_offsets.add(mapped_offset)
        self._host_offset_map[offset] = mapped_offset
        return mapped_offset

    def host(self, offset):
        offset = int(offset)
        mapped_offset = self._map_host_offset(offset)
        return str(self.network.network_address + mapped_offset)

    def host_with_prefix(self, offset):
        return f'{self.host(offset)}/{self.prefixlen}'

    @staticmethod
    def _is_legacy_subnet(offset, prefix):
        size = 2 ** (32 - prefix)
        return offset % size == 0

    def subnet(self, offset, old_prefix):
        return self._subnet_network(offset, old_prefix).with_prefixlen

    def _match_is_subnet(self, match):
        prefix = match.group('prefix')
        if prefix is None:
            return False
        return self._is_legacy_subnet(int(match.group('offset')), int(prefix))

    def replace_legacy_ips(self, content):
        matches = list(self._LEGACY_IP_RE.finditer(content))
        direct_offsets = [
            int(match.group('offset'))
            for match in matches
            if not self._match_is_subnet(match)
        ]
        self._reserve_direct_offsets(direct_offsets)

        def replace(match):
            offset = int(match.group('offset'))
            prefix = match.group('prefix')
            if prefix is not None and self._match_is_subnet(match):
                return self.subnet(offset, int(prefix))
            if prefix is not None:
                return self.host_with_prefix(offset)
            return self.host(offset)

        return self._LEGACY_IP_RE.sub(replace, content)

    def render_template(self, template, **context):
        context = dict(context)
        context.update(
            ip_range=self.TEMPLATE_MARKER,
            ip=self.host,
            ip_with_prefix=self.host_with_prefix,
            network_cidr=self.cidr,
            prefix_length=self.prefixlen,
            gateway_ip=str(self.network.network_address + 1),
        )
        return self.replace_legacy_ips(template.render(**context))
