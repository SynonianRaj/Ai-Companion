"""
Indian Calendar & Panchang Engine:
Authoritative astronomical dates for 2026 and 2027 verified against Drik Panchang
(New Delhi & Bengaluru coordinates), official state gazettes (Karnataka, Delhi),
and official sports tournament calendars (ICC, BCCI).
"""

from datetime import datetime, date
from typing import Dict, Any, Optional, List


# Authoritative Panchang-verified dates for 2026 and 2027
INDIAN_FESTIVALS_AND_EVENTS: Dict[date, Dict[str, Any]] = {
    # --- 2026 ---
    date(2026, 1, 14): {
        "name": "Makar Sankranti / Pongal",
        "type": "major_festival",
        "source": "Drik Panchang",
        "cues": "sesame chikki, Delhi rooftop kite memories, Indiranagar neighbour sharing sweet pongal"
    },
    date(2026, 1, 26): {
        "name": "Republic Day",
        "type": "national_holiday",
        "source": "Official Gazette",
        "cues": "watching parade on TV with Papa on phone call, lazy holiday breakfast"
    },
    date(2026, 2, 7): {
        "name": "ICC Men's T20 World Cup Begins (India & Sri Lanka)",
        "type": "sports_tournament",
        "source": "Official ICC",
        "cues": "tournament excitement, Papa discussing group stage fixtures"
    },
    date(2026, 2, 15): {
        "name": "Maha Shivratri",
        "type": "cultural_observance",
        "source": "Drik Panchang",
        "cues": "temple bells, sabudana khichdi home cooking"
    },
    date(2026, 3, 3): {
        "name": "Holika Dahan",
        "type": "cultural_observance",
        "source": "Drik Panchang",
        "cues": "evening bonfires, festive gathering"
    },
    date(2026, 3, 4): {
        "name": "Holi (Rangwali Holi)",
        "type": "major_festival",
        "source": "Drik Panchang",
        "cues": "colors, gujiya parcel sent from Delhi, washing stubborn pink gulal off hands"
    },
    date(2026, 3, 8): {
        "name": "ICC Men's T20 World Cup Final (Ahmedabad)",
        "type": "sports_fixture",
        "source": "Official ICC",
        "cues": "intense match excitement, cheering heard across 12th Main Indiranagar, Papa calling every over"
    },
    date(2026, 3, 19): {
        "name": "Ugadi (Yugadi)",
        "type": "regional_festival",
        "source": "Drik Panchang",
        "cues": "Karnataka New Year; Mrs. Rao downstairs brings bevu-bella (neem & jaggery) and festive greetings"
    },
    date(2026, 3, 20): {
        "name": "Eid-ul-Fitr (Moon Sighting Dependent)",
        "type": "major_festival",
        "source": "Official Moon Sighting",
        "cues": "sheer khurma from college friends, festive street food"
    },
    date(2026, 3, 21): {
        "name": "Eid-ul-Fitr (General Observance in India)",
        "type": "major_festival",
        "source": "Official Moon Sighting",
        "cues": "warm festive wishes, biryani shared by friends"
    },
    date(2026, 3, 28): {
        "name": "IPL 2026 Opening Window",
        "type": "sports_season",
        "source": "BCCI Calendar",
        "cues": "RCB flags across Indiranagar cafes, friendly Delhi Capitals teasing with Kabir"
    },
    date(2026, 5, 28): {
        "name": "Eid al-Adha (Bakrid)",
        "type": "major_festival",
        "source": "Official Moon Sighting",
        "cues": "festive feast, wishing friends"
    },
    date(2026, 8, 15): {
        "name": "Independence Day",
        "type": "national_holiday",
        "source": "Official Gazette",
        "cues": "patriotic songs on radio, Delhi rooftop kite battles nostalgia"
    },
    date(2026, 8, 26): {
        "name": "Onam (Thiruvonam)",
        "type": "regional_festival",
        "source": "Drik Panchang",
        "cues": "Onasadhya feast at an Indiranagar Kerala restaurant with Rhea, floral pookkalam"
    },
    date(2026, 8, 28): {
        "name": "Raksha Bandhan",
        "type": "family_festival",
        "source": "Drik Panchang",
        "cues": "tracking speed-post parcel sent to Kabir in Delhi, teasing video call"
    },
    date(2026, 9, 4): {
        "name": "Krishna Janmashtami",
        "type": "major_festival",
        "source": "Drik Panchang",
        "cues": "midnight prayers, panjiri and butter prasad"
    },
    date(2026, 9, 14): {
        "name": "Ganesh Chaturthi",
        "type": "major_festival",
        "source": "Drik Panchang",
        "cues": "clay Ganesha pandals on 100 Feet Road, modaks, loud evening aartis"
    },
    date(2026, 10, 2): {
        "name": "Gandhi Jayanti",
        "type": "national_holiday",
        "source": "Official Gazette",
        "cues": "dry day, quiet Indiranagar lanes, peaceful morning walk"
    },
    date(2026, 10, 11): {
        "name": "Shardiya Navratri Prarambh (Ghatasthapana)",
        "type": "major_festival",
        "source": "Drik Panchang",
        "cues": "Mummy fasting in Delhi, garba nights music, festive buzz"
    },
    date(2026, 10, 17): {
        "name": "Durga Puja (Maha Saptami)",
        "type": "major_festival",
        "source": "Drik Panchang",
        "cues": "pandal hopping in Koramangala with Rhea, dhunuchi dance"
    },
    date(2026, 10, 19): {
        "name": "Durga Mahashtami / Maha Navami",
        "type": "major_festival",
        "source": "Drik Panchang",
        "cues": "ashtami pushpanjali, evening pandal bhog"
    },
    date(2026, 10, 20): {
        "name": "Dussehra / Vijayadashami",
        "type": "major_festival",
        "source": "Drik Panchang",
        "cues": "Ravan dahan in Delhi nostalgia, sweet jalebi, Vijayadashami greetings"
    },
    date(2026, 10, 29): {
        "name": "Karwa Chauth",
        "type": "cultural_observance",
        "source": "Drik Panchang (Verified)",
        "cues": "Mummy fasting in Delhi; evening moon sighting calls on family group; festive sargi memories"
    },
    date(2026, 11, 1): {
        "name": "Kannada Rajyotsava",
        "type": "regional_holiday",
        "source": "Karnataka Gazette",
        "cues": "Karnataka State Day: red and yellow flags fluttering on Indiranagar autos and shops, Kannada songs playing, cheerful holiday mood"
    },
    date(2026, 11, 8): {
        "name": "Diwali (Lakshmi Puja)",
        "type": "major_festival",
        "source": "Drik Panchang",
        "cues": "balcony diyas, fairy lights, cleaning madness, kaju katli boxes, video calling home"
    },
    date(2026, 11, 11): {
        "name": "Bhai Dooj (Yama Dwitiya)",
        "type": "family_festival",
        "source": "Drik Panchang (Verified)",
        "cues": "Kabir demanding GPay transfer over WhatsApp, teasing sibling exchange"
    },
    date(2026, 11, 15): {
        "name": "Chhath Puja (Surya Shashthi Arghya)",
        "type": "cultural_observance",
        "source": "Drik Panchang",
        "cues": "evening river Arghya, thekua prasad sent from relatives, Delhi memories"
    },
    date(2026, 12, 25): {
        "name": "Christmas",
        "type": "celebration",
        "source": "Official Gazette",
        "cues": "illuminated Brigade Road strolls, plum cake from Thom's Bakery, chilly evening breeze"
    },

    # --- 2027 ---
    date(2027, 1, 14): {
        "name": "Makar Sankranti / Pongal",
        "type": "major_festival",
        "source": "Drik Panchang",
        "cues": "crisp morning, sesame sweets, rooftop kites in Delhi nostalgia"
    },
    date(2027, 1, 26): {
        "name": "Republic Day",
        "type": "national_holiday",
        "source": "Official Gazette",
        "cues": "national holiday, relaxed tea and morning news"
    },
    date(2027, 3, 6): {
        "name": "Maha Shivratri",
        "type": "cultural_observance",
        "source": "Drik Panchang",
        "cues": "temple morning chants, fasting sabudana vada"
    },
    date(2027, 3, 10): {
        "name": "Eid-ul-Fitr (Subject to Moon Sighting)",
        "type": "major_festival",
        "source": "Official Moon Sighting",
        "cues": "sweet sheer khurma, festive greetings"
    },
    date(2027, 3, 21): {
        "name": "Holika Dahan",
        "type": "cultural_observance",
        "source": "Drik Panchang",
        "cues": "evening Holika bonfire, sweets"
    },
    date(2027, 3, 22): {
        "name": "Holi (Rangwali Holi)",
        "type": "major_festival",
        "source": "Drik Panchang",
        "cues": "colors, gujiya parcel, joyous celebrations"
    },
    date(2027, 4, 7): {
        "name": "Ugadi",
        "type": "regional_festival",
        "source": "Drik Panchang",
        "cues": "Karnataka New Year; mango leaves on doors, neem and jaggery prasada with Mrs. Rao"
    },
    date(2027, 5, 17): {
        "name": "Eid al-Adha (Bakrid) (Subject to Moon Sighting)",
        "type": "major_festival",
        "source": "Official Moon Sighting",
        "cues": "festive feast, warm greetings"
    },
    date(2027, 8, 15): {
        "name": "Independence Day",
        "type": "national_holiday",
        "source": "Official Gazette",
        "cues": "80th Independence Day, patriotic atmosphere"
    },
    date(2027, 8, 17): {
        "name": "Raksha Bandhan",
        "type": "family_festival",
        "source": "Drik Panchang",
        "cues": "rakhi tying rituals, gift banter with Kabir"
    },
    date(2027, 8, 25): {
        "name": "Krishna Janmashtami",
        "type": "major_festival",
        "source": "Drik Panchang",
        "cues": "dahi handi celebrations, midnight bhajans"
    },
    date(2027, 9, 4): {
        "name": "Ganesh Chaturthi",
        "type": "major_festival",
        "source": "Drik Panchang",
        "cues": "Indiranagar street pandals, modak treats"
    },
    date(2027, 9, 12): {
        "name": "Onam (Thiruvonam)",
        "type": "regional_festival",
        "source": "Drik Panchang",
        "cues": "pookkalam flowers at cafes, sadhya lunch with friends"
    },
    date(2027, 9, 30): {
        "name": "Shardiya Navratri Prarambh",
        "type": "major_festival",
        "source": "Drik Panchang",
        "cues": "nine nights of festivities, fasting, festive lights"
    },
    date(2027, 10, 9): {
        "name": "Dussehra / Vijayadashami",
        "type": "major_festival",
        "source": "Drik Panchang",
        "cues": "Vijayadashami sweets, victory of good over evil"
    },
    date(2027, 10, 18): {
        "name": "Karwa Chauth",
        "type": "cultural_observance",
        "source": "Drik Panchang",
        "cues": "family moon sighting video calls, evening prayers"
    },
    date(2027, 10, 20): {
        "name": "ICC Men's Cricket World Cup Begins (South Africa/Zimbabwe/Namibia)",
        "type": "sports_tournament",
        "source": "Official ICC",
        "cues": "50-over World Cup excitement, Papa tracking match schedules"
    },
    date(2027, 10, 29): {
        "name": "Diwali (Lakshmi Puja)",
        "type": "major_festival",
        "source": "Drik Panchang",
        "cues": "diyas on terrace, lights, sweets, new clothes"
    },
    date(2027, 10, 31): {
        "name": "Bhai Dooj",
        "type": "family_festival",
        "source": "Drik Panchang",
        "cues": "sibling bond celebration, sweet boxes"
    },
    date(2027, 11, 1): {
        "name": "Kannada Rajyotsava",
        "type": "regional_holiday",
        "source": "Karnataka Gazette",
        "cues": "Bengaluru celebrations, yellow-red flags along CMH Road"
    },
    date(2027, 11, 4): {
        "name": "Chhath Puja (Surya Shashthi Arghya)",
        "type": "cultural_observance",
        "source": "Drik Panchang",
        "cues": "evening Arghya, thekua from Delhi family"
    },
    date(2027, 12, 25): {
        "name": "Christmas",
        "type": "celebration",
        "source": "Official Gazette",
        "cues": "Brigade Road lights, winter holiday feel"
    }
}


class IndianCalendar:
    """Provides deterministic date-based Indian calendar, festival, and seasonal context."""

    @classmethod
    def get_context_for_date(cls, target_dt: datetime) -> Dict[str, Any]:
        """
        Calculates active festival, approaching festival (1-7 days away),
        and authentic Bengaluru/Delhi season texture for any given datetime.
        """
        d = target_dt.date() if isinstance(target_dt, datetime) else target_dt

        active_event = INDIAN_FESTIVALS_AND_EVENTS.get(d)

        # Check approaching events within 7 days
        upcoming_event = None
        for offset in range(1, 8):
            future_date = date.fromordinal(d.toordinal() + offset)
            if future_date in INDIAN_FESTIVALS_AND_EVENTS:
                ev = INDIAN_FESTIVALS_AND_EVENTS[future_date]
                upcoming_event = {
                    "name": ev["name"],
                    "type": ev["type"],
                    "days_away": offset,
                    "target_date": future_date.strftime("%Y-%m-%d"),
                    "cues": ev["cues"]
                }
                break

        # Season texture in Bengaluru & Delhi
        month = d.month
        if month in (11, 12, 1):
            season = "pleasant Bengaluru winter nip; crisp mornings, warm cardigan in the evening; Delhi chilly and foggy"
        elif month in (2, 3, 4):
            season = "gorgeous Bengaluru spring; jacaranda trees blooming purple on Indiranagar lanes; mild sunny days"
        elif month in (5, 6):
            season = "warm pre-monsoon breeze; mango cravings; occasional sudden evening thunderstorms"
        else:
            season = "Bengaluru monsoon showers; petrichor smell on wet asphalt; hot cutting adrak chai weather"

        return {
            "calendar_date": d.strftime("%Y-%m-%d"),
            "active_event": active_event,
            "upcoming_event": upcoming_event,
            "season_texture": season
        }

    @classmethod
    def get_all_events(cls) -> List[Dict[str, Any]]:
        """Returns sorted list of all 2026-2027 festivals for test printing and validation."""
        events = []
        for d, ev in sorted(INDIAN_FESTIVALS_AND_EVENTS.items()):
            events.append({
                "date": d.strftime("%Y-%m-%d"),
                "name": ev["name"],
                "type": ev["type"],
                "source": ev["source"],
                "cues": ev["cues"]
            })
        return events
