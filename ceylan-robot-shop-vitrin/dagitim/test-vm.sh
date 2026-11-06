#!/usr/bin/env bash
# Çalışma ağacını cr-web-demo VM'ine kopyalayıp orada pytest çalıştırır.
# Kullanım (depo kökünden ya da herhangi bir alt klasörden):
#   bash dagitim/test-vm.sh tests/test_para.py -q
#   bash dagitim/test-vm.sh -q            # bütün testler
# Ortam: CR_TEST_HOST (varsayılan: cr-web-demo ssh takma adı)
# Çıkış kodu: VM'deki pytest'in çıkış kodu (ssh bağlantı hatası 255, pip hatası 1).
set -euo pipefail
export MSYS_NO_PATHCONV=1

HOST="${CR_TEST_HOST:-cr-web-demo}"
KOK="$(git rev-parse --show-toplevel)"
cd "$KOK"
# Her çalışma ağacı (worktree) VM'de kendi klasörünü kullanır; paralel ajanlar birbirinin testini silmez.
KLASOR="kod-$(printf '%s' "$KOK" | sha256sum | cut -c1-8)"

# 1) İzlenen + izlenmeyen (ignore edilmeyen) ve diskte var olan dosyaları tar'la, VM'de temiz klasöre aç
git ls-files -z -co --exclude-standard \
  | while IFS= read -r -d '' f; do if [ -f "$f" ]; then printf '%s\0' "$f"; fi; done \
  | tar --null -T - -czf - \
  | ssh "$HOST" "set -e; rm -rf ~/gelistirme/$KLASOR; mkdir -p ~/gelistirme/$KLASOR; tar -xzf - -C ~/gelistirme/$KLASOR"

# 2) requirements.txt değiştiyse bağımlılıkları kur; 3) pytest
ARGS=""
for a in "$@"; do ARGS+=" $(printf '%q' "$a")"; done

set +e
ssh "$HOST" "bash -s -- $KLASOR $ARGS" <<'UZAK'
set -euo pipefail
KLASOR="$1"; shift
cd ~/gelistirme/"$KLASOR"
VENV=~/gelistirme/.venv
OZET_DOSYASI=~/gelistirme/.requirements.sha256
if [ -f requirements.txt ]; then
  # özet kontrolü + kurulum + özet yazımı tek kilit altında; kilit içinde özet yeniden karşılaştırılır
  export VENV OZET_DOSYASI
  flock ~/gelistirme/.pip.kilit bash -c '
    set -euo pipefail
    YENI="$(sha256sum requirements.txt | cut -d" " -f1)"
    ESKI="$(cat "$OZET_DOSYASI" 2>/dev/null || true)"
    if [ "$YENI" != "$ESKI" ]; then
      echo ">> requirements.txt değişti, pip install çalışıyor" >&2
      "$VENV/bin/python" -m pip install -q -r requirements.txt
      echo "$YENI" > "$OZET_DOSYASI"
    fi
  '
fi
exec "$VENV/bin/python" -m pytest -p no:cacheprovider "$@"
UZAK
KOD=$?
set -e
exit "$KOD"
