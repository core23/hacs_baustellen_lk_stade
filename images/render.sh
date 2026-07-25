#!/usr/bin/env bash
# Erzeugt preview.png sowie die Brand-Assets aus den HTML-Quellen daneben.
# Voraussetzungen: Google Chrome, ImageMagick, optipng.
set -euo pipefail

cd "$(dirname "$0")"

# HACS erwartet die Brand-Assets im Verzeichnis der Integration.
BRAND=../custom_components/baustellen_stade/brand

CHROME=${CHROME:-"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"}

shot() { # shot <html> <breite> <hoehe> <ziel>
  "$CHROME" --headless --disable-gpu --hide-scrollbars \
    --default-background-color=00000000 --force-device-scale-factor=2 \
    --window-size="$2,$3" --screenshot="$4" "file://$PWD/$1" >/dev/null 2>&1
}

# Vorschaubild: in doppelter Auflösung rendern, dann sauber herunterskalieren.
shot preview.html 1200 630 preview@2x.png
magick preview@2x.png -resize 1200x630 +dither -colors 256 \
  -define png:compression-level=9 -strip preview.png
rm preview@2x.png

# Icon: 512 px für brands, 256 px als Standardgröße.
mkdir -p "$BRAND"
shot icon.html 256 256 "$BRAND/icon@2x.png"
magick "$BRAND/icon@2x.png" -resize 256x256 -strip "$BRAND/icon.png"

optipng -quiet -o5 -strip all preview.png "$BRAND/icon.png" "$BRAND/icon@2x.png"

magick identify -format "%f  %wx%h  %b\n" preview.png "$BRAND/icon.png" "$BRAND/icon@2x.png"
