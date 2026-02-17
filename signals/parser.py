"""Signal parser using Groq LLM to extract structured data from Telegram messages."""

import json
import re

from groq import AsyncGroq
from decouple import config


GROQ_MODEL = config("GROQ_MODEL", default="openai/gpt-oss-20b")

SYSTEM_PROMPT = """Analyze this crypto futures trading signal message and extract ALL information.

The signals come from BITFA FUTURES channel on Telegram. They follow this general format:

SIGNAL FORMAT:
- Exchange: Lbank Futures
- Direction: LONG or SHORT (indicated by colored circles 🔴=SHORT, 🟢=LONG)
- Symbol: e.g. #ETH/USDT
- Entry price: single price or range (e.g. "1966.3 🦅 1986.4")
- Take Profits: TP1, TP2, TP3 (marked with ✅ or 🟢)
- Stop Loss: marked with 🔴
- Risk: e.g. "1% Risk (Isolated 8X)" — percentage, margin type, leverage

UPDATE MESSAGES (follow-up to original signals):
1. "Entry X Achieved" — an entry point was hit
2. Risk management instructions in Persian — e.g. "نصف پوزیشن رو ببندید" (close half position)
3. "Target (X) Reached" with profit % — a TP was hit
4. "Position fully closed" — trade is done
5. "SL to entry" / "ریسک‌فری" — move stop loss to breakeven

MESSAGE TYPES:
- "new_signal" — Fresh trading signal with entry, SL, TPs
- "entry_hit" — Entry point reached notification
- "tp_hit" — Take profit reached
- "sl_modified" — Stop loss modification
- "partial_close" — Close part of position
- "full_close" — Close entire position
- "risk_free" — Move SL to entry (breakeven)
- "position_closed" — Position fully closed
- "info" — Informational, no action needed

Return JSON:
{
    "message_type": "new_signal|entry_hit|tp_hit|sl_modified|partial_close|full_close|risk_free|position_closed|info",
    "symbol": "ETH/USDT" or null,
    "direction": "long|short" or null,
    "entry_price_low": number or null,
    "entry_price_high": number or null,
    "stop_loss": number or null,
    "take_profits": [number, ...] or [],
    "risk_percent": number or null,
    "leverage": number or null,
    "margin_type": "isolated|cross" or null,
    "tp_number": number or null,
    "profit_percent": number or null,
    "close_percentage": number or null,
    "new_stop_loss": number or null,
    "instructions": "brief description of what to do" or null,
    "confidence": 0.0-1.0
}

IMPORTANT:
- Parse Persian text for risk management instructions
- Entry prices can be a range (two numbers) — use entry_price_low and entry_price_high
- For update messages, try to identify which symbol they relate to
- Return ONLY valid JSON, no explanation."""


class SignalParser:
    """Parses trading signals using Groq LLM."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.client = AsyncGroq(api_key=api_key)
        self.model = model or GROQ_MODEL

    async def parse(self, text: str) -> dict | None:
        """Parse a signal message into structured data.

        Args:
            text: Raw message text from Telegram

        Returns:
            Parsed signal dict or None if not a trading message
        """
        try:
            completion = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ],
                temperature=0.1,
                max_completion_tokens=4096,
                stream=False,
            )
            response_text = completion.choices[0].message.content.strip()
            return self._parse_response(response_text)
        except Exception as e:
            print(f"Error parsing signal: {e}")
            return None

    def _parse_response(self, response_text: str) -> dict | None:
        """Parse JSON response from LLM."""
        cleaned = re.sub(r"^```json\s*", "", response_text)
        cleaned = re.sub(r"\s*```$", "", cleaned)

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            print(f"Failed to parse JSON: {response_text[:200]}")
            return None

        if data.get("message_type") == "info" and not data.get("symbol"):
            return None

        return data
