#!/usr/bin/env bash
# deploy.sh'nin VM tarafı. crwebdemo olarak, yeni release'in içinden çalışır:
#   bash /opt/cr-shop-demo/releases/<release>/dagitim/uzak-yayinla.sh <release>
# sudo yalnız /etc/sudoers.d/cr-shop-demo'daki parolasız komutlarla (-n) kullanılır.
# CR_SHOP_KOK yalnız testler içindir (tests/test_isletme.py, sahte sudo/curl ile); üretimde tanımlanmaz.
set -euo pipefail

RELEASE="${1:?release adı gerekli}"
KOK="${CR_SHOP_KOK:-/opt/cr-shop-demo}"
REL="$KOK/releases/$RELEASE"
SAGLIK_URL=http://127.0.0.1:3030/saglik

release_sil_ve_dur() {
  echo "HATA: $1 — release siliniyor, current değişmedi." >&2
  cd "$KOK"
  rm -rf "${REL:?}"
  exit 1
}

servisi_yeniden_baslat() {
  # Hata betiği (set -e) kesmez; çağıran dönüş koduna göre karar verir.
  if ! sudo -n /usr/bin/systemctl restart cr-shop-demo </dev/null; then
    echo "UYARI: systemctl restart cr-shop-demo hata verdi." >&2
    return 1
  fi
}

geri_al_ve_dur() {
  # Yeni release yayına alınamadı: current önceki release'e döner, restart denenir, çıkış 1.
  echo "HATA: $1" >&2
  if [ -n "$ONCEKI" ] && [ "$ONCEKI" != "$RELEASE" ] && [ -d "$KOK/releases/$ONCEKI" ]; then
    current_ayarla "$ONCEKI"
    servisi_yeniden_baslat || echo "UYARI: geri dönüşte de restart başarısız; servisi elle kontrol edin." >&2
    echo "GERİ ALINDI: current -> $ONCEKI. Hatalı release incelemek için duruyor: $REL" >&2
    echo "Veritabanı gerekirse elle geri yüklenir: $KOK/veri/shop-onceki-$RELEASE.db" >&2
  else
    echo "Önceki release yok; geri alınacak sürüm bulunamadı." >&2
  fi
  exit 1
}

current_ayarla() {
  ln -sfn "releases/$1" "$KOK/current.yeni"
  mv -Tf "$KOK/current.yeni" "$KOK/current"
}

saglikli_mi() {
  local deneme kod
  for deneme in 1 2 3 4 5 6 7 8 9 10; do
    kod="$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 "$SAGLIK_URL" || true)"
    if [ "$kod" = "200" ]; then
      return 0
    fi
    sleep 1
  done
  return 1
}

cd "$REL"

echo "[1/6] venv + bağımlılıklar"
python3 -m venv venv </dev/null || release_sil_ve_dur "venv kurulamadı (python3-venv kurulu mu?)"
venv/bin/pip install --quiet --disable-pip-version-check -r requirements.txt "pytest==8.*" </dev/null \
  || release_sil_ve_dur "pip install başarısız"

echo "[2/6] testler (release venv'inde; her test geçici veritabanı kullanır)"
venv/bin/python -m pytest -q -p no:cacheprovider tests </dev/null || release_sil_ve_dur "testler geçmedi"

# GERİ ALMA VE ŞEMA (son inceleme M-8): geri_al_ve_dur yalnız `current` bağlantısını önceki release'e çevirir;
# uygulanmış geçişleri (şemayı) GERİ ALMAZ. Bu yüzden geçişler geri uyumlu (yalnız ekleme: tablo/sütun/indeks) yazılır.
# Yıkıcı bir geçiş gerekirse önce servis durdurulur, sonra yedek alınıp geçiş uygulanır.
# Şemayı / veriyi geri döndürmenin tek yolu bu adımın aldığı yedektir: $KOK/veri/shop-onceki-<release>.db
# (gecis_calistir son 3 yedeği tutar). Yedek, eski süreç çalışırken alınır: yedek ile geri yükleme arasındaki
# yazımlar (sipariş, teklif, oturum) kaybolur. Elle geri yükleme (VM'de crwebdemo, sudo parolası ister):
#   sudo systemctl stop cr-shop-demo
#   sudo -u crshop cp /opt/cr-shop-demo/veri/shop-onceki-<RELEASE>.db /opt/cr-shop-demo/veri/shop.db
#   sudo -u crshop rm -f /opt/cr-shop-demo/veri/shop.db-wal /opt/cr-shop-demo/veri/shop.db-shm
#   cd /opt/cr-shop-demo && ln -sfn releases/<ONCEKI_RELEASE> current.yeni && mv -Tf current.yeni current
#   sudo systemctl start cr-shop-demo && curl -fsS http://127.0.0.1:3030/saglik
# <RELEASE> geri alınan (yeni) release'in adıdır (yedek onun dağıtımında alındı); <ONCEKI_RELEASE> eski kodun klasörü.
echo "[3/6] veritabanı yedeği + geçişler (crshop)"
sudo -n -u crshop "$REL/venv/bin/python" -m app.gecis_calistir </dev/null \
  || release_sil_ve_dur "yedek/geçiş başarısız (yedek: $KOK/veri/shop-onceki-$RELEASE.db)"

echo "[4/6] current -> $RELEASE ve yeniden başlatma"
ONCEKI=""
if [ -L "$KOK/current" ]; then
  ONCEKI="$(basename "$(readlink -f "$KOK/current")")"
fi
current_ayarla "$RELEASE"
# Restart başarısızsa eski süreç çalışmaya devam eder; sağlık 200 dönse bile çalışan kod eski release olur.
# Bu yüzden restart hatası, sağlığa bakılmadan başarısızlıktır.
if ! servisi_yeniden_baslat; then
  journalctl -u cr-shop-demo -n 30 --no-pager >&2 || true
  geri_al_ve_dur "systemctl restart cr-shop-demo başarısız"
fi

echo "[5/6] sağlık kontrolü (en fazla 10 sn)"
if ! saglikli_mi; then
  journalctl -u cr-shop-demo -n 30 --no-pager >&2 || true
  geri_al_ve_dur "$SAGLIK_URL 10 sn içinde 200 dönmedi."
fi

echo "[6/6] eski release'ler (son 3 tutulur)"
GUNCEL="$(basename "$(readlink -f "$KOK/current")")"
for eski in $(ls -1 "$KOK/releases" | sort -r | tail -n +4); do
  if [ "$eski" = "$GUNCEL" ]; then
    continue
  fi
  rm -rf "${KOK:?}/releases/${eski:?}"
  echo "  silindi: $eski"
done

echo "TAMAM: $RELEASE yayında (commit $(cat "$REL/SURUM")); önceki: ${ONCEKI:-yok}"
