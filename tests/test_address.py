# tests/test_address.py
import pytest
from terraformat.address import TerraformResourceAddress


@pytest.mark.parametrize("address, expected_modules, expected_type, expected_name, expected_key", [
    # Test case 1: Simple address (unchanged)
    ("aws_instance.web_server", [], "aws_instance", "web_server", None),

    # Test case 2: Address with a numeric key (unchanged)
    ("random_pet.server[2]", [], "random_pet", "server", 2),

    # Test case 3: Address with a string key (unchanged)
    ('google_project_iam_member.project["roles/owner"]', [], "google_project_iam_member", "project", "roles/owner"),

    # Test case 4: Address in a single module (MODIFIED)
    ("module.vpc.aws_subnet.public", ["module", "vpc"], "aws_subnet", "public", None),

    ("module.aws_firehose_stream[\"elements_shopfront.download\"].aws_kinesis_firehose_delivery_stream.this", ["module", "aws_firehose_stream[\"elements_shopfront.download\"]"], "aws_kinesis_firehose_delivery_stream", "this", None),

    # Test case 5: Address in nested modules with a key (MODIFIED)
    ("module.network.module.subnets.aws_route_table.private[0]", ["module", "network", "module", "subnets"],
     "aws_route_table", "private", 0),

    ("module.aws_s3_bucket[\"hub-iceberg-poc-target\"].aws_s3_bucket_policy.this[0]", ["module", r'aws_s3_bucket["hub-iceberg-poc-target"]'], "aws_s3_bucket_policy", "this", 0),
])
def test_valid_address_parsing(address, expected_modules, expected_type, expected_name, expected_key):

    resource = TerraformResourceAddress(address)

    print(resource.type)
    print(resource.name)
    print(resource.key)
    print(resource.module_path)

    assert resource.type == expected_type
    assert resource.name == expected_name
    assert resource.key == expected_key

    assert resource.module_path == expected_modules
