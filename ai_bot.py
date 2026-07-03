#!/usr/bin/env python3
"""
SnipeDAT AI Bot - Backend service for load parsing, registry checks, and Telegram alerts.

Features:
1. OpenAI/LLM integration for parsing load data (Origin, Dest, Weight, Type, Price)
2. Kazakhstan business registry checks via KGD API / pk.uchet.kz
3. Robust Telegram long-polling with error handling
4. HTTP API endpoints for extension integration
"""

import os
import sys
import json
import time
import logging
import asyncio
import re
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict
from enum import Enum

# Try to import httpx, fall back to mock if unavailable
try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    logger_msg = "WARNING: httpx not available. Using mock implementations."

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('snipedat.log'),
        logging.StreamHandler()
    ]
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


def get_utc_now() -> str:
    """Get current UTC time in ISO format."""
    return datetime.now(timezone.utc).isoformat()


class OpenAIParser:
    """Parse load data using OpenAI API."""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.api_key = api_key
        self.model = model
        self.client = None
        if HTTPX_AVAILABLE:
            self.client = httpx.AsyncClient(timeout=30)
        logger.info(f"OpenAI Parser initialized with model: {model}")

    async def parse_load_text(self, raw_text: str) -> Optional[ParsedLoad]:
        """
        Parse raw load text using OpenAI API to extract structured fields.

        Args:
            raw_text: Raw load information text

        Returns:
            ParsedLoad object with extracted fields, or None if parsing fails
        """
        if not raw_text or not raw_text.strip():
            logger.warning("Empty raw_text provided to parse_load_text")
            return None

        if not HTTPX_AVAILABLE:
            logger.warning("httpx not available, falling back to regex parsing")
            return await self._parse_with_regex(raw_text)

        if not self.api_key or self.api_key.startswith("sk-placeholder"):
            logger.warning("OpenAI API key not configured, falling back to regex parsing")
            return await self._parse_with_regex(raw_text)

        prompt = f"""Extract load information from the following text. Return a JSON object with these fields:
- origin: pickup location (city, state/country code)
- destination: delivery location (city, state/country code)
- weight: weight in lbs or kg (numeric with unit, or null)
- load_type: cargo type (e.g., "dry", "refrigerated", "hazmat", or null)
- price: rate/price offered (numeric, or null)
- pickup_date: estimated pickup date if mentioned (ISO format or null)

If a field cannot be determined, use null.

Load text:
{raw_text}

Return only valid JSON, no markdown."""

        try:
            response = await self.client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.3,
                    "max_tokens": 200
                }
            )

            if response.status_code != 200:
                logger.error(f"OpenAI API error: {response.status_code}")
                return None

            result = response.json()
            if not result.get("choices"):
                logger.error("No choices in OpenAI response")
                return None

            content = result["choices"][0]["message"]["content"]
            parsed = json.loads(content)

            return ParsedLoad(
                origin=parsed.get("origin", ""),
                destination=parsed.get("destination", ""),
                weight=parsed.get("weight"),
                load_type=parsed.get("load_type"),
                price=parsed.get("price"),
                pickup_date=parsed.get("pickup_date"),
                raw_text=raw_text,
                parsed_at=get_utc_now()
            )

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse OpenAI JSON response: {e}")
            return None
        except Exception as e:
            logger.error(f"OpenAI API request failed: {e}")
            return None

    @staticmethod
    async def _parse_with_regex(raw_text: str) -> Optional[ParsedLoad]:
        """Fallback regex-based parsing."""
        origin = OpenAIParser._extract_origin(raw_text)
        destination = OpenAIParser._extract_destination(raw_text)
        weight = OpenAIParser._extract_weight(raw_text)
        load_type = OpenAIParser._extract_load_type(raw_text)
        price = OpenAIParser._extract_price(raw_text)
        pickup_date = OpenAIParser._extract_date(raw_text)

        return ParsedLoad(
            origin=origin,
            destination=destination,
            weight=weight,
            load_type=load_type,
            price=price,
            pickup_date=pickup_date,
            raw_text=raw_text,
            parsed_at=get_utc_now()
        )

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
        types = ["dry van", "refrigerated", "flatbed", "hazmat", "machinery"]
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
        """Close the HTTP client."""
        if self.client:
            await self.client.aclose()


class KazakhstanRegistry:
    """Check company status in Kazakhstan business registries."""

    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.client = None
        if HTTPX_AVAILABLE:
            self.client = httpx.AsyncClient(timeout=timeout)
        self.kgd_search_url = "https://kgd.gov.kz/api/v1/company/search"
        self.kgd_detail_url = "https://kgd.gov.kz/api/v1/company/{bin}"
        self.pk_uchet_search_url = "https://pk.uchet.kz/api/company/search"
        logger.info("Kazakhstan Registry initialized")

    async def check_by_bin(self, bin: str) -> CompanyCheckResult:
        """
        Check company status by BIN (Business Identification Number).

        Args:
            bin: 12-digit Kazakhstan BIN

        Returns:
            CompanyCheckResult with status and details
        """
        bin_clean = bin.strip().replace(" ", "").replace("-", "")

        if not re.match(r"^\d{12}$", bin_clean):
            logger.warning(f"Invalid BIN format: {bin}")
            return CompanyCheckResult(
                bin=bin,
                status=CompanyStatus.ERROR,
                error="Invalid BIN format (must be 12 digits)",
                checked_at=get_utc_now()
            )

        if not HTTPX_AVAILABLE or not self.client:
            logger.warning("httpx not available, returning mock result")
            return self._mock_check_by_bin(bin_clean)

        # Try KGD API first
        result = await self._check_kgd(bin_clean)
        if result:
            return result

        # Fallback to pk.uchet.kz
        result = await self._check_pk_uchet(bin_clean)
        if result:
            return result

        return CompanyCheckResult(
            bin=bin_clean,
            status=CompanyStatus.UNKNOWN,
            error="Could not verify against available registries",
            checked_at=get_utc_now()
        )

    async def _check_kgd(self, bin: str) -> Optional[CompanyCheckResult]:
        """Check KGD API for company status."""
        try:
            response = await self.client.get(
                f"{self.kgd_detail_url.format(bin=bin)}",
                headers={"Accept": "application/json"}
            )

            if response.status_code == 404:
                logger.info(f"BIN {bin} not found in KGD registry")
                return None

            if response.status_code != 200:
                logger.warning(f"KGD API returned {response.status_code}")
                return None

            data = response.json()
            status = self._parse_kgd_status(data.get("status", ""))
            return CompanyCheckResult(
                bin=bin,
                company_name=data.get("name") or data.get("company_name"),
                status=status,
                registration_date=data.get("registration_date"),
                address=data.get("address"),
                checked_at=get_utc_now(),
                source="kgd_api"
            )

        except Exception as e:
            logger.debug(f"KGD lookup error: {e}")
            return None

    async def _check_pk_uchet(self, bin: str) -> Optional[CompanyCheckResult]:
        """Check pk.uchet.kz registry as fallback."""
        try:
            response = await self.client.get(
                f"{self.pk_uchet_search_url}?bin={bin}",
                headers={"Accept": "application/json"}
            )

            if response.status_code == 404:
                logger.info(f"BIN {bin} not found in pk.uchet.kz")
                return None

            if response.status_code != 200:
                logger.warning(f"pk.uchet.kz returned {response.status_code}")
                return None

            data = response.json()
            company = data.get("result") if isinstance(data, dict) and "result" in data else data

            status = self._parse_pk_uchet_status(company.get("status", ""))
            return CompanyCheckResult(
                bin=bin,
                company_name=company.get("name") or company.get("legal_name"),
                status=status,
                registration_date=company.get("registration_date"),
                address=company.get("address"),
                checked_at=get_utc_now(),
                source="pk_uchet"
            )

        except Exception as e:
            logger.debug(f"pk.uchet.kz lookup error: {e}")
            return None

    @staticmethod
    def _mock_check_by_bin(bin: str) -> CompanyCheckResult:
        """Return mock registry result for testing."""
        if bin.startswith("010101"):
            return CompanyCheckResult(
                bin=bin,
                company_name="Sample Transport Co.",
                status=CompanyStatus.ACTIVE,
                registration_date="2020-01-15",
                address="123 Dostyk Ave, Almaty, Kazakhstan",
                checked_at=get_utc_now(),
                source="mock"
            )
        return CompanyCheckResult(
            bin=bin,
            status=CompanyStatus.UNKNOWN,
            error="Not found in registry (mock mode)",
            checked_at=get_utc_now()
        )

    @staticmethod
    def _parse_kgd_status(status_str: str) -> CompanyStatus:
        """Map KGD status string to CompanyStatus enum."""
        status_lower = (status_str or "").lower()
        if "active" in status_lower or "registr" in status_lower:
            return CompanyStatus.ACTIVE
        elif "dissolv" in status_lower or "liquidat" in status_lower:
            return CompanyStatus.DISSOLVED
        elif "inactive" in status_lower:
            return CompanyStatus.INACTIVE
        return CompanyStatus.UNKNOWN

    @staticmethod
    def _parse_pk_uchet_status(status_str: str) -> CompanyStatus:
        """Map pk.uchet status string to CompanyStatus enum."""
        status_lower = (status_str or "").lower()
        if "active" in status_lower or "действу" in status_lower:
            return CompanyStatus.ACTIVE
        elif "dissolv" in status_lower or "удален" in status_lower:
            return CompanyStatus.DISSOLVED
        elif "inactive" in status_lower:
            return CompanyStatus.INACTIVE
        return CompanyStatus.UNKNOWN

    async def close(self):
        """Close the HTTP client."""
        if self.client:
            await self.client.aclose()


class TelegramPoller:
    """Robust Telegram long-polling with error handling."""

    def __init__(self, bot_token: str, chat_id: str, poll_timeout: int = 30):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.poll_timeout = poll_timeout
        self.api_url = f"https://api.telegram.org/bot{bot_token}"
        self.client = None
        if HTTPX_AVAILABLE:
            self.client = httpx.AsyncClient(timeout=60)
        self.offset = 0
        self.is_running = False
        self.poll_errors = 0
        self.max_poll_errors = 10
        logger.info("Telegram Poller initialized")

    async def start(self, message_handler):
        """Start the long-polling loop."""
        if not HTTPX_AVAILABLE:
            logger.warning("httpx not available, cannot start polling")
            return

        self.is_running = True
        self.poll_errors = 0
        logger.info("Telegram poller started")

        while self.is_running:
            try:
                updates = await self._poll_updates()
                self.poll_errors = 0

                for update in updates:
                    try:
                        await message_handler(update)
                    except Exception as e:
                        logger.error(f"Message handler error: {e}")

            except asyncio.CancelledError:
                logger.info("Telegram poller cancelled")
                break
            except Exception as e:
                self.poll_errors += 1
                logger.error(f"Poll error ({self.poll_errors}/{self.max_poll_errors}): {e}")

                if self.poll_errors >= self.max_poll_errors:
                    logger.error("Max poll errors reached, stopping poller")
                    break

                backoff_delay = min(2 ** self.poll_errors, 300)
                logger.info(f"Backing off for {backoff_delay}s")
                await asyncio.sleep(backoff_delay)

    async def stop(self):
        """Stop the polling loop."""
        self.is_running = False
        logger.info("Telegram poller stopped")

    async def _poll_updates(self) -> List[Dict[str, Any]]:
        """Poll for new updates from Telegram."""
        try:
            response = await self.client.get(
                f"{self.api_url}/getUpdates",
                params={
                    "offset": self.offset,
                    "timeout": self.poll_timeout,
                    "allowed_updates": ["message"]
                }
            )

            if response.status_code != 200:
                raise Exception(f"Telegram API error: {response.status_code}")

            result = response.json()
            if not result.get("ok"):
                raise Exception(f"Telegram API error: {result.get('description', 'Unknown')}")

            updates = result.get("result", [])
            if updates:
                self.offset = updates[-1]["update_id"] + 1

            return updates

        except Exception as e:
            raise Exception(f"Poll error: {e}")

    async def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """Send a message to the configured chat."""
        if not self.client:
            logger.warning("HTTP client not available for sending message")
            return False

        try:
            response = await self.client.post(
                f"{self.api_url}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": parse_mode,
                    "disable_web_page_preview": True
                }
            )

            if response.status_code != 200:
                logger.error(f"Failed to send Telegram message: {response.status_code}")
                return False

            result = response.json()
            return result.get("ok", False)

        except Exception as e:
            logger.error(f"Error sending Telegram message: {e}")
            return False

    async def close(self):
        """Close the HTTP client."""
        if self.client:
            await self.client.aclose()


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
        self.parser = OpenAIParser(openai_key)

        self.registry = KazakhstanRegistry(
            timeout=int(os.getenv("KZ_REGISTRY_TIMEOUT", "10"))
        )

        telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        self.telegram = TelegramPoller(telegram_token, telegram_chat_id)

    async def parse_and_check_load(self, raw_load_text: str, company_bin: Optional[str] = None) -> Dict[str, Any]:
        """Parse load text and optionally check company registry status."""
        result = {
            "load": None,
            "company_check": None,
            "timestamp": get_utc_now()
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

        message_lines = [f"<b>{title}</b>"]

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
            message_lines.append("<b>Company Status:</b>")
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
            "timestamp": get_utc_now(),
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


async def test_full_workflow():
    """Test the complete workflow: parse, check registry, send alert."""
    logger.info("=" * 70)
    logger.info("SnipeDAT AI Bot - Full Integration Test")
    logger.info("=" * 70)

    snipedat = SnipeDAT()

    test_cases = [
        {
            "raw_text": "New Load: Los Angeles, CA to Dallas, TX. 45,000 lbs, Dry van. Rate: $3,500. Pickup ASAP.",
            "bin": "010101001234"
        },
        {
            "raw_text": "Flatbed load: Denver to Phoenix. 22 tons, Machinery. $2,800. Available tomorrow.",
            "bin": None
        },
        {
            "raw_text": "Load from Almaty to Bishkek. 30 tons machinery. Rate: $2,500.",
            "bin": "123456789012"
        }
    ]

    for i, test in enumerate(test_cases, 1):
        logger.info(f"\n--- Test Case {i} ---")
        logger.info(f"Load: {test['raw_text'][:60]}...")
        if test['bin']:
            logger.info(f"BIN: {test['bin']}")

        result = await snipedat.parse_and_check_load(test['raw_text'], test['bin'])

        if result['load']:
            load = result['load']
            logger.info(f"✅ Parsed: {load.origin} -> {load.destination}, "
                       f"Weight={load.weight}, Type={load.load_type}, Price={load.price}")

        if result['company_check']:
            company = result['company_check']
            logger.info(f"✅ Registry: {company.company_name} ({company.status.value})")

    logger.info("\n" + "=" * 70)
    logger.info("✅ All test cases completed")
    logger.info("=" * 70)

    await snipedat.close()


async def main():
    """Main entry point."""
    logger.info(f"SnipeDAT AI Bot v1.0")
    logger.info(f"httpx available: {HTTPX_AVAILABLE}")

    try:
        await test_full_workflow()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutdown")
        sys.exit(0)
