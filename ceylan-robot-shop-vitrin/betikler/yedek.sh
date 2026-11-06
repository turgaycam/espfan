#!/usr/bin/env bash
# Gece SQLite yedeği — cr-shop-yedek.service (03:00).
# Tutarlı kopya: sqlite3 ".backup" (varsa) ya da Python sqlite3 con.backup().
# Ortam: SHOP_DB (zorunlu), SHOP_YEDEK_DIZIN, SHOP_YEDEK_GUN (7), SHOP_YEDEK_ARAC (otomatik|sqlite3|python), SHOP_PYTHON (python3)
set -euo pipefail

DB="${SHOP_DB:?SHOP_DB tanımlı değil}"
YEDEK_DIZIN="${SHOP_YEDEK_DIZIN:-/opt/cr-shop-demo/yedek}"
TUTULAN_GUN="${SHOP_YEDEK_GUN:-7}"
ARAC="${SHOP_YEDEK_ARAC:-otomatik}"
PYTHON="${SHOP_PYTHON:-python3}"

if [ ! -f "$DB" ]; then
  echo "HATA: veritabanı yok: $DB" >&2
  exit 1
fi
mkdir -p "$YEDEK_DIZIN"
HEDEF="$YEDEK_DIZIN/shop-$(date +%Y%m%d).db"
GECICI="$HEDEF.yarim"
rm -f "$GECICI"

if [ "$ARAC" = "otomatik" ]; then
  if command -v sqlite3 >/dev/null 2>&1; then ARAC=sqlite3; else ARAC=python; fi
fi

case "$ARAC" in
  sqlite3)
    sqlite3 "$DB" ".backup '$GECICI'"
    ;;
  python)
    "$PYTHON" - "$DB" "$GECICI" <<'PY'
import sqlite3
import sys

kaynak = sqlite3.connect(sys.argv[1])
hedef = sqlite3.connect(sys.argv[2])
try:
    kaynak.backup(hedef)
finally:
    hedef.close()
    kaynak.close()
PY
    ;;
  *)
    echo "HATA: bilinmeyen SHOP_YEDEK_ARAC: $ARAC" >&2
    exit 1
    ;;
esac

BUTUNLUK="$("$PYTHON" -c 'import sqlite3, sys; c = sqlite3.connect(sys.argv[1]); print(c.execute("PRAGMA integrity_check").fetchone()[0]); c.close()' "$GECICI")"
if [ "$BUTUNLUK" != "ok" ]; then
  rm -f "$GECICI"
  echo "HATA: yedek bütünlük kontrolü başarısız: $BUTUNLUK" >&2
  exit 1
fi
mv -f "$GECICI" "$HEDEF"

# 7 günden eski yedekleri sil (-mtime +6: en az 7 tam gün önce değişmiş)
find "$YEDEK_DIZIN" -maxdepth 1 -type f -name 'shop-[0-9]*.db' -mtime "+$((TUTULAN_GUN - 1))" -print -delete \
  | sed 's/^/silindi: /'

echo "yedek: $HEDEF ($(du -h "$HEDEF" | cut -f1)) via $ARAC"
