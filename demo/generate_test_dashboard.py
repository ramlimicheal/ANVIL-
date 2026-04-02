"""Generate a synthetic dark crypto dashboard image for ANVIL demo."""
import sys
sys.path.insert(0, "/Users/apple/Desktop/Alpha/ANVIL/.venv/lib/python3.14/site-packages")

import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 800
bg = (10, 15, 28)        # Dark navy
sidebar_bg = (14, 20, 36)
card_bg = (18, 26, 46)
accent = (94, 106, 210)  # Purple-blue accent
green = (0, 200, 120)
red = (220, 60, 80)
text_w = (240, 245, 250)
text_dim = (120, 130, 150)
border = (30, 40, 60)

img = Image.new("RGB", (W, H), bg)
draw = ImageDraw.Draw(img)

# Try to load a font, fall back to default
try:
    font_lg = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 28)
    font_md = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 16)
    font_sm = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 12)
    font_xl = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 42)
except:
    font_lg = ImageFont.load_default()
    font_md = font_lg
    font_sm = font_lg
    font_xl = font_lg

# ── Sidebar ──
draw.rectangle([0, 0, 220, H], fill=sidebar_bg)
draw.rectangle([220, 0, 222, H], fill=border)

# Logo area
draw.text((30, 30), "CoinLytix", fill=text_w, font=font_lg)

# Menu items
menu = ["Dashboard", "Transaction", "Tokens", "Analytics", "Dex Tracker", "Liquidation", "History"]
for i, item in enumerate(menu):
    y = 100 + i * 48
    if i == 0:
        draw.rounded_rectangle([12, y-8, 210, y+32], radius=8, fill=accent)
        draw.text((30, y), item, fill=(255, 255, 255), font=font_md)
    else:
        draw.text((30, y), item, fill=text_dim, font=font_md)

# ── Top bar ──
draw.rectangle([222, 0, W, 60], fill=sidebar_bg)
draw.rectangle([222, 60, W, 62], fill=border)

# Search
draw.rounded_rectangle([260, 12, 500, 48], radius=8, fill=card_bg, outline=border)
draw.text((280, 20), "Search Here...", fill=text_dim, font=font_sm)

# Connect Wallet button
draw.rounded_rectangle([W-200, 12, W-20, 48], radius=20, fill=red)
draw.text((W-180, 20), "Connect Wallet", fill=(255, 255, 255), font=font_sm)

# ── Main content ──
content_x = 242

# Professional Highlights card
draw.rounded_rectangle([content_x, 80, W-20, 280], radius=12, fill=card_bg, outline=border)
draw.text((content_x+24, 96), "Professional Highlights", fill=text_w, font=font_md)
draw.text((content_x+24, 124), "Daily Transactions", fill=text_dim, font=font_sm)
draw.text((content_x+24, 150), "9,323.745k", fill=text_w, font=font_xl)

# Green badge
draw.rounded_rectangle([content_x+24, 210, content_x+100, 236], radius=12, fill=(0, 40, 30))
draw.text((content_x+34, 216), "3.27%", fill=green, font=font_sm)
draw.text((content_x+110, 216), "+$782.40", fill=green, font=font_sm)

# Sparkline area (fake chart)
for x in range(content_x+400, W-40, 3):
    y_val = 180 + int(np.sin((x - content_x) * 0.03) * 30 + np.random.randint(-5, 5))
    draw.rectangle([x, y_val, x+2, y_val+2], fill=accent)

# Month labels
months = ["January", "February", "March", "April", "May", "June"]
for i, m in enumerate(months):
    x = content_x + 400 + i * 90
    if x < W - 40:
        draw.text((x, 250), f"$1,322", fill=text_dim, font=font_sm)
        draw.text((x, 264), m, fill=text_dim, font=font_sm)

# ── Stat cards row ──
card_titles = ["Latest Batch", "Average Block Time", "Total Txns", "Total Addresses"]
card_values = ["$593,513.7", "$324,212.7", "$2134,121.7", "$593,513.7"]
card_deltas = ["+70%", "-50%", "+70%", "+70%"]
card_colors = [green, red, green, green]

card_w = (W - content_x - 20 - 3*16) // 4
for i in range(4):
    cx = content_x + i * (card_w + 16)
    draw.rounded_rectangle([cx, 300, cx+card_w, 420], radius=12, fill=card_bg, outline=border)
    draw.text((cx+16, 316), card_titles[i], fill=text_w, font=font_sm)
    draw.text((cx+16, 348), card_values[i], fill=text_w, font=font_md)
    draw.text((cx+16+120, 350), card_deltas[i], fill=card_colors[i], font=font_sm)
    
    # Mini sparkline
    for x in range(cx+16, cx+card_w-16, 2):
        y_val = 390 + int(np.sin((x - cx) * 0.05) * 10 + np.random.randint(-3, 3))
        draw.rectangle([x, y_val, x+1, y_val+1], fill=card_colors[i])

# ── Latest Transactions ──
draw.rounded_rectangle([content_x, 440, content_x+580, 700], radius=12, fill=card_bg, outline=border)
draw.text((content_x+24, 456), "Latest Transactions", fill=text_w, font=font_md)
draw.text((content_x+400, 456), "Success Rate", fill=text_dim, font=font_sm)
draw.text((content_x+500, 456), "95%", fill=green, font=font_md)

for i in range(4):
    ty = 500 + i * 48
    draw.rounded_rectangle([content_x+24, ty, content_x+90, ty+24], radius=4, fill=(0, 40, 30))
    draw.text((content_x+32, ty+4), "Success", fill=green, font=font_sm)
    draw.text((content_x+100, ty+4), "Contract Call", fill=text_w, font=font_sm)
    draw.text((content_x+280, ty+4), "131.35 EDU", fill=text_dim, font=font_sm)
    draw.text((content_x+420, ty+4), "NOW", fill=text_dim, font=font_sm)

# ── Latest Batches ──
draw.rounded_rectangle([content_x+600, 440, W-20, 700], radius=12, fill=card_bg, outline=border)
draw.text((content_x+624, 456), "Latest Batches", fill=text_w, font=font_md)

batch_items = ["+0.2849 ETH", "+0.2849 BTC", "+0.2849 ETH", "+0.2849 ETH"]
for i, item in enumerate(batch_items):
    ty = 500 + i * 44
    draw.text((content_x+624, ty), item, fill=green, font=font_sm)
    draw.text((content_x+624, ty+16), "Swap/USDC > ETH", fill=text_dim, font=font_sm)

# ── Subtle gradient overlay (glassmorphism hint) ──
overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
odraw = ImageDraw.Draw(overlay)
for y in range(80):
    alpha = int(30 * (1 - y/80))
    odraw.line([(0, y), (W, y)], fill=(94, 106, 210, alpha))
img.paste(Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB"))

# Save
output_path = "/Users/apple/Desktop/Alpha/ANVIL/demo/test_dashboard.png"
img.save(output_path)
print(f"✅ Saved: {output_path} ({W}x{H})")
