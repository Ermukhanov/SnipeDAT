#!/usr/bin/env python3
"""
SnipeDAT AI Bot - Standalone version with mock HTTP for testing (no external deps).
Production version uses httpx + real API calls.
"""

import os
import sys
import json
import re
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict
from enum import Enum
import asyncio

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class CompanyStatus(Enum):
    """Kazakhstan company registry status codes."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    DISSOLVED = "dissolved"
    UNKNOWN = "unknown"
    ERROR = "error"


@dataclass
class ParsedLoad:
    """Parsed load data extracted from raw text."""
    origin: str
    destination: str
    weight: Optional[str] = None
    load_type: Optional[str] = None
    price: Optional[str] = None
    pickup_date: Optional[str] = None
    raw_text: str = ""
    parsed_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CompanyCheckResult:
    """Result of a company registry lookup."""
    bin: str
    company_name: Optional[str] = None
    status: CompanyStatus = CompanyStatus.UNKNOWN
    registration_date: Optional[str] = None
    address: Optional[str] = None
    error: Optional[str] = None
    checked_at: str = ""
    source: str = "unknown"

    def to_dict(self) -> Dict[str, Any]:
        return {
            **asdict(self),
            'status': self.status.value
        }


class MockOpenAIParser:
    """
    Mock OpenAI parser for testing.
    In production, replace with real httpx-based API calls.
    """

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.api_key = api_key
        self.model = model
        logger.info(f"Parser initialized with model: {model}")

    async def parse_load_text(self, raw_text: str) -> Optional[ParsedLoad]:
        """
        Mock parser using regex patterns to extract load data.
        Production version calls OpenAI API.
        """
        if not raw_text or not raw_text.strip():
            logger.warning("Empty raw_text provided")
            return None

        logger.info(f"Parsing load text: {raw_text[:80]}...")

        # Mock parsing with regex patterns
        origin = self._extract_origin(raw_text)
        destination = self._extract_destination(raw_text)
        weight = self._extract_weight(raw_text)
        load_type = self._extract_load_type(raw_text)
        price = self._extract_price(raw_text)
        pickup_date = self._extract_date(raw_text)

        parsed = ParsedLoad(
            origin=origin,
            destination=destination,
            weight=weight,
            load_type=load_type,
            price=price,
            pickup_date=pickup_date,
            raw_text=raw_text,
            parsed_at=datetime.utcnow().isoformat()
        )

        logger.info(f"Extracted: {origin} -> {destination}, Weight: {weight}, Type: {load_type}, Price: {price}")
        return parsed

    @staticmethod
    def _extract_origin(text: str) -> str:
        """Extract pickup city from load text."""
        patterns = [
            r"from\s+([A-Z][a-z]+(?:,\s*[A-Z]{2})?)",
            r"pickup[:\s]+([A-Z][a-z]+(?:,\s*[A-Z]{2})?)",
            r"^([A-Z][a-z]+(?:,\s*[A-Z]{2})?)\s+to",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
        return ""

    @staticmethod
    def _extract_destination(text: str) -> str:
        """Extract delivery city from load text."""
        patterns = [
            r"to\s+([A-Z][a-z]+(?:,\s*[A-Z]{2})?)",
            r"delivery[:\s]+([A-Z][a-z]+(?:,\s*[A-Z]{2})?)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
        return ""

    @staticmethod
    def _extract_weight(text: str) -> Optional[str]:
        """Extract cargo weight from load text."""
        patterns = [
            r"(\d+(?:,\d{3})?)\s*(?:lbs?|pounds?|kg|tons?)",
            r"(\d+)\s*(?:lbs?|pounds?|kg|tons?)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(0).strip()
        return None

    @staticmethod
    def _extract_load_type(text: str) -> Optional[str]:
        """Extract cargo type from load text."""
        types = ["dry van", "refrigerated", "flatbed", "hazmat", "machinery", "general", "hazmat"]
        text_lower = text.lower()
        for load_type in types:
            if load_type in text_lower:
                return load_type.title()
        return None

    @staticmethod
    def _extract_price(text: str) -> Optional[str]:
        """Extract rate/price from load text."""
        patterns = [
            r"rate[:\s]+\$?(\d+(?:,\d{3})?)",
            r"\$(\d+(?:,\d{3})?)",
            r"(\d+(?:,\d{3})?)\s*(?:rate|price)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return f"${match.group(1)}" if "$" not in match.group(0) else match.group(0)
        return None

    @staticmethod
    def _extract_date(text: str) -> Optional[str]:
        """Extract pickup date from load text."""
        patterns = [
            r"(?:pickup|available)[\s:]+([A-Za-z0-9\s,-]+)",
            r"((?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|tomorrow|today|ASAP))",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

    async def close(self):
        """Cleanup."""
        logger.info("Parser closed")


class MockKazakhstanRegistry:
    """
    Mock Kazakhstan registry checker.
    Production version calls real KGD API / pk.uchet.kz endpoints.
    """

    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        logger.info(f"Registry initialized with timeout: {timeout}s")

    async def check_by_bin(self, bin: str) -> CompanyCheckResult:
        """Check company status by BIN (mock implementation)."""
        bin_clean = bin.strip().replace(" ", "").replace("-", "")

        # Validate BIN format
        if not re.match(r"^\d{12}$", bin_clean):
            logger.warning(f"Invalid BIN format: {bin}")
            return CompanyCheckResult(
                bin=bin,
                status=CompanyStatus.ERROR,
                error="Invalid BIN format (must be 12 digits)",
                checked_at=datetime.utcnow().isoformat()
            )

        # Mock response based on BIN patterns
        if bin_clean.startswith("010101"):
            return CompanyCheckResult(
                bin=bin_clean,
                company_name="Sample Transport Co.",
                status=CompanyStatus.ACTIVE,
                registration_date="2020-01-15",
                address="123 Dostyk Ave, Almaty, Kazakhstan",
                checked_at=datetime.utcnow().isoformat(),
                source="kgd_api"
            )
        else:
            return CompanyCheckResult(
                bin=bin_clean,
                status=CompanyStatus.UNKNOWN,
                error="Company not found in registry",
                checked_at=datetime.utcnow().isoformat()
            )

    async def close(self):
        """Cleanup."""
        logger.info("Registry closed")


class MockTelegramPoller:
    """Mock Telegram poller for testing."""

    def __init__(self, bot_token: str, chat_id: str, poll_timeout: int = 30):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.poll_timeout = poll_timeout
        self.is_running = False
        logger.info(f"Telegram poller initialized (chat_id: {chat_id[:10]}...)")

    async def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """Mock send message (in tests, just logs)."""
        logger.info(f"[TELEGRAM] {text[:100]}...")
        return True

    async def close(self):
        """Cleanup."""
        logger.info("Telegram poller closed")


class SnipeDAT:
    """Main SnipeDAT service orchestrator."""

    def __init__(self):
        self.parser = None
        self.registry = None
        self.telegram = None
        self._init_from_env()

    def _init_from_env(self):
        """Initialize components from environment variables."""
        openai_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.parser = MockOpenAIParser(openai_key if openai_key else "mock-key")

        self.registry = MockKazakhstanRegistry(
            timeout=int(os.getenv("KZ_REGISTRY_TIMEOUT", "10"))
        )

        telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        self.telegram = MockTelegramPoller(
            telegram_token if telegram_token else "mock-token",
            telegram_chat_id if telegram_chat_id else "mock-chat-id"
        )

    async def parse_and_check_load(self, raw_load_text: str, company_bin: Optional[str] = None) -> Dict[str, Any]:
        """Parse load text and optionally check company registry status."""
        result = {
            "load": None,
            "company_check": None,
            "timestamp": datetime.utcnow().isoformat()
        }

        if self.parser:
            result["load"] = await self.parser.parse_load_text(raw_load_text)

        if company_bin and self.registry:
            result["company_check"] = await self.registry.check_by_bin(company_bin)

        return result

    async def send_alert(self, title: str, load: ParsedLoad, company: Optional[CompanyCheckResult] = None) -> bool:
        """Send a formatted Telegram alert."""
        if not self.telegram:
            logger.warning("Telegram not configured")
            return False

        message_lines = [f"**{title}**"]

        if load:
            if load.origin and load.destination:
                message_lines.append(f"📍 {load.origin} → {load.destination}")
            if load.price:
                message_lines.append(f"💰 Rate: {load.price}")
            if load.weight:
                message_lines.append(f"⚖️ Weight: {load.weight}")
            if load.load_type:
                message_lines.append(f"📦 Type: {load.load_type}")
            if load.pickup_date:
                message_lines.append(f"📅 Pickup: {load.pickup_date}")

        if company:
            message_lines.append("")
            message_lines.append("**Company Status:**")
            message_lines.append(f"BIN: {company.bin}")
            if company.company_name:
                message_lines.append(f"Name: {company.company_name}")
            status_emoji = "✅" if company.status == CompanyStatus.ACTIVE else "⚠️"
            message_lines.append(f"{status_emoji} Status: {company.status.value}")
            if company.address:
                message_lines.append(f"Address: {company.address}")

        message = "\n".join(message_lines)
        return await self.telegram.send_message(message, parse_mode="HTML")

    async def health_check(self) -> Dict[str, Any]:
        """Return health status of all components."""
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "parser": "ready" if self.parser else "missing",
            "registry": "ready" if self.registry else "missing",
            "telegram": "ready" if self.telegram else "missing"
        }

    async def close(self):
        """Cleanup resources."""
        if self.parser:
            await self.parser.close()
        if self.registry:
            await self.registry.close()
        if self.telegram:
            await self.telegram.close()


async def test_parser():
    """Test the parser with sample load text."""
    logger.info("=" * 60)
    logger.info("TEST 1: OpenAI Parser (Mock)")
    logger.info("=" * 60)

    snipedat = SnipeDAT()

    test_loads = [
        "New Load: Los Angeles, CA to Dallas, TX. 45,000 lbs, Dry van. Rate: $3,500. Pickup ASAP.",
        "Flatbed load: Denver to Phoenix. 22 tons, Machinery. $2,800. Available tomorrow.",
        "From Chicago to Atlanta. 35000 lbs. Hazmat. Price: $4200.",
    ]

    for i, load_text in enumerate(test_loads, 1):
        logger.info(f"\nTest {i}:")
        logger.info(f"Input: {load_text}")
        parsed = await snipedat.parser.parse_load_text(load_text)
        if parsed:
            logger.info(f"✅ Parsed successfully:")
            for key, value in parsed.to_dict().items():
                if value:
                    logger.info(f"   {key}: {value}")
        else:
            logger.warning("❌ Failed to parse")

    await snipedat.close()


async def test_registry():
    """Test the Kazakhstan registry checker."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 2: Kazakhstan Registry Checker (Mock)")
    logger.info("=" * 60)

    snipedat = SnipeDAT()

    test_bins = [
        "010101001234",  # Valid format, should return mock active status
        "123456789012",  # Valid format, should return unknown
        "invalid-bin",   # Invalid format
    ]

    for bin_num in test_bins:
        logger.info(f"\nChecking BIN: {bin_num}")
        result = await snipedat.registry.check_by_bin(bin_num)
        logger.info(f"   Status: {result.status.value}")
        if result.company_name:
            logger.info(f"   Company: {result.company_name}")
        if result.address:
            logger.info(f"   Address: {result.address}")
        if result.error:
            logger.info(f"   Error: {result.error}")

    await snipedat.close()


async def test_full_workflow():
    """Test the complete workflow: parse, check registry, send alert."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 3: Full Workflow (Parse + Registry + Alert)")
    logger.info("=" * 60)

    snipedat = SnipeDAT()

    raw_text = "Load from Almaty to Bishkek. 30 tons machinery. Rate: $2,500. Company BIN: 010101001234."
    company_bin = "010101001234"

    logger.info(f"\nInput load text: {raw_text}")
    logger.info(f"Company BIN: {company_bin}")

    result = await snipedat.parse_and_check_load(raw_text, company_bin)

    logger.info(f"\n✅ Parse Result:")
    if result["load"]:
        load = result["load"]
        logger.info(f"   Origin: {load.origin}")
        logger.info(f"   Destination: {load.destination}")
        logger.info(f"   Weight: {load.weight}")
        logger.info(f"   Type: {load.load_type}")
        logger.info(f"   Price: {load.price}")

    logger.info(f"\n✅ Registry Result:")
    if result["company_check"]:
        company = result["company_check"]
        logger.info(f"   BIN: {company.bin}")
        logger.info(f"   Company: {company.company_name}")
        logger.info(f"   Status: {company.status.value}")
        logger.info(f"   Address: {company.address}")

    logger.info(f"\nSending Telegram alert...")
    success = await snipedat.send_alert(
        "🚚 New Load Alert",
        result["load"],
        result["company_check"]
    )

    if success:
        logger.info("✅ Alert sent successfully")
    else:
        logger.error("❌ Failed to send alert")

    await snipedat.close()


async def main():
    """Run all tests."""
    logger.info("\n🚀 SnipeDAT AI Bot - Test Suite\n")

    try:
        await test_parser()
        await test_registry()
        await test_full_workflow()

        logger.info("\n" + "=" * 60)
        logger.info("✅ ALL TESTS COMPLETED SUCCESSFULLY")
        logger.info("=" * 60 + "\n")

    except Exception as e:
        logger.error(f"❌ Test error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)
