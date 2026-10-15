"""HS (Harmonized System 2022) 6-digit codes for furniture, with attribute-based selection.

Codes are selected from product attributes (category, frame material, upholstery, function),
never from a generic "furniture" keyword. National tariff lines (GTİP 12-digit, CN 8-digit) extend
these and must be confirmed by the exporter's customs broker.
"""
from dataclasses import dataclass

HS_DESCRIPTIONS = {
    "9401.31": "Swivel seats with variable height adjustment, wooden frame",
    "9401.39": "Swivel seats with variable height adjustment, other",
    "9401.41": "Seats convertible into beds (sofa-beds), wooden frame",
    "9401.49": "Seats convertible into beds, other frame",
    "9401.52": "Seats of bamboo", "9401.53": "Seats of rattan",
    "9401.61": "Upholstered seats with wooden frames",
    "9401.69": "Other seats with wooden frames (non-upholstered)",
    "9401.71": "Upholstered seats with metal frames",
    "9401.79": "Other seats with metal frames",
    "9401.80": "Other seats (e.g. plastic)",
    "9403.10": "Metal furniture of a kind used in offices",
    "9403.20": "Other metal furniture",
    "9403.30": "Wooden furniture of a kind used in offices",
    "9403.40": "Wooden furniture of a kind used in the kitchen",
    "9403.50": "Wooden furniture of a kind used in the bedroom",
    "9403.60": "Other wooden furniture (incl. dining tables, living-room furniture)",
    "9403.70": "Furniture of plastics",
    "9403.82": "Furniture of bamboo", "9403.83": "Furniture of rattan",
    "9403.89": "Furniture of other materials (glass, stone, etc.)",
    "9404.21": "Mattresses of cellular rubber or plastics",
    "9404.29": "Mattresses of other materials",
}

WOOD = {"wood", "wooden", "solid wood", "mdf", "chipboard", "particleboard", "plywood", "veneer", "oak", "walnut", "beech", "ahşap", "masif"}
METAL = {"metal", "steel", "iron", "aluminium", "aluminum", "metal frame", "çelik"}
PLASTIC = {"plastic", "polypropylene", "pp", "acrylic", "polycarbonate", "plastik"}


@dataclass
class HSSuggestion:
    code: str
    description: str
    confidence: float
    reasoning: str


def _material_class(materials: list[str]) -> str:
    m = {x.strip().lower() for x in materials}
    if m & WOOD:
        return "wood"
    if m & METAL:
        return "metal"
    if m & PLASTIC:
        return "plastic"
    if m & {"bamboo"}:
        return "bamboo"
    if m & {"rattan", "wicker"}:
        return "rattan"
    if m & {"glass", "marble", "stone", "ceramic"}:
        return "other"
    return "unknown"


def suggest_hs_codes(category: str, materials: list[str] | None = None, upholstered: bool | None = None,
                     swivel: bool = False, convertible: bool = False) -> list[HSSuggestion]:
    materials = materials or []
    mc = _material_class(materials)
    out: list[HSSuggestion] = []

    def add(code: str, conf: float, why: str) -> None:
        out.append(HSSuggestion(code, HS_DESCRIPTIONS[code], conf, why))

    seat_like = category in {"chair", "sofa", "armchair"} or (category in {"office_furniture"} and swivel)
    if seat_like:
        if swivel:
            add("9401.31" if mc == "wood" else "9401.39", 0.8, "swivel, height-adjustable seat")
        elif convertible:
            add("9401.41" if mc == "wood" else "9401.49", 0.8, "seat convertible into bed")
        elif mc == "wood":
            up = upholstered if upholstered is not None else category in {"sofa", "armchair"}
            add("9401.61" if up else "9401.69", 0.85 if upholstered is not None else 0.6,
                f"wooden frame, {'upholstered' if up else 'not upholstered'}"
                + ("" if upholstered is not None else " (upholstery assumed from category)"))
        elif mc == "metal":
            up = upholstered if upholstered is not None else category in {"sofa", "armchair"}
            add("9401.71" if up else "9401.79", 0.85 if upholstered is not None else 0.6, f"metal frame, {'upholstered' if up else 'not upholstered'}")
        elif mc == "bamboo":
            add("9401.52", 0.8, "bamboo seat")
        elif mc == "rattan":
            add("9401.53", 0.8, "rattan seat")
        elif mc == "plastic":
            add("9401.80", 0.75, "plastic seat")
        else:
            add("9401.61", 0.35, "frame material unknown — confirm"); add("9401.71", 0.3, "frame material unknown — confirm")
        return out

    if category == "mattress":
        add("9404.21" if "foam" in [m.lower() for m in materials] else "9404.29", 0.6, "mattress")
        return out

    room = {"office_furniture": "office", "kitchen_furniture": "kitchen", "bed": "bedroom", "cabinet": "other",
            "dining_table": "other", "hotel_furniture": "other", "restaurant_furniture": "other",
            "outdoor_furniture": "other", "home_furniture": "other"}.get(category, "other")
    if mc == "wood":
        code = {"office": "9403.30", "kitchen": "9403.40", "bedroom": "9403.50"}.get(room, "9403.60")
        add(code, 0.85, f"wooden furniture, {room} use")
    elif mc == "metal":
        add("9403.10" if room == "office" else "9403.20", 0.85, f"metal furniture, {room} use")
    elif mc == "plastic":
        add("9403.70", 0.8, "plastic furniture")
    elif mc == "bamboo":
        add("9403.82", 0.8, "bamboo furniture")
    elif mc == "rattan":
        add("9403.83", 0.8, "rattan furniture")
    elif mc == "other":
        add("9403.89", 0.7, "other material (glass/stone)")
    else:
        add("9403.60", 0.35, "material unknown — wooden assumed; confirm")
        add("9403.20", 0.3, "material unknown — metal alternative; confirm")
    return out
