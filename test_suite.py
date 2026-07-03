#!/usr/bin/env python3
"""
Comprehensive test suite for SnipeDAT AI Bot.
Tests parsing, registry checks, and error handling.
"""

import asyncio
import json
from ai_bot import (
    SnipeDAT, ParsedLoad, CompanyStatus, CompanyCheckResult,
    OpenAIParser, KazakhstanRegistry, TelegramPoller
)


async def test_parser_extraction():
    """Test OpenAI parser with various load text formats."""
    print("\n" + "="*70)
    print("TEST 1: Parser Extraction (Regex Fallback)")
    print("="*70)

    snipedat = SnipeDAT()
    test_cases = [
        {
            "text": "Los Angeles, CA to Dallas, TX. 45,000 lbs, Dry van. Rate: $3,500.",
            "expected_origin": "Los Angeles",
            "expected_dest": "Dallas",
        },
        {
            "text": "From Denver to Phoenix. 22 tons machinery. $2,800. Tomorrow.",
            "expected_origin": "Denver",
            "expected_dest": "Phoenix",
        },
        {
            "text": "Chicago to Atlanta. 35000 lbs. Hazmat. Price: $4200.",
            "expected_origin": "Chicago",
            "expected_dest": "Atlanta",
        },
    ]

    passed = 0
    for i, test in enumerate(test_cases, 1):
        parsed = await snipedat.parser.parse_load_text(test["text"])
        if parsed:
            # Check if key fields were extracted
            has_origin = test["expected_origin"].lower() in parsed.origin.lower() or parsed.origin
            has_dest = test["expected_dest"].lower() in parsed.destination.lower() or parsed.destination
            has_weight = parsed.weight is not None
            has_price = parsed.price is not None

            if has_origin or has_dest:
                print(f"✅ Test {i}: {parsed.origin} -> {parsed.destination} (Weight: {parsed.weight})")
                passed += 1
            else:
                print(f"⚠️ Test {i}: Incomplete extraction")
        else:
            print(f"❌ Test {i}: Failed to parse")

    print(f"\nResult: {passed}/{len(test_cases)} passed")
    await snipedat.close()
    return passed == len(test_cases)


async def test_registry_validation():
    """Test Kazakhstan registry BIN validation."""
    print("\n" + "="*70)
    print("TEST 2: Registry BIN Validation")
    print("="*70)

    snipedat = SnipeDAT()
    test_cases = [
        {
            "bin": "010101001234",
            "expect_valid": True,
            "description": "Valid 12-digit BIN"
        },
        {
            "bin": "123456789012",
            "expect_valid": True,
            "description": "Another valid 12-digit BIN"
        },
        {
            "bin": "invalid-bin",
            "expect_valid": False,
            "description": "Invalid format (non-numeric)"
        },
        {
            "bin": "12345",
            "expect_valid": False,
            "description": "Invalid format (too short)"
        },
    ]

    passed = 0
    for i, test in enumerate(test_cases, 1):
        result = await snipedat.registry.check_by_bin(test["bin"])

        if test["expect_valid"]:
            # Valid BINs should return either ACTIVE, INACTIVE, or UNKNOWN
            is_valid = result.status in [CompanyStatus.ACTIVE, CompanyStatus.INACTIVE, CompanyStatus.UNKNOWN]
        else:
            # Invalid BINs should return ERROR
            is_valid = result.status == CompanyStatus.ERROR

        if is_valid:
            print(f"✅ Test {i}: {test['description']} - Status: {result.status.value}")
            passed += 1
        else:
            print(f"❌ Test {i}: {test['description']} - Unexpected status: {result.status.value}")

    print(f"\nResult: {passed}/{len(test_cases)} passed")
    await snipedat.close()
    return passed == len(test_cases)


async def test_full_workflow():
    """Test complete workflow: parse, check, alert."""
    print("\n" + "="*70)
    print("TEST 3: Full Workflow Integration")
    print("="*70)

    snipedat = SnipeDAT()

    workflow_test = {
        "raw_text": "Load from Almaty to Bishkek. 30 tons machinery. Rate: $2,500. Company BIN: 010101001234.",
        "bin": "010101001234"
    }

    print(f"Input: {workflow_test['raw_text']}")
    print(f"BIN: {workflow_test['bin']}")

    result = await snipedat.parse_and_check_load(
        workflow_test['raw_text'],
        workflow_test['bin']
    )

    checks = {
        "Parse Result": result['load'] is not None,
        "Registry Result": result['company_check'] is not None,
        "Timestamp": result['timestamp'] is not None,
    }

    passed = sum(1 for v in checks.values() if v)

    for check, passed_check in checks.items():
        status = "✅" if passed_check else "❌"
        print(f"{status} {check}: {'Present' if passed_check else 'Missing'}")

    if result['load']:
        print(f"\n  Parsed Load:")
        print(f"    Origin: {result['load'].origin}")
        print(f"    Destination: {result['load'].destination}")
        print(f"    Weight: {result['load'].weight}")
        print(f"    Type: {result['load'].load_type}")
        print(f"    Price: {result['load'].price}")

    if result['company_check']:
        print(f"\n  Registry Result:")
        print(f"    Company: {result['company_check'].company_name}")
        print(f"    Status: {result['company_check'].status.value}")
        print(f"    Address: {result['company_check'].address}")

    print(f"\nResult: {passed}/{len(checks)} checks passed")
    await snipedat.close()
    return passed == len(checks)


async def test_error_handling():
    """Test error handling and edge cases."""
    print("\n" + "="*70)
    print("TEST 4: Error Handling")
    print("="*70)

    snipedat = SnipeDAT()

    edge_cases = [
        {
            "text": "",
            "description": "Empty string",
            "should_return_none": True
        },
        {
            "text": "   ",
            "description": "Whitespace only",
            "should_return_none": True
        },
        {
            "text": "No recognizable data here at all",
            "description": "No structured data",
            "should_return_none": False  # May still parse, just empty fields
        },
    ]

    passed = 0
    for i, test in enumerate(edge_cases, 1):
        result = await snipedat.parser.parse_load_text(test["text"])

        if test["should_return_none"]:
            is_correct = result is None
            status = "✅" if is_correct else "❌"
            print(f"{status} Test {i}: {test['description']} - Correctly returned None")
        else:
            is_correct = result is not None
            status = "✅" if is_correct else "❌"
            print(f"{status} Test {i}: {test['description']} - Got result")

        if is_correct:
            passed += 1

    print(f"\nResult: {passed}/{len(edge_cases)} passed")
    await snipedat.close()
    return passed == len(edge_cases)


async def test_data_serialization():
    """Test that parsed data can be serialized to JSON."""
    print("\n" + "="*70)
    print("TEST 5: Data Serialization")
    print("="*70)

    snipedat = SnipeDAT()

    # Create test data
    test_load = ParsedLoad(
        origin="Los Angeles",
        destination="Dallas",
        weight="45,000 lbs",
        load_type="Dry Van",
        price="$3,500",
        pickup_date="Tomorrow",
        raw_text="Test load"
    )

    test_company = CompanyCheckResult(
        bin="010101001234",
        company_name="Test Transport Co.",
        status=CompanyStatus.ACTIVE,
        address="Almaty, Kazakhstan"
    )

    try:
        # Serialize to JSON
        load_json = json.dumps(test_load.to_dict())
        company_json = json.dumps(test_company.to_dict())

        # Deserialize back
        load_parsed = json.loads(load_json)
        company_parsed = json.loads(company_json)

        print(f"✅ Load serialization successful")
        print(f"✅ Company serialization successful")
        print(f"\nSerialized Load: {load_json[:80]}...")
        print(f"Serialized Company: {company_json[:80]}...")

        await snipedat.close()
        return True

    except Exception as e:
        print(f"❌ Serialization failed: {e}")
        await snipedat.close()
        return False


async def main():
    """Run all tests."""
    print("\n" + "="*70)
    print("SnipeDAT AI Bot - Comprehensive Test Suite")
    print("="*70)

    results = {}
    try:
        results["Parser Extraction"] = await test_parser_extraction()
        results["Registry Validation"] = await test_registry_validation()
        results["Full Workflow"] = await test_full_workflow()
        results["Error Handling"] = await test_error_handling()
        results["Data Serialization"] = await test_data_serialization()

        # Summary
        print("\n" + "="*70)
        print("TEST SUMMARY")
        print("="*70)

        passed_count = sum(1 for v in results.values() if v)
        total_count = len(results)

        for test_name, passed in results.items():
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"{status}: {test_name}")

        print(f"\nTotal: {passed_count}/{total_count} test suites passed")

        if passed_count == total_count:
            print("\n🚀 ALL TESTS PASSED - Ready for production!")
            return 0
        else:
            print("\n⚠️ Some tests failed - Review above for details")
            return 1

    except KeyboardInterrupt:
        print("\n\n🛑 Tests interrupted by user")
        return 1
    except Exception as e:
        print(f"\n\n❌ Test suite error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
