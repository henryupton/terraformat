class TerraformResourceAddress:
    SPECIAL_VALUES = {
        ".": "{{ DOT }}"
    }

    def __init__(self, address_string):
        self.full_address = address_string

        self.module_path = []
        self.type = ""
        self.name = ""
        self.key = None

        self._parse()

    def _escape_dynamic_keys(self, address):
        """
        Escapes dots which are allowed in keys but will upset the parser.
        """
        is_key = False
        for i, char in enumerate(address):
            if char == '"':
                is_key = not is_key

            if is_key and char in self.SPECIAL_VALUES:
                address = address[:i] + self.SPECIAL_VALUES[char] + address[i + 1:]

        return address

    def _reencode_dynamic_keys(self, address):
        """
        Replaces special values in the address with their original characters.
        """
        for key, value in self.SPECIAL_VALUES.items():
            address = address.replace(value, key)
        return address

    @staticmethod
    def _parse_key_from_address(address):
        address_reversed = address[::-1]

        value = ""
        is_key = False
        start_index = 0
        end_index = 0
        for i, char in enumerate(address_reversed):
            if char == '[':
                start_index = i
                break

            if char == ']':
                is_key = True
                end_index = i
                continue

            if is_key:
                value += char

        return value[::-1].strip().strip('"'), start_index, end_index

    def _parse(self):
        """
        Parses the address string using guard clauses for early exit on errors.
        """
        address = self.full_address

        # 1. Check if the address contains a key (e.g., "module.vpc.aws_subnet.public[0]")
        key, start, end = self._parse_key_from_address(address)
        if key and address.endswith(']'):  # Only want keys which are at the end.
            try:
                self.key = int(key)  # Try to convert to an integer if possible
            except ValueError:
                self.key = key
            address = address[:len(address) - start - 1]

        # 2. Split the address into parts.
        address = self._escape_dynamic_keys(address)
        parts = address.split('.')
        parts = [self._reencode_dynamic_keys(part) for part in parts]

        self.name = parts.pop(-1)
        self.type = parts.pop(-1)
        self.module_path = parts

    def __repr__(self):
        return f"TerraformResourceAddress('{self.full_address}')"
