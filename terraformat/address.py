# terraformat/address.py
import re


class TerraformResourceAddress:
    # ... __init__ remains the same ...
    def __init__(self, address_string):
        self.full_address = address_string

        self.module_path = []
        self.type = ""
        self.name = ""
        self.key = None

        self._parse()

    @staticmethod
    def _parse_key(key_str):
        key_str_reversed = key_str[::-1]

        key_value = ""
        is_key = False
        start_index = 0
        end_index = 0
        for i, char in enumerate(key_str_reversed):
            if char == '[':
                start_index = i
                break

            if char == ']':
                is_key = True
                end_index = i
                continue

            if is_key:
                key_value += char

        return key_value[::-1].strip().strip('"'), start_index, end_index

    def _parse(self):
        """
        Parses the address string using guard clauses for early exit on errors.
        """
        address = self.full_address

        # 1. Check if the address contains a key (e.g., "module.vpc.aws_subnet.public[0]")
        key, start, end = self._parse_key(address)
        if key:
            try:
                self.key = int(key)  # Try to convert to an integer if possible
            except ValueError:
                self.key = key
            address = address[:len(address) - start - 1]

        # 2. Split the address into parts.
        parts = address.split('.')
        if len(parts) < 2:
            raise ValueError("Must contain at least a type and a name")

        self.name = parts.pop(-1)
        self.type = parts.pop(-1)
        self.module_path = parts

    def __repr__(self):
        return f"TerraformResourceAddress('{self.full_address}')"
