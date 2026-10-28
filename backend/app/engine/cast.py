"""
Cast manager: loads Aanya's recurring cast from cast.json and provides
convenient access to Core vs Occasional cast members and their tendencies.
"""

import json
import random
from pathlib import Path
from typing import Dict, Any, List, Optional


CAST_JSON_PATH = Path(__file__).parent / "cast.json"


def load_cast() -> Dict[str, List[Dict[str, Any]]]:
    """Loads cast data from cast.json."""
    if not CAST_JSON_PATH.exists():
        return {"core": [], "occasional": []}
    with open(CAST_JSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


class CastManager:
    """Manages cast queries, descriptions, and daily tendency sampling."""

    _cast_data: Optional[Dict[str, List[Dict[str, Any]]]] = None

    @classmethod
    def get_cast_data(cls) -> Dict[str, List[Dict[str, Any]]]:
        if cls._cast_data is None:
            cls._cast_data = load_cast()
        return cls._cast_data

    @classmethod
    def reload(cls) -> None:
        cls._cast_data = load_cast()

    @classmethod
    def get_core_cast(cls) -> List[Dict[str, Any]]:
        return cls.get_cast_data().get("core", [])

    @classmethod
    def get_occasional_cast(cls) -> List[Dict[str, Any]]:
        return cls.get_cast_data().get("occasional", [])

    @classmethod
    def get_member_by_id(cls, member_id: str) -> Optional[Dict[str, Any]]:
        data = cls.get_cast_data()
        for member in data.get("core", []) + data.get("occasional", []):
            if member["id"] == member_id:
                return member
        return None

    @classmethod
    def sample_daily_cast_tendencies(
        cls,
        current_date_str: str,
        is_first_of_month: bool = False,
        has_active_storyline: bool = False,
        active_storyline_id: Optional[str] = None,
        seed: Optional[int] = None
    ) -> List[Dict[str, str]]:
        """
        Samples 3-5 cast interactions for a day's journal.
        Applies at most 1-2 tendencies per person with realistic gaps.
        Core members appear frequently; Occasional members appear rarely,
        except when triggered by date context (e.g. 1st of month for landlord).
        """
        rng = random.Random(seed if seed is not None else hash(current_date_str))
        selected_events: List[Dict[str, str]] = []

        # 1. Check special triggers
        if is_first_of_month:
            landlord = cls.get_member_by_id("mr_krishnamurthy")
            if landlord and landlord.get("tendencies"):
                selected_events.append({
                    "cast_id": "mr_krishnamurthy",
                    "cast_name": landlord["name"],
                    "relation": landlord["relation"],
                    "tendency": landlord["tendencies"][0]["tendency"],
                    "timing": "morning"
                })

        # 2. Sample 2-3 Core cast members
        core_members = list(cls.get_core_cast())
        rng.shuffle(core_members)
        for member in core_members[:3]:
            tendencies = member.get("tendencies", [])
            if tendencies:
                t = rng.choice(tendencies)
                # Roll against probability with slight floor so offline generation has variety
                if rng.random() < max(0.4, t.get("probability", 0.35)):
                    selected_events.append({
                        "cast_id": member["id"],
                        "cast_name": member["name"],
                        "relation": member["relation"],
                        "tendency": t["tendency"],
                        "timing": t.get("timing", "flexible")
                    })

        # 3. Rare Occasional cast member (30% chance or if storyline calls for it)
        occasional_members = list(cls.get_occasional_cast())
        if has_active_storyline and active_storyline_id == "meera_wedding":
            meera = cls.get_member_by_id("meera")
            if meera and meera.get("tendencies"):
                selected_events.append({
                    "cast_id": "meera",
                    "cast_name": meera["name"],
                    "relation": meera["relation"],
                    "tendency": rng.choice(meera["tendencies"])["tendency"],
                    "timing": "evening"
                })
        elif rng.random() < 0.30:
            occ = rng.choice(occasional_members)
            tendencies = occ.get("tendencies", [])
            if tendencies:
                t = rng.choice(tendencies)
                selected_events.append({
                    "cast_id": occ["id"],
                    "cast_name": occ["name"],
                    "relation": occ["relation"],
                    "tendency": t["tendency"],
                    "timing": t.get("timing", "flexible")
                })

        return selected_events

    @classmethod
    def get_cast_summary_for_prompt(cls) -> str:
        """Generates concise summary of the recurring cast for system prompt injection."""
        data = cls.get_cast_data()
        lines = ["Recurring People in Your Life (Fictional, Authentic Relationships):"]
        lines.append("CORE (Regular in your life):")
        for m in data.get("core", []):
            lines.append(f"- {m['name']} ({m['relation']}): {m['bio']}")
        lines.append("OCCASIONAL (Appear when relevant):")
        for m in data.get("occasional", []):
            lines.append(f"- {m['name']} ({m['relation']}): {m['bio']}")
        return "\n".join(lines)


cast_manager = CastManager()
