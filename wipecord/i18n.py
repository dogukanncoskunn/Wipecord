"""Interface strings.

A plain dict lookup rather than gettext: two languages, a few dozen keys, and
no build step. English is the source of truth; a missing key falls back to it,
then to the key itself, so a gap is visible rather than crashing the UI.
"""

from __future__ import annotations

DEFAULT_LANGUAGE = "en"

LANGUAGE_NAMES = {"en": "English", "tr": "Türkçe"}

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "app.title": "Wipecord",
        # Disclaimer
        "tos.title": "Read this before you start",
        "tos.body": (
            "Wipecord signs in with your personal user token. Discord's terms of "
            "service prohibit automating a user account, and accounts have been "
            "terminated for it.\n\n"
            "The pacing in this tool keeps you inside Discord's rate limits. It "
            "does not, and cannot, remove the risk that using it violates those "
            "terms. There is no way to make that risk zero.\n\n"
            "Deletion is permanent. Nothing here can be undone.\n\n"
            "Your token stays on this machine. It is never written to disk and "
            "never sent anywhere except discord.com."
        ),
        "tos.accept": "I understand the risk and accept it",
        "tos.continue": "Continue",
        "tos.quit": "Quit",
        # Credentials
        "section.account": "Account",
        "label.token": "User token",
        "label.token.placeholder": "Never saved to disk",
        "btn.verify": "Verify",
        "btn.show": "Show",
        "btn.hide": "Hide",
        "help.token.link": "How do I get my token?",
        "help.token.title": "Getting your Discord token",
        "help.token.body": (
            "Your token has to be read from Discord in the browser — the desktop "
            "app will not show it. It takes about a minute:\n\n"
            "1.  Open discord.com/app in your browser and log in.\n"
            "2.  Press F12 to open Developer Tools, then click the \"Network\" tab.\n"
            "3.  In the filter box, type:  /api\n"
            "4.  Click a channel, or send or open a message, so requests appear in "
            "the list.\n"
            "5.  Click any request to \"discord.com/api/…\". In the panel that opens, "
            "find \"Headers\" → \"Request Headers\".\n"
            "6.  Locate the line that starts with  authorization:  — the value after "
            "it is your token. Copy that value and paste it above."
        ),
        "help.token.warning": (
            "⚠  This value is full access to your account. Never paste it into a "
            "website, and never run a script someone tells you to paste into the "
            "console — that is how tokens get stolen. Wipecord keeps it in memory "
            "only and sends it nowhere except discord.com."
        ),
        "help.close": "Got it",
        "status.verifying": "Verifying…",
        "status.verified": "Signed in as {name}",
        "status.verify_failed": "Could not verify: {error}",
        # Target
        "section.target": "Target",
        "label.channel": "Channel or DM ID",
        "label.channel.placeholder": "Right-click a channel, Copy Channel ID",
        "btn.fetch_channel": "Look up",
        "status.channel": "{label} · {kind}",
        "status.channel_failed": "Could not read that channel: {error}",
        "kind.dm": "direct message",
        "kind.guild": "server channel",
        # Mode
        "section.mode": "What to delete",
        "mode.all": "Everything",
        "mode.last_n": "Last N",
        "mode.date_range": "Date range",
        "label.count": "How many messages",
        "label.since": "From",
        "label.until": "To",
        "hint.dates": "YYYY-MM-DD, in your local time. Both ends included.",
        # Filters and pace
        "section.filters": "Filters",
        "filter.skip_pinned": "Skip pinned messages",
        "section.pace": "Pace",
        "label.delay_min": "Min delay (s)",
        "label.delay_max": "Max delay (s)",
        "hint.pace": "Randomised between these. Minimum {floor}s; slower is safer.",
        "hint.estimate": "≈ {count} messages ≈ {duration}",
        # Actions
        "btn.find": "Find (preview)",
        "btn.delete": "Delete",
        "btn.pause": "Pause",
        "btn.resume": "Resume",
        "btn.stop": "Stop",
        "btn.clear_log": "Clear",
        "btn.save_log": "Save log",
        "btn.export": "Export preview",
        # Status
        "state.idle": "Ready",
        "state.scanning": "Searching…",
        "state.preview": "Preview ready",
        "state.deleting": "Deleting…",
        "state.paused": "Paused",
        "state.done": "Finished",
        "progress.counts": "{done} / {total}",
        "progress.eta": "elapsed {elapsed} · ETA {eta}",
        # Validation and confirmation
        "error.token_required": "Enter your user token first.",
        "error.channel_required": "Enter a channel or DM ID first.",
        "error.count_required": "Enter how many messages to delete.",
        "error.dates_required": "Enter both dates.",
        "error.dates_order": "The start date must not be after the end date.",
        "error.date_format": "Dates must look like 2024-01-31.",
        "error.preview_required": "Run a preview first, so you can see what will be deleted.",
        "error.nothing_found": "The preview found nothing to delete.",
        "confirm.title": "Confirm deletion",
        "confirm.body": (
            "This will permanently delete {count} of your messages in {label}.\n\n"
            "This cannot be undone."
        ),
        "confirm.type_name": "Type the channel name to confirm:",
        "confirm.mismatch": "That does not match {label}.",
        "confirm.delete": "Delete them",
        "confirm.cancel": "Cancel",
        # Results
        "summary.dry_run": "Preview: {scanned} message(s) would be deleted. Nothing was changed.",
        "summary.done": (
            "Done in {duration}. Deleted {deleted}, skipped {skipped}, failed {failed}."
        ),
        "summary.stopped": "Stopped early. Deleted {deleted} before stopping.",
        "log.saved": "Log written to {path}",
        "log.exported": "Preview written to {path}",
        "log.write_failed": "Could not write the file: {error}",
        "log.preview_stale": "Settings changed — run the preview again before deleting.",
    },
    "tr": {
        "app.title": "Wipecord",
        # Uyarı
        "tos.title": "Başlamadan önce okuyun",
        "tos.body": (
            "Wipecord kişisel kullanıcı token'ınızla giriş yapar. Discord'un "
            "kullanım şartları bir kullanıcı hesabının otomatikleştirilmesini "
            "yasaklar ve bu nedenle kapatılmış hesaplar vardır.\n\n"
            "Bu araçtaki gecikmeler sizi Discord'un hız sınırları içinde tutar. "
            "Ancak kullanımın bu şartları ihlal etmesi riskini ortadan "
            "kaldırmaz, kaldıramaz. Bu riski sıfırlamanın bir yolu yoktur.\n\n"
            "Silme işlemi kalıcıdır. Buradaki hiçbir şey geri alınamaz.\n\n"
            "Token'ınız bu makinede kalır. Diske hiç yazılmaz ve discord.com "
            "dışında hiçbir yere gönderilmez."
        ),
        "tos.accept": "Riski anlıyorum ve kabul ediyorum",
        "tos.continue": "Devam et",
        "tos.quit": "Çık",
        # Hesap
        "section.account": "Hesap",
        "label.token": "Kullanıcı token'ı",
        "label.token.placeholder": "Diske asla kaydedilmez",
        "btn.verify": "Doğrula",
        "btn.show": "Göster",
        "btn.hide": "Gizle",
        "help.token.link": "Token'ımı nasıl alırım?",
        "help.token.title": "Discord token'ınızı alma",
        "help.token.body": (
            "Token'ınız Discord'dan, tarayıcıda okunur — masaüstü uygulaması onu "
            "göstermez. Yaklaşık bir dakika sürer:\n\n"
            "1.  Tarayıcınızda discord.com/app adresini açıp giriş yapın.\n"
            "2.  F12'ye basarak Geliştirici Araçları'nı açın, sonra \"Network\" (Ağ) "
            "sekmesine tıklayın.\n"
            "3.  Filtre kutusuna şunu yazın:  /api\n"
            "4.  Bir kanala tıklayın ya da bir mesaj gönderin/açın; böylece listede "
            "istekler görünür.\n"
            "5.  \"discord.com/api/…\" isteklerinden birine tıklayın. Açılan panelde "
            "\"Headers\" → \"Request Headers\"ı bulun.\n"
            "6.  authorization:  ile başlayan satırı bulun — sonrasındaki değer sizin "
            "token'ınızdır. O değeri kopyalayıp yukarıya yapıştırın."
        ),
        "help.token.warning": (
            "⚠  Bu değer hesabınızın tam erişimidir. Onu asla bir siteye "
            "yapıştırmayın ve kimsenin \"konsola yapıştır\" dediği bir script'i "
            "çalıştırmayın — token'lar tam böyle çalınır. Wipecord onu yalnızca "
            "bellekte tutar ve discord.com dışında hiçbir yere göndermez."
        ),
        "help.close": "Anladım",
        "status.verifying": "Doğrulanıyor…",
        "status.verified": "Giriş yapıldı: {name}",
        "status.verify_failed": "Doğrulanamadı: {error}",
        # Hedef
        "section.target": "Hedef",
        "label.channel": "Kanal veya DM ID",
        "label.channel.placeholder": "Kanala sağ tıklayın, Kanal Kimliğini Kopyala",
        "btn.fetch_channel": "Getir",
        "status.channel": "{label} · {kind}",
        "status.channel_failed": "Kanal okunamadı: {error}",
        "kind.dm": "özel mesaj",
        "kind.guild": "sunucu kanalı",
        # Mod
        "section.mode": "Ne silinecek",
        "mode.all": "Tümü",
        "mode.last_n": "Son N",
        "mode.date_range": "Tarih aralığı",
        "label.count": "Kaç mesaj",
        "label.since": "Başlangıç",
        "label.until": "Bitiş",
        "hint.dates": "YYYY-AA-GG, yerel saatinizle. İki uç da dahildir.",
        # Filtreler ve hız
        "section.filters": "Filtreler",
        "filter.skip_pinned": "Sabitlenmiş mesajları atla",
        "section.pace": "Hız",
        "label.delay_min": "En az bekleme (sn)",
        "label.delay_max": "En çok bekleme (sn)",
        "hint.pace": "Bu aralıkta rastgele. En az {floor} sn; yavaş olan güvenlidir.",
        "hint.estimate": "≈ {count} mesaj ≈ {duration}",
        # Eylemler
        "btn.find": "Bul (önizleme)",
        "btn.delete": "Sil",
        "btn.pause": "Duraklat",
        "btn.resume": "Devam et",
        "btn.stop": "Durdur",
        "btn.clear_log": "Temizle",
        "btn.save_log": "Log'u kaydet",
        "btn.export": "Önizlemeyi dışa aktar",
        # Durum
        "state.idle": "Hazır",
        "state.scanning": "Aranıyor…",
        "state.preview": "Önizleme hazır",
        "state.deleting": "Siliniyor…",
        "state.paused": "Duraklatıldı",
        "state.done": "Bitti",
        "progress.counts": "{done} / {total}",
        "progress.eta": "geçen {elapsed} · kalan {eta}",
        # Doğrulama ve onay
        "error.token_required": "Önce kullanıcı token'ınızı girin.",
        "error.channel_required": "Önce bir kanal veya DM ID girin.",
        "error.count_required": "Kaç mesaj silineceğini girin.",
        "error.dates_required": "İki tarihi de girin.",
        "error.dates_order": "Başlangıç tarihi bitişten sonra olamaz.",
        "error.date_format": "Tarihler 2024-01-31 biçiminde olmalı.",
        "error.preview_required": "Önce önizleme çalıştırın; ne silineceğini görmelisiniz.",
        "error.nothing_found": "Önizleme silinecek bir şey bulamadı.",
        "confirm.title": "Silmeyi onayla",
        "confirm.body": (
            "{label} içindeki {count} mesajınız kalıcı olarak silinecek.\n\n"
            "Bu işlem geri alınamaz."
        ),
        "confirm.type_name": "Onaylamak için kanal adını yazın:",
        "confirm.mismatch": "Bu {label} ile eşleşmiyor.",
        "confirm.delete": "Sil",
        "confirm.cancel": "Vazgeç",
        # Sonuçlar
        "summary.dry_run": "Önizleme: {scanned} mesaj silinecekti. Hiçbir şey değişmedi.",
        "summary.done": (
            "{duration} sürdü. Silinen {deleted}, atlanan {skipped}, başarısız {failed}."
        ),
        "summary.stopped": "Erken durduruldu. Durmadan önce {deleted} mesaj silindi.",
        "log.saved": "Log şuraya yazıldı: {path}",
        "log.exported": "Önizleme şuraya yazıldı: {path}",
        "log.write_failed": "Dosya yazılamadı: {error}",
        "log.preview_stale": "Ayarlar değişti — silmeden önce önizlemeyi tekrar çalıştırın.",
    },
}

_current = DEFAULT_LANGUAGE


def available() -> list[str]:
    return list(STRINGS)


def get_language() -> str:
    return _current


def set_language(code: str) -> None:
    global _current
    if code in STRINGS:
        _current = code


def t(key: str, **kwargs) -> str:
    text = STRINGS.get(_current, {}).get(key)
    if text is None:
        text = STRINGS[DEFAULT_LANGUAGE].get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError):
            return text
    return text
