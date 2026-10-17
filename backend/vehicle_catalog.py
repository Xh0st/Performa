import re
from datetime import date
import httpx

MAKES = {
    "Alfa Romeo": ["Giulia", "Giulietta", "Stelvio", "Tonale", "159", "MiTo"],
    "Audi": ["A1", "A3", "A4", "A5", "A6", "A7", "A8", "Q2", "Q3", "Q5", "Q7", "Q8", "e-tron", "TT"],
    "BMW": ["Seria 1", "Seria 2", "Seria 3", "Seria 4", "Seria 5", "Seria 7", "X1", "X2", "X3", "X4", "X5", "X6", "X7", "i3", "iX"],
    "Chevrolet": ["Aveo", "Captiva", "Cruze", "Spark"],
    "Citroën": ["C1", "C3", "C3 Aircross", "C4", "C5 Aircross", "Berlingo", "Jumper", "Jumpy"],
    "Cupra": ["Born", "Formentor", "Leon"],
    "Dacia": ["Logan", "Sandero", "Sandero Stepway", "Duster", "Jogger", "Spring", "Lodgy", "Dokker", "Bigster"],
    "Fiat": ["500", "500X", "Doblo", "Ducato", "Panda", "Punto", "Tipo"],
    "Ford": ["Fiesta", "Focus", "Mondeo", "Kuga", "Puma", "EcoSport", "Mustang Mach-E", "Ranger", "Transit", "Transit Custom", "Transit Connect", "Galaxy", "S-Max"],
    "Honda": ["Civic", "CR-V", "HR-V", "Jazz", "Accord"],
    "Hyundai": ["i10", "i20", "i30", "Bayon", "Kona", "Tucson", "Santa Fe", "Ioniq 5", "ix35"],
    "Jaguar": ["E-Pace", "F-Pace", "XE", "XF"],
    "Jeep": ["Compass", "Renegade", "Grand Cherokee", "Wrangler"],
    "Kia": ["Picanto", "Rio", "Ceed", "XCeed", "Stonic", "Sportage", "Sorento", "Niro", "EV6"],
    "Land Rover": ["Defender", "Discovery", "Discovery Sport", "Range Rover", "Range Rover Evoque", "Range Rover Sport", "Range Rover Velar"],
    "Lexus": ["NX", "RX", "UX", "ES", "IS"],
    "Mazda": ["Mazda2", "Mazda3", "Mazda6", "CX-3", "CX-30", "CX-5", "CX-60", "MX-5"],
    "Mercedes-Benz": ["Clasa A", "Clasa B", "Clasa C", "Clasa E", "Clasa S", "CLA", "GLA", "GLB", "GLC", "GLE", "GLS", "Vito", "Sprinter", "Citan", "EQA", "EQC"],
    "Mini": ["Cooper", "Countryman", "Clubman"],
    "Mitsubishi": ["ASX", "Outlander", "Eclipse Cross", "L200", "Space Star"],
    "Nissan": ["Micra", "Juke", "Qashqai", "X-Trail", "Leaf", "Navara", "Note"],
    "Opel": ["Corsa", "Astra", "Insignia", "Mokka", "Crossland", "Grandland", "Zafira", "Vivaro", "Movano", "Combo"],
    "Peugeot": ["208", "2008", "308", "3008", "408", "508", "5008", "Partner", "Expert", "Boxer", "Rifter"],
    "Porsche": ["911", "Cayenne", "Macan", "Panamera", "Taycan"],
    "Renault": ["Clio", "Captur", "Megane", "Arkana", "Austral", "Kadjar", "Koleos", "Scenic", "Talisman", "Zoe", "Kangoo", "Trafic", "Master"],
    "Seat": ["Ibiza", "Leon", "Arona", "Ateca", "Tarraco", "Alhambra"],
    "Skoda": ["Fabia", "Scala", "Octavia", "Superb", "Kamiq", "Karoq", "Kodiaq", "Enyaq", "Rapid", "Yeti"],
    "Smart": ["ForTwo", "ForFour", "#1"],
    "Subaru": ["Forester", "Outback", "XV", "Impreza"],
    "Suzuki": ["Swift", "Vitara", "S-Cross", "Ignis", "Jimny", "SX4"],
    "Tesla": ["Model 3", "Model Y", "Model S", "Model X"],
    "Toyota": ["Aygo", "Yaris", "Yaris Cross", "Corolla", "C-HR", "RAV4", "Camry", "Auris", "Avensis", "Land Cruiser", "Hilux", "Proace"],
    "Volkswagen": ["Polo", "Golf", "Passat", "Arteon", "T-Roc", "T-Cross", "Tiguan", "Touareg", "Touran", "Sharan", "ID.3", "ID.4", "Caddy", "Transporter", "Crafter", "Amarok", "Up!"],
    "Volvo": ["XC40", "XC60", "XC90", "S60", "S90", "V40", "V60", "V90"],
}

WMI = {
    "WVW": "Volkswagen", "WV1": "Volkswagen", "WV2": "Volkswagen", "WV3": "Volkswagen", "WAU": "Audi", "WUA": "Audi", "TRU": "Audi",
    "WBA": "BMW", "WBS": "BMW", "WBY": "BMW", "WMW": "Mini", "WDB": "Mercedes-Benz", "WDD": "Mercedes-Benz", "WDC": "Mercedes-Benz",
    "WDF": "Mercedes-Benz", "W1K": "Mercedes-Benz", "W1N": "Mercedes-Benz", "W1V": "Mercedes-Benz", "WME": "Smart", "TMB": "Skoda",
    "UU1": "Dacia", "UU6": "Dacia", "VF1": "Renault", "VF6": "Renault", "VF3": "Peugeot", "VR3": "Peugeot", "VF7": "Citroën", "VR7": "Citroën",
    "WF0": "Ford", "WF1": "Ford", "ZFA": "Fiat", "ZFF": "Fiat", "ZAR": "Alfa Romeo", "ZAC": "Jeep", "1C4": "Jeep", "SAL": "Land Rover",
    "SAJ": "Jaguar", "YV1": "Volvo", "YV4": "Volvo", "VSS": "Seat", "KNA": "Kia", "KNE": "Kia", "U5Y": "Kia", "U6Y": "Kia", "KMH": "Hyundai",
    "TMA": "Hyundai", "NLH": "Hyundai", "JTD": "Toyota", "JTE": "Toyota", "JTN": "Toyota", "SB1": "Toyota", "VNK": "Toyota", "NMT": "Toyota",
    "JTH": "Lexus", "JMZ": "Mazda", "JM1": "Mazda", "JN1": "Nissan", "SJN": "Nissan", "VSK": "Nissan", "W0L": "Opel", "W0V": "Opel",
    "JHM": "Honda", "SHH": "Honda", "JSA": "Suzuki", "TSM": "Suzuki", "JMB": "Mitsubishi", "JMY": "Mitsubishi", "WP0": "Porsche",
    "WP1": "Porsche", "5YJ": "Tesla", "LRW": "Tesla", "XP7": "Tesla", "JF1": "Subaru", "KL1": "Chevrolet",
}

YEAR_CODES = "ABCDEFGHJKLMNPRSTVWXY123456789"
VAG_MODELS = {
    "Volkswagen": {"AU": "Golf", "5G": "Golf", "1K": "Golf", "CD": "Golf", "3C": "Passat", "3G": "Passat", "5N": "Tiguan", "AD": "Tiguan",
                   "6R": "Polo", "AW": "Polo", "7H": "Transporter", "7E": "Transporter", "2K": "Caddy", "5T": "Touran", "A1": "T-Roc"},
    "Skoda": {"NE": "Octavia", "5E": "Octavia", "1Z": "Octavia", "NX": "Octavia", "3V": "Superb", "3T": "Superb", "NJ": "Fabia",
              "PJ": "Fabia", "NS": "Kodiaq", "NU": "Karoq", "NW": "Scala"},
    "Audi": {"8V": "A3", "8Y": "A3", "8W": "A4", "8K": "A4", "4G": "A6", "4K": "A6", "8U": "Q3", "F3": "Q3", "FY": "Q5", "8R": "Q5", "4M": "Q7"},
    "Seat": {"5F": "Leon", "KL": "Leon", "6J": "Ibiza", "KJ": "Ibiza"},
}
FUEL_MAP = {"diesel": "diesel", "gasoline": "benzina", "electric": "electric", "lpg": "gpl", "hybrid": "hibrid"}
VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")


def canonical_make(raw: str) -> str:
    if not raw:
        return ""
    low = raw.strip().lower().replace("-", " ")
    for m in MAKES:
        if m.lower().replace("-", " ") == low or (low.startswith(m.lower().split()[0]) and len(m.split()) == 1):
            return m
    return raw.strip().title()


def canonical_model(make: str, raw: str) -> str:
    if not raw:
        return ""
    low = raw.strip().lower()
    for m in MAKES.get(make, []):
        if m.lower() == low or m.lower().replace("seria ", "") == low:
            return m
    return raw.strip()


def year_from_code(c: str):
    if c not in YEAR_CODES:
        return None
    i = YEAR_CODES.index(c)
    for base in (2010, 1980):
        y = base + i
        if y <= date.today().year + 1:
            return y
    return None


async def decode_vin(vin: str) -> dict:
    vin = vin.strip().upper()
    out = {"vin": vin, "make": WMI.get(vin[:3], ""), "model": "", "year": year_from_code(vin[9]) if len(vin) == 17 else None,
           "engine": "", "power_kw": None, "fuel": "", "source": "wmi", "warnings": []}
    out["model"] = VAG_MODELS.get(out["make"], {}).get(vin[6:8], "")
    if not VIN_RE.fullmatch(vin):
        out["warnings"].append("VIN invalid: 17 caractere, fără I, O, Q")
        return out
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=3.0)) as c:
            r = await c.get(f"https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/{vin}", params={"format": "json"})
            r.raise_for_status()
            raw = (r.json().get("Results") or [{}])[0]
        make = canonical_make(raw.get("Make", ""))
        if make:
            out["make"] = make
            out["source"] = "nhtsa"
        out["model"] = canonical_model(out["make"], raw.get("Model", "")) or out["model"]
        if make and (raw.get("ModelYear") or "").isdigit():
            out["year"] = int(raw["ModelYear"])
        disp = raw.get("DisplacementL") or ""
        out["engine"] = " ".join(x for x in [f"{float(disp):.1f}" if disp else "", raw.get("EngineModel") or ""] if x)
        kw = raw.get("EngineKW") or ""
        hp = raw.get("EngineHP") or ""
        out["power_kw"] = round(float(kw)) if kw else (round(float(hp) * 0.7355) if hp else None)
        fuel = (raw.get("FuelTypePrimary") or "").lower()
        out["fuel"] = next((v for k, v in FUEL_MAP.items() if k in fuel), "")
        if (raw.get("ElectrificationLevel") or "").lower().find("hybrid") >= 0:
            out["fuel"] = "hibrid"
    except (httpx.HTTPError, ValueError, KeyError):
        out["warnings"].append("Decodorul online indisponibil – date parțiale (WMI)")
    return out
