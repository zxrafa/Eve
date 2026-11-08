STAGES = ("vertex", "tess-control", "tess-eval", "geometry", "fragment", "compute",
          "vertex-a", "task", "mesh")
GAMES = {
    "040074a01bf12000": "Donkey Kong Bananza",
    "040077201be50000": "Kirby Air Riders",
    "04007c6028aa8000": "Yoshi demo",
    "04007ef01f8ae000": "Fire Emblem: Fortune's Weave",
    "0400c3f00006e000": "Mario Kart World",
    "04008e001f098000": "Nintendo Switch Sports Resort",
    "0400a3a01ee4c000": "Pokémon Pokopia",
    "0400a4802437e000": "Drag x Drive Global Jam",
    "040041e0212ae000": "Fast Fusion",
    "04005b902517c000": "Kirby Air Riders Global Test Ride",
    "040057c02159a000": "Nintendo Switch 2 Welcome Tour",
    "040004f027560000": "Orbitals Global Friends Pass",
    "0400380020056000": "Raiders",
    "0400d1d02399a000": "The Duskbloods network test",
    "0400d4201c6ea000": "Mario Tennis Fever",
    "0400e88025b1a000": "Star Fox",
}
MAP_MAGIC = 0x50414D4E4544454E
GRAPHICS_KEY_SIZE = 1056


class CacheError(ValueError):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()
