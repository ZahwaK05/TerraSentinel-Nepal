"""
Quick check: what Sentinel-1 collections does the Copernicus STAC server have,
and what does one scene look like? No password needed. Downloads nothing.

Run:  python sentinel1\probe_s1.py
"""
from pystac_client import Client

STAC_URL = "https://catalogue.dataspace.copernicus.eu/stac"
BBOX = (85.45, 27.75, 85.75, 28.05)  # Melamchi

cat = Client.open(STAC_URL)

names = [c.id for c in cat.get_collections()]
print("ALL COLLECTIONS:")
for n in names:
    print("  ", n)

s1 = [n for n in names if "sentinel-1" in n.lower() or "sentinel1" in n.lower()]
print("\nSENTINEL-1 COLLECTIONS:", s1)

for name in s1:
    print("\n==========", name, "==========")
    try:
        search = cat.search(
            collections=[name],
            bbox=BBOX,
            datetime="2021-06-01/2021-06-20",
            max_items=1,
        )
        items = list(search.items())
    except Exception as e:
        print("Search failed:", repr(e)[:300])
        continue
    if not items:
        print("No scene found for this window.")
        continue
    item = items[0]
    print("Scene id:", item.id)
    print("Properties:")
    for k, v in item.properties.items():
        print("   ", k, "=", str(v)[:80])
    print("Assets:")
    for k, a in item.assets.items():
        print("   ", k, "|", a.media_type, "|", str(a.href)[:110])
