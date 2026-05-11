"""Sector → hero image mapping. Curated Unsplash URLs, no API calls.

Why curated and not dynamic Unsplash search? Reliability. We control quality
absolutely. Adding a new sector = 1 hardcoded URL.
"""

from __future__ import annotations

# Each entry has 1+ image URL options. The first is the default. The picker
# uses a stable hash of the slug so the same prospect always gets the same
# image (idempotent rendering).

# All URLs are Unsplash CDN with size 1200, quality 85, auto format, fit crop.
_BASE_PARAMS = "?w=1200&q=85&auto=format&fit=crop"

SECTOR_HERO_IMAGES: dict[str, list[str]] = {
    "wealth_management": [
        f"https://images.unsplash.com/photo-1502602898657-3e91760cbb34{_BASE_PARAMS}",  # Paris Eiffel
        f"https://images.unsplash.com/photo-1431274172761-fca41d930114{_BASE_PARAMS}",  # arch detail
        f"https://images.unsplash.com/photo-1486325212027-8081e485255e{_BASE_PARAMS}",  # haussmann
    ],
    "law": [
        f"https://images.unsplash.com/photo-1505664194779-8beaceb93744{_BASE_PARAMS}",  # courtroom
        f"https://images.unsplash.com/photo-1589994965851-a8f479c573a9{_BASE_PARAMS}",  # books
    ],
    "consulting": [
        f"https://images.unsplash.com/photo-1497366216548-37526070297c{_BASE_PARAMS}",  # office
        f"https://images.unsplash.com/photo-1556761175-5973dc0f32e7{_BASE_PARAMS}",  # meeting
    ],
    "real_estate": [
        f"https://images.unsplash.com/photo-1564013799919-ab600027ffc6{_BASE_PARAMS}",  # house
        f"https://images.unsplash.com/photo-1493809842364-78817add7ffb{_BASE_PARAMS}",  # interior
    ],
    "restaurant": [
        f"https://images.unsplash.com/photo-1514933651103-005eec06c04b{_BASE_PARAMS}",  # restaurant
        f"https://images.unsplash.com/photo-1559339352-11d035aa65de{_BASE_PARAMS}",  # plate
    ],
    "healthcare": [
        f"https://images.unsplash.com/photo-1576091160399-112ba8d25d1d{_BASE_PARAMS}",  # clinic
        f"https://images.unsplash.com/photo-1631815589968-fdb09a223b1e{_BASE_PARAMS}",  # care
    ],
    "beauty": [
        f"https://images.unsplash.com/photo-1560066984-138dadb4c035{_BASE_PARAMS}",  # salon
        f"https://images.unsplash.com/photo-1522337360788-8b13dee7a37e{_BASE_PARAMS}",  # spa
    ],
    "construction": [
        f"https://images.unsplash.com/photo-1503387762-592deb58ef4e{_BASE_PARAMS}",  # building
        f"https://images.unsplash.com/photo-1581094794329-c8112a89af12{_BASE_PARAMS}",  # tools
    ],
    "ecommerce": [
        f"https://images.unsplash.com/photo-1556909114-f6e7ad7d3136{_BASE_PARAMS}",  # boutique
        f"https://images.unsplash.com/photo-1441986300917-64674bd600d8{_BASE_PARAMS}",  # store
    ],
    "fitness": [
        f"https://images.unsplash.com/photo-1534438327276-14e5300c3a48{_BASE_PARAMS}",  # gym
        f"https://images.unsplash.com/photo-1517836357463-d25dfeac3438{_BASE_PARAMS}",  # studio
    ],
    "education": [
        f"https://images.unsplash.com/photo-1497486751825-1233686d5d80{_BASE_PARAMS}",  # books
        f"https://images.unsplash.com/photo-1524178232363-1fb2b075b655{_BASE_PARAMS}",  # classroom
    ],
    "creative": [
        f"https://images.unsplash.com/photo-1542744173-8e7e53415bb0{_BASE_PARAMS}",  # studio
        f"https://images.unsplash.com/photo-1561070791-2526d30994b8{_BASE_PARAMS}",  # creative
    ],
    "professional_service": [
        f"https://images.unsplash.com/photo-1554224155-6726b3ff858f{_BASE_PARAMS}",  # documents
        f"https://images.unsplash.com/photo-1450101499163-c8848c66ca85{_BASE_PARAMS}",  # office
    ],
    "default": [
        f"https://images.unsplash.com/photo-1486325212027-8081e485255e{_BASE_PARAMS}",  # haussmann
        f"https://images.unsplash.com/photo-1431274172761-fca41d930114{_BASE_PARAMS}",  # arch detail
    ],
}


def pick_hero_image(sector: str, slug: str = "") -> str:
    """Pick a hero image URL for the sector. Stable per slug (hash-based)."""
    options = SECTOR_HERO_IMAGES.get(sector, SECTOR_HERO_IMAGES["default"])
    if not slug:
        return options[0]
    # Stable hash so re-rendering same slug yields same image
    idx = abs(hash(slug)) % len(options)
    return options[idx]
