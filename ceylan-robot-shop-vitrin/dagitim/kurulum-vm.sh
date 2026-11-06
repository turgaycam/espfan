#!/usr/bin/env bash
# cr-shop-demo VM ön koşulları. BİR KEZ çalıştırılır; yeniden çalıştırmak güvenlidir (idempotent).
# systemd birim dosyaları değiştiğinde de yeniden çalıştırılır (deploy.sh birimleri güncellemez).
# Kullanım (VM'de, depo kopyasının kökünden): sudo bash dagitim/kurulum-vm.sh
set -euo pipefail

KAYNAK="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KOK=/opt/cr-shop-demo
DAGITICI="${CR_SHOP_DAGITICI:-crwebdemo}"
SERVIS_KULLANICISI=crshop
PORT=3030
AGLAR=(192.168.2.0/24 192.168.5.0/24 192.168.11.0/24 192.168.12.0/24)
SUDOERS=/etc/sudoers.d/cr-shop-demo
BIRIMLER=(cr-shop-demo.service cr-shop-esitle.service cr-shop-esitle.timer cr-shop-yedek.service
          cr-shop-yedek.timer cr-shop-kur.service cr-shop-kur.timer)
ZAMANLAYICILAR=(cr-shop-esitle.timer cr-shop-yedek.timer cr-shop-kur.timer)

if [ "$(id -u)" -ne 0 ]; then
  echo "HATA: sudo ile çalıştırın: sudo bash $0" >&2
  exit 1
fi
if ! id "$DAGITICI" >/dev/null 2>&1; then
  echo "HATA: dağıtıcı kullanıcı yok: $DAGITICI" >&2
  exit 1
fi
for birim in "${BIRIMLER[@]}"; do
  if [ ! -f "$KAYNAK/systemd/$birim" ]; then
    echo "HATA: eksik birim dosyası: $KAYNAK/systemd/$birim" >&2
    exit 1
  fi
done
# Sembolik bağ üzerinden root chown/chmod hedefe uygulanmasın.
for yol in "$KOK" "$KOK/releases" "$KOK/veri" "$KOK/yedek" "$KOK/ortam"; do
  if [ -L "$yol" ]; then
    echo "HATA: $yol sembolik bağ; kurulum durduruldu (elle inceleyin)." >&2
    exit 1
  fi
done
# ufw kurulu ve etkin olmalı, gelen trafik varsayılanı deny olmalı; betik ufw'yi etkinleştirmez.
if ! command -v ufw >/dev/null 2>&1; then
  echo "HATA: ufw kurulu değil; kurulum durduruldu (betik ufw kurmaz/etkinleştirmez)." >&2
  exit 1
fi
UFW_DURUM="$(LANGUAGE= LC_ALL=C ufw status verbose)"
if ! grep -q '^Status: active' <<<"$UFW_DURUM"; then
  echo "HATA: ufw etkin değil; kurulum durduruldu (betik ufw'yi etkinleştirmez)." >&2
  exit 1
fi
if ! grep -Eq '^Default: deny \(incoming\)' <<<"$UFW_DURUM"; then
  echo "HATA: ufw gelen trafik varsayılanı 'deny' değil; kurulum durduruldu:" >&2
  grep '^Default:' <<<"$UFW_DURUM" >&2 || true
  exit 1
fi
DIGER_SERVISLER=(web-demo aic-demo)

cat <<EOF
cr-shop-demo kurulumu şunları yapacak:
  1. apt: apt-get update + python3-venv ve sqlite3 paketleri
     (NEEDRESTART_MODE=l: needrestart yalnız listeler, hiçbir servisi yeniden başlatmaz)
  2. Sistem kullanıcısı: $SERVIS_KULLANICISI (giriş kabuğu yok, ev klasörü yok)
  3. Klasörler: $KOK ve $KOK/releases (sahibi $DAGITICI, 755);
               $KOK/veri ve $KOK/yedek (sahibi $SERVIS_KULLANICISI, 750)
  4. Ortam dosyası: $KOK/ortam yoksa boş oluşturulur; sahibi $SERVIS_KULLANICISI, izin 600 (içeriğe dokunulmaz)
  5. sudoers ($SUDOERS): $DAGITICI parolasız YALNIZ şunları çalıştırabilir:
       /usr/bin/systemctl restart cr-shop-demo
       /usr/bin/systemctl start cr-shop-esitle
       ($SERVIS_KULLANICISI olarak) $KOK/releases/<release>/venv/bin/python -m app.gecis_calistir
  6. systemd: ${BIRIMLER[*]}
     -> /etc/systemd/system, daemon-reload, cr-shop-demo.service enable (başlatılmaz; ilk deploy başlatır),
     zamanlayıcılar enable --now
  7. ufw: $PORT/tcp yalnız ${AGLAR[*]}
Port 80 (web-demo) ve 3027 (aic-demo) servislerine dokunulmaz;
sonda ActiveEnterTimestamp önce/sonra karşılaştırılıp yazdırılır.
EOF
read -r -p "devam? (e/h) " CEVAP
if [ "$CEVAP" != "e" ]; then
  echo "İptal edildi."
  exit 1
fi

DIGER_ONCE="$(systemctl show -p ActiveEnterTimestamp "${DIGER_SERVISLER[@]}" 2>&1 || true)"

echo "[1/7] paketler"
export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE=l
apt-get update -q
apt-get install -y -q python3-venv sqlite3

echo "[2/7] servis kullanıcısı"
if id "$SERVIS_KULLANICISI" >/dev/null 2>&1; then
  echo "  $SERVIS_KULLANICISI zaten var"
else
  useradd --system --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin --user-group "$SERVIS_KULLANICISI"
fi

echo "[3/7] klasörler"
install -d -o "$DAGITICI" -g "$DAGITICI" -m 755 "$KOK" "$KOK/releases"
install -d -o "$SERVIS_KULLANICISI" -g "$SERVIS_KULLANICISI" -m 750 "$KOK/veri" "$KOK/yedek"

echo "[4/7] ortam dosyası"
if [ ! -e "$KOK/ortam" ]; then
  install -o "$SERVIS_KULLANICISI" -g "$SERVIS_KULLANICISI" -m 600 /dev/null "$KOK/ortam"
  echo "  boş $KOK/ortam oluşturuldu (doldurulması gerekiyor)"
fi
chown "$SERVIS_KULLANICISI:$SERVIS_KULLANICISI" "$KOK/ortam"
chmod 600 "$KOK/ortam"

echo "[5/7] sudoers"
GECICI_SUDOERS="$(mktemp)"
trap 'rm -f "$GECICI_SUDOERS"' EXIT
cat > "$GECICI_SUDOERS" <<EOF
# cr-shop-demo: deploy'un parolasız çalıştırabildiği komutlar (yalnız bunlar).
# Bu dosyayı dagitim/kurulum-vm.sh üretir; elle değiştirmeyin.
Cmnd_Alias CR_SHOP_SERVIS = /usr/bin/systemctl restart cr-shop-demo, /usr/bin/systemctl start cr-shop-esitle
Cmnd_Alias CR_SHOP_GECIS = $KOK/releases/[0-9]*-[0-9]*/venv/bin/python -m app.gecis_calistir
$DAGITICI ALL=(root) NOPASSWD: CR_SHOP_SERVIS
$DAGITICI ALL=($SERVIS_KULLANICISI) NOPASSWD: CR_SHOP_GECIS
EOF
visudo -cf "$GECICI_SUDOERS"
install -o root -g root -m 440 "$GECICI_SUDOERS" "$SUDOERS"
if ! visudo -c; then
  rm -f "$SUDOERS"
  echo "HATA: visudo -c başarısız; $SUDOERS silindi, kurulum durduruldu." >&2
  exit 1
fi

echo "[6/7] systemd birimleri"
for birim in "${BIRIMLER[@]}"; do
  install -o root -g root -m 644 "$KAYNAK/systemd/$birim" "/etc/systemd/system/$birim"
done
systemctl daemon-reload
systemctl enable cr-shop-demo.service
systemctl enable --now "${ZAMANLAYICILAR[@]}"

echo "[7/7] ufw"
for ag in "${AGLAR[@]}"; do
  ufw allow proto tcp from "$ag" to any port "$PORT" comment "cr-shop-demo"
done

echo "Özet:"
id "$SERVIS_KULLANICISI"
ls -ld "$KOK" "$KOK/releases" "$KOK/veri" "$KOK/yedek" "$KOK/ortam"
systemctl list-timers --all --no-pager 'cr-shop-*'
ufw status | grep -E "^$PORT/tcp" || true
DIGER_SONRA="$(systemctl show -p ActiveEnterTimestamp "${DIGER_SERVISLER[@]}" 2>&1 || true)"
echo "Diğer servisler (${DIGER_SERVISLER[*]}) ActiveEnterTimestamp — önce:"
echo "$DIGER_ONCE"
echo "sonra:"
echo "$DIGER_SONRA"
if [ "$DIGER_ONCE" = "$DIGER_SONRA" ]; then
  echo "  değişmedi: ${DIGER_SERVISLER[*]} yeniden başlatılmadı."
else
  echo "UYARI: ${DIGER_SERVISLER[*]} ActiveEnterTimestamp değişti; yeniden başlatılmış olabilir, kontrol edin." >&2
fi
echo "TAMAM. Sıradaki: $KOK/ortam dosyasını doldurun, sonra laptopta: bash dagitim/deploy.sh"
