#!/usr/bin/env python3
"""
generate_gallery.py
Generates a realistic, authentic gallery of photos, screenshots, and WhatsApp images
specifically tailored for a retail Samsung Galaxy S24 Ultra (SM-S928B) on Android 14.
Populates:
  - /sdcard/DCIM/Camera/ (60+ photos with S24 Ultra EXIF + GPS + timestamps)
  - /sdcard/DCIM/Screenshots/ (15 realistic UI screenshots in 1440x3120)
  - /sdcard/Pictures/WhatsApp/ (20 realistic WhatsApp shared media)
"""

import os
import random
import math
import subprocess
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFilter, ImageFont
import piexif

OUTPUT_BASE = "/tmp/fake_gallery"

def ensure_dirs():
    os.makedirs(f"{OUTPUT_BASE}/DCIM/Camera", exist_ok=True)
    os.makedirs(f"{OUTPUT_BASE}/DCIM/Screenshots", exist_ok=True)
    os.makedirs(f"{OUTPUT_BASE}/Pictures/WhatsApp", exist_ok=True)

def deg_to_dms_rational(deg):
    d = int(deg)
    m = int((deg - d) * 60)
    s = int(round(((deg - d) * 60 - m) * 60 * 100))
    return ((d, 1), (m, 1), (s, 100))

def build_exif(dt, lat=None, lon=None, lens_type='main'):
    dt_str = dt.strftime("%Y:%m:%d %H:%M:%S")
    zeroth_ifd = {
        piexif.ImageIFD.Make: "samsung",
        piexif.ImageIFD.Model: "SM-S928B",
        piexif.ImageIFD.Software: "S928BXXU1AXCA",
        piexif.ImageIFD.DateTime: dt_str,
        piexif.ImageIFD.Orientation: 1,
    }
    
    if lens_type == 'wide':
        focal_length = (22, 10) # 2.2mm
        f_num = (22, 10) # f/2.2
        iso = random.choice([50, 64, 80, 100])
        exp_time = (1, random.choice([100, 200, 400, 800]))
    elif lens_type == 'tele':
        focal_length = (186, 10) # 18.6mm
        f_num = (34, 10) # f/3.4
        iso = random.choice([100, 160, 250, 400])
        exp_time = (1, random.choice([250, 500, 1000]))
    else: # main
        focal_length = (63, 10) # 6.3mm
        f_num = (17, 10) # f/1.7
        iso = random.choice([50, 80, 100, 125, 200, 400])
        exp_time = (1, random.choice([50, 100, 125, 250, 500]))
        
    exif_ifd = {
        piexif.ExifIFD.DateTimeOriginal: dt_str,
        piexif.ExifIFD.DateTimeDigitized: dt_str,
        piexif.ExifIFD.ExposureTime: exp_time,
        piexif.ExifIFD.FNumber: f_num,
        piexif.ExifIFD.ISOSpeedRatings: iso,
        piexif.ExifIFD.FocalLength: focal_length,
        piexif.ExifIFD.FocalLengthIn35mmFilm: 23 if lens_type == 'main' else (13 if lens_type == 'wide' else 115),
        piexif.ExifIFD.Flash: 0,
        piexif.ExifIFD.WhiteBalance: 0,
        piexif.ExifIFD.ColorSpace: 1,
        piexif.ExifIFD.ExposureMode: 0,
    }
    
    gps_ifd = {}
    if lat and lon:
        gps_ifd = {
            piexif.GPSIFD.GPSLatitudeRef: 'N',
            piexif.GPSIFD.GPSLatitude: deg_to_dms_rational(lat),
            piexif.GPSIFD.GPSLongitudeRef: 'E',
            piexif.GPSIFD.GPSLongitude: deg_to_dms_rational(lon),
            piexif.GPSIFD.GPSAltitude: (random.randint(180, 240), 1),
            piexif.GPSIFD.GPSTimeStamp: ((dt.hour, 1), (dt.minute, 1), (dt.second, 1)),
            piexif.GPSIFD.GPSDateStamp: dt.strftime("%Y:%m:%d")
        }
        
    return piexif.dump({'0th': zeroth_ifd, 'Exif': exif_ifd, 'GPS': gps_ifd, '1st': {}, 'thumbnail': None})

# Procedural image generators
def draw_landscape(w, h):
    im = Image.new('RGB', (w, h))
    draw = ImageDraw.Draw(im)
    # Sky gradient
    sky_top = (random.randint(40, 90), random.randint(110, 160), random.randint(200, 245))
    sky_bot = (random.randint(140, 200), random.randint(180, 220), random.randint(230, 255))
    horizon_y = int(h * random.uniform(0.5, 0.65))
    for y in range(horizon_y):
        t = y / max(1, horizon_y)
        r = int(sky_top[0] * (1-t) + sky_bot[0] * t)
        g = int(sky_top[1] * (1-t) + sky_bot[1] * t)
        b = int(sky_top[2] * (1-t) + sky_bot[2] * t)
        draw.line([(0, y), (w, y)], fill=(r, g, b))
    # Sun / light glow
    sun_x = random.randint(int(w*0.2), int(w*0.8))
    sun_y = random.randint(int(horizon_y*0.2), int(horizon_y*0.8))
    draw.ellipse([sun_x-40, sun_y-40, sun_x+40, sun_y+40], fill=(255, 250, 220))
    # Hills / Mountains
    hill_color = (random.randint(50, 90), random.randint(100, 140), random.randint(40, 80))
    points = [(0, horizon_y)]
    for x in range(0, w + 50, 40):
        y = horizon_y - int(30 * math.sin(x * 0.01) + 20 * math.cos(x * 0.03))
        points.append((x, y))
    points.append((w, h))
    points.append((0, h))
    draw.polygon(points, fill=hill_color)
    # Ground gradient
    ground_color = (random.randint(70, 120), random.randint(120, 160), random.randint(50, 80))
    for y in range(horizon_y, h):
        t = (y - horizon_y) / max(1, h - horizon_y)
        r = int(hill_color[0] * (1-t) + ground_color[0] * t)
        g = int(hill_color[1] * (1-t) + ground_color[1] * t)
        b = int(hill_color[2] * (1-t) + ground_color[2] * t)
        draw.line([(0, y), (w, y)], fill=(r, g, b))
    return im.filter(ImageFilter.GaussianBlur(radius=0.5))

def draw_indoor_cafe(w, h):
    im = Image.new('RGB', (w, h))
    draw = ImageDraw.Draw(im)
    # Warm indoor ambient gradient
    top_c = (random.randint(80, 120), random.randint(60, 90), random.randint(40, 70))
    bot_c = (random.randint(160, 210), random.randint(130, 170), random.randint(90, 130))
    for y in range(h):
        t = y / h
        r = int(top_c[0] * (1-t) + bot_c[0] * t)
        g = int(top_c[1] * (1-t) + bot_c[1] * t)
        b = int(top_c[2] * (1-t) + bot_c[2] * t)
        draw.line([(0, y), (w, y)], fill=(r, g, b))
    # Table top
    table_y = int(h * 0.6)
    table_c = (random.randint(140, 180), random.randint(100, 140), random.randint(70, 100))
    draw.rectangle([0, table_y, w, h], fill=table_c)
    # Cup / coffee plate
    cup_x = int(w * 0.5)
    cup_y = int(h * 0.75)
    draw.ellipse([cup_x-120, cup_y-50, cup_x+120, cup_y+50], fill=(240, 240, 240))
    draw.ellipse([cup_x-90, cup_y-35, cup_x+90, cup_y+35], fill=(90, 50, 30))
    draw.ellipse([cup_x-60, cup_y-25, cup_x+60, cup_y+25], fill=(160, 110, 70))
    return im.filter(ImageFilter.GaussianBlur(radius=0.8))

def draw_city_street(w, h):
    im = Image.new('RGB', (w, h))
    draw = ImageDraw.Draw(im)
    # Sky
    sky_c = (random.randint(100, 160), random.randint(130, 180), random.randint(180, 220))
    draw.rectangle([0, 0, w, int(h*0.5)], fill=sky_c)
    # Buildings
    for _ in range(8):
        bx = random.randint(0, w - 100)
        bw = random.randint(80, 220)
        bh = random.randint(int(h*0.25), int(h*0.55))
        b_color = (random.randint(90, 140), random.randint(100, 150), random.randint(110, 160))
        draw.rectangle([bx, int(h*0.5) - bh, bx + bw, int(h*0.5)], fill=b_color)
        # Windows
        for wy in range(int(h*0.5) - bh + 20, int(h*0.5) - 20, 25):
            for wx in range(bx + 15, bx + bw - 15, 25):
                draw.rectangle([wx, wy, wx+12, wy+12], fill=(230, 240, 255))
    # Road
    road_c = (50, 52, 58)
    draw.rectangle([0, int(h*0.5), w, h], fill=road_c)
    # Road markings
    draw.line([(int(w*0.5), int(h*0.5)), (int(w*0.5), h)], fill=(230, 210, 50), width=6)
    return im.filter(ImageFilter.GaussianBlur(radius=0.6))

def draw_document_notes(w, h):
    im = Image.new('RGB', (w, h), color=(245, 245, 240))
    draw = ImageDraw.Draw(im)
    # Desk background
    desk_c = (random.randint(160, 190), random.randint(120, 150), random.randint(90, 120))
    draw.rectangle([0, 0, w, h], fill=desk_c)
    # White paper sheet
    px = int(w * 0.15)
    py = int(h * 0.12)
    pw = int(w * 0.7)
    ph = int(h * 0.76)
    draw.rectangle([px, py, px+pw, py+ph], fill=(255, 255, 253))
    # Ruled lines or text shapes
    for ly in range(py + 40, py + ph - 30, 28):
        draw.line([(px + 30, ly), (px + pw - 30, ly)], fill=(210, 220, 235), width=2)
        # Simulated handwriting ink
        ink_len = random.randint(int(pw * 0.3), int(pw * 0.8))
        draw.line([(px + 35, ly - 4), (px + 35 + ink_len, ly - 4)], fill=(random.randint(20, 50), random.randint(30, 70), random.randint(100, 160)), width=2)
    return im.filter(ImageFilter.GaussianBlur(radius=0.5))

def draw_sunset_sky(w, h):
    im = Image.new('RGB', (w, h))
    draw = ImageDraw.Draw(im)
    colors = [
        (40, 20, 70),
        (120, 30, 80),
        (210, 60, 50),
        (245, 140, 40),
        (255, 210, 90)
    ]
    for y in range(h):
        t = y / h
        idx = min(len(colors)-2, int(t * (len(colors)-1)))
        sub_t = (t * (len(colors)-1)) - idx
        c1 = colors[idx]
        c2 = colors[idx+1]
        r = int(c1[0]*(1-sub_t) + c2[0]*sub_t)
        g = int(c1[1]*(1-sub_t) + c2[1]*sub_t)
        b = int(c1[2]*(1-sub_t) + c2[2]*sub_t)
        draw.line([(0, y), (w, y)], fill=(r, g, b))
    # Horizon silhouette
    draw.rectangle([0, int(h*0.82), w, h], fill=(20, 15, 25))
    return im.filter(ImageFilter.GaussianBlur(radius=0.5))

def draw_screenshot_ui(w, h, app_type="upi"):
    im = Image.new('RGB', (w, h), color=(255, 255, 255))
    draw = ImageDraw.Draw(im)
    # Status bar
    draw.rectangle([0, 0, w, 90], fill=(245, 245, 247))
    # Header bar
    if app_type == "upi":
        header_color = (13, 110, 253) # Google Pay / PhonePe blue
        title = "Payment Successful"
    elif app_type == "delivery":
        header_color = (252, 128, 25) # Swiggy orange
        title = "Order Delivered"
    else:
        header_color = (18, 140, 126) # WhatsApp green
        title = "Chat"
        
    draw.rectangle([0, 90, w, 240], fill=header_color)
    # Card container
    draw.rectangle([60, 320, w - 60, 900], fill=(248, 249, 250), outline=(220, 224, 230), width=3)
    # Large checkmark / status circle
    draw.ellipse([int(w/2) - 80, 400, int(w/2) + 80, 560], fill=header_color)
    # Details rows
    draw.rectangle([100, 640, w - 100, 670], fill=(180, 185, 195))
    draw.rectangle([100, 710, w - 180, 735], fill=(200, 205, 215))
    draw.rectangle([100, 770, w - 140, 795], fill=(200, 205, 215))
    draw.rectangle([100, 830, w - 220, 855], fill=(200, 205, 215))
    # Bottom action button
    draw.rectangle([60, 1050, w - 60, 1180], fill=header_color)
    # Navigation bar
    draw.rectangle([0, h - 80, w, h], fill=(245, 245, 247))
    draw.rectangle([int(w/2) - 150, h - 45, int(w/2) + 150, h - 35], fill=(60, 60, 60))
    return im

def generate_all():
    ensure_dirs()
    print("Generating photos...")
    
    # 150 days timeline: from May 15, 2026 to October 10, 2026
    start_date = datetime(2026, 5, 15, 9, 30, 0)
    current_dt = start_date
    
    # Coordinates in Delhi NCR / Noida (around 28.53 - 28.62 N, 77.30 - 77.42 E)
    base_lat = 28.5765
    base_lon = 77.3304
    
    photo_count = 65
    for i in range(photo_count):
        # advance time 1 to 4 days
        hours_jump = random.randint(18, 72)
        current_dt += timedelta(hours=hours_jump, minutes=random.randint(5, 55), seconds=random.randint(0, 59))
        if current_dt > datetime(2026, 10, 10, 23, 0, 0):
            current_dt = datetime(2026, 10, 10, 18, random.randint(10, 50), random.randint(0, 59))
            
        style = random.choice(['landscape', 'cafe', 'city', 'doc', 'sunset'])
        # aspect ratio
        if random.random() < 0.7:
            w, h = 2048, 1536 # 4:3
        else:
            w, h = 1920, 1080 # 16:9
            
        if style == 'landscape':
            im = draw_landscape(w, h)
            lens = 'wide'
        elif style == 'cafe':
            im = draw_indoor_cafe(w, h)
            lens = 'main'
        elif style == 'city':
            im = draw_city_street(w, h)
            lens = 'main'
        elif style == 'doc':
            im = draw_document_notes(w, h)
            lens = 'main'
        else:
            im = draw_sunset_sky(w, h)
            lens = 'tele'
            
        lat = base_lat + random.uniform(-0.05, 0.05)
        lon = base_lon + random.uniform(-0.05, 0.05)
        exif_bytes = build_exif(current_dt, lat, lon, lens)
        
        filename = f"{current_dt.strftime('%Y%m%d_%H%M%S')}.jpg"
        filepath = f"{OUTPUT_BASE}/DCIM/Camera/{filename}"
        im.save(filepath, "JPEG", quality=90, exif=exif_bytes)
        
        # update file access/modified times
        mtime = current_dt.timestamp()
        os.utime(filepath, (mtime, mtime))
        
    print(f"Generated {photo_count} camera photos in DCIM/Camera.")
    
    # Screenshots
    print("Generating screenshots...")
    ss_dt = datetime(2026, 6, 1, 12, 0, 0)
    for i in range(15):
        ss_dt += timedelta(days=random.randint(6, 10), hours=random.randint(1, 6), minutes=random.randint(1, 40))
        if ss_dt > datetime(2026, 10, 10, 22, 0, 0):
            ss_dt = datetime(2026, 10, 10, 14, 0, 0)
            
        app_t = random.choice(["upi", "delivery", "chat"])
        # Screen resolution of device: 1440x3120
        im = draw_screenshot_ui(1440, 3120, app_t)
        filename = f"Screenshot_{ss_dt.strftime('%Y%m%d_%H%M%S')}.jpg"
        filepath = f"{OUTPUT_BASE}/DCIM/Screenshots/{filename}"
        im.save(filepath, "JPEG", quality=88)
        mtime = ss_dt.timestamp()
        os.utime(filepath, (mtime, mtime))
        
    print("Generated 15 screenshots in DCIM/Screenshots.")
    
    # WhatsApp Images (WhatsApp format: IMG-YYYYMMDD-WA000X.jpg, no EXIF)
    print("Generating WhatsApp images...")
    wa_dt = datetime(2026, 5, 20, 10, 0, 0)
    for i in range(20):
        wa_dt += timedelta(days=random.randint(4, 8), hours=random.randint(1, 5))
        if wa_dt > datetime(2026, 10, 10, 20, 0, 0):
            wa_dt = datetime(2026, 10, 10, 16, 0, 0)
        im = draw_indoor_cafe(1280, 960) if random.random() < 0.5 else draw_sunset_sky(1280, 960)
        filename = f"IMG-{wa_dt.strftime('%Y%m%d')}-WA{i+1:04d}.jpg"
        filepath = f"{OUTPUT_BASE}/Pictures/WhatsApp/{filename}"
        im.save(filepath, "JPEG", quality=85)
        mtime = wa_dt.timestamp()
        os.utime(filepath, (mtime, mtime))
        
    print("Generated 20 WhatsApp images in Pictures/WhatsApp.")

if __name__ == "__main__":
    generate_all()
