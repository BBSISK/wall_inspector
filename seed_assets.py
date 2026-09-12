import urllib.request
import ssl
import os

# Bypass macOS missing CA bundle error
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

WALLS_METADATA = [
    {
        "filename": "drystone_01.jpg",
        "url": "https://images.pexels.com/photos/2873671/pexels-photo-2873671.jpeg?auto=compress&cs=tinysrgb&w=1200",
        "title": "Traditional Irish Dry Stone Field Boundary"
    },
    {
        "filename": "drystone_02.jpg",
        "url": "https://images.pexels.com/photos/1029604/pexels-photo-1029604.jpeg?auto=compress&cs=tinysrgb&w=1200",
        "title": "Rustic Field Stone Retaining Dyke"
    },
    {
        "filename": "brick_efflorescence_01.jpg",
        "url": "https://images.pexels.com/photos/207142/pexels-photo-207142.jpeg?auto=compress&cs=tinysrgb&w=1200",
        "title": "Industrial Red Brick Cavity Wall"
    },
    {
        "filename": "stone_rubble_01.jpg",
        "url": "https://images.pexels.com/photos/2440024/pexels-photo-2440024.jpeg?auto=compress&cs=tinysrgb&w=1200",
        "title": "Historic Lime-Mortared Rubble Wall"
    },
    {
        "filename": "brick_crack_01.jpg",
        "url": "https://images.pexels.com/photos/159358/brick-wall-bricks-masonry-texture-159358.jpeg?auto=compress&cs=tinysrgb&w=1200",
        "title": "Differential Settlement Stepped Crack"
    },
    {
        "filename": "drystone_aran_01.jpg",
        "url": "https://images.pexels.com/photos/2387873/pexels-photo-2387873.jpeg?auto=compress&cs=tinysrgb&w=1200",
        "title": "Limestone Karst Dry Boundary"
    },
    {
        "filename": "stone_bulge_01.jpg",
        "url": "https://images.pexels.com/photos/2260783/pexels-photo-2260783.jpeg?auto=compress&cs=tinysrgb&w=1200",
        "title": "Granite Field Dyke with Subsidence"
    },
    {
        "filename": "ashlar_cracking_01.jpg",
        "url": "https://images.pexels.com/photos/2440009/pexels-photo-2440009.jpeg?auto=compress&cs=tinysrgb&w=1200",
        "title": "Dressed Ashlar Masonry Parapet"
    },
    {
        "filename": "old_brick_decay_01.jpg",
        "url": "https://images.pexels.com/photos/207300/pexels-photo-207300.jpeg?auto=compress&cs=tinysrgb&w=1200",
        "title": "Aged Factory Boundary with Spalling"
    },
    {
        "filename": "retaining_drystone_01.jpg",
        "url": "https://images.pexels.com/photos/1029618/pexels-photo-1029618.jpeg?auto=compress&cs=tinysrgb&w=1200",
        "title": "Terraced Dry Stone Retaining Boundary"
    },
    {
        "filename": "lime_coursed_01.jpg",
        "url": "https://images.pexels.com/photos/326240/pexels-photo-326240.jpeg?auto=compress&cs=tinysrgb&w=1200",
        "title": "Coursed Limestone Farm Wall"
    },
    {
        "filename": "modern_brick_damage_01.jpg",
        "url": "https://images.pexels.com/photos/1098982/pexels-photo-1098982.jpeg?auto=compress&cs=tinysrgb&w=1200",
        "title": "Perimeter Brick Wall with Joint Separation"
    }
]

dest_dir = "static/img/walls"
os.makedirs(dest_dir, exist_ok=True)
headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}

print(f"Downloading {len(WALLS_METADATA)} authentic wall assets...")
for item in WALLS_METADATA:
    filepath = os.path.join(dest_dir, item["filename"])
    print(f"  Fetching: {item['filename']} ({item['title']})")
    req = urllib.request.Request(item["url"], headers=headers)
    try:
        with urllib.request.urlopen(req, context=ctx) as resp, open(filepath, "wb") as f:
            f.write(resp.read())
    except Exception as e:
        print(f"    Failed: {e}")

print("All wall images downloaded successfully.")
