# Wipecord

A local desktop tool for deleting **your own** Discord messages — in a DM or a server channel — without handing your token to a website.

*[Türkçe](#türkçe) below.*

---

> ## ⚠️ Read this first
>
> Wipecord signs in with your **personal user token**. Discord's Terms of Service prohibit automating a user account ("self-bots"), and accounts have been terminated for it.
>
> The pacing in this tool keeps you inside Discord's rate limits. It does **not**, and cannot, remove the risk that using it violates those terms. **There is no way to make that risk zero.** Anyone telling you otherwise is selling something.
>
> **Deletion is permanent.** Nothing here can be undone.
>
> Use it on your own account, at your own risk.

---

## Why it exists

The web-based "message cleaners" all work the same way: you paste your Discord token into someone else's website. That token is full account access — read every DM, send messages as you, change your email. Pasting it into a page you did not write is the single worst thing you can do with it.

Wipecord does the same job locally. Your token never leaves your machine, never touches disk, and the only host the app ever contacts is `discord.com`. The source is short enough to read before you trust it.

## What it does

- Deletes **only** messages authored by the token owner. Other people's messages are filtered out server-side *and* checked again on every message before anything is deleted.
- Three modes: **everything**, the **last N** messages, or a **date range**.
- **Preview first.** The Delete button stays disabled until you have run a preview, and re-locks the moment you change any setting.
- Randomised, human-scale delays between deletions, with full `429` / `Retry-After` compliance.
- Pause, resume, and stop — stop takes effect immediately, even mid-wait.
- Live colour-coded log, progress bar and ETA.
- English and Turkish interface.

## Install

Requires Python 3.10+ (developed on 3.11).

```bash
git clone https://github.com/DogukanCoskun/Wipecord.git
cd Wipecord
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
python -m wipecord
```

## Using it

1. **Token** — paste it, press *Verify*. The field is masked; the token is held in memory only.
2. **Channel or DM ID** — in Discord, enable *Settings → Advanced → Developer Mode*, then right-click the channel or DM and choose *Copy Channel ID*. Press *Look up* to confirm you have the right conversation before anything happens.
3. **Mode** — everything, last N, or a date range (dates are inclusive, in your local time).
4. **Find (preview)** — see exactly what would be deleted. Nothing is changed.
5. **Delete** — now enabled. Deleting *everything* asks you to type the channel name to confirm.

## How the pacing works

This is the part that matters, so it is worth stating plainly. Four layers, in the order they engage:

1. **A randomised delay between deletions** — uniform in your configured range, recomputed every time. The floor is 1.0s and the UI will not go below it no matter what you type.
2. **Proactive bucket tracking** — every response carries `X-RateLimit-Remaining` and `X-RateLimit-Reset-After`. When a bucket is spent, Wipecord waits for the reset *before* sending, rather than sending and collecting a 429.
3. **Reactive 429 handling** — the `retry_after` value from the response body (more precise than the header) plus jitter, then the same message is retried. Three in a row and the baseline delay slows down. Five in a row and the job stops.
4. **Transport backoff** — exponential retry for 5xx and network errors, then the message is recorded as failed and the run continues.

Every 50 deletions there is a longer pause, because an hour of perfectly uniform traffic is a worse pattern than the same traffic broken up.

**Why stopping at five 429s matters:** Cloudflare bans an IP after roughly 10,000 failed requests in 10 minutes. A tool that retries in a tight loop is exactly how people get there. Wipecord would rather abandon the job than burn your IP.

## What it deliberately does not do

This list is the reason the project can be open source without embarrassment:

- **No User-Agent spoofing.** Wipecord identifies itself honestly. It does not pretend to be the official Discord client.
- **No proxy or IP rotation.**
- **No CAPTCHA solving or challenge evasion.**
- **No multi-account support.**
- **No telemetry, analytics, or crash reporting.** The only host contacted is `discord.com`.
- **No token storage.** Not a config file, not a keyring, not a "remember me" checkbox.

The distinction is deliberate: respecting a rate limit is being a good API citizen. Defeating detection is something else, and this project does not do it.

## Headless preview

For verifying behaviour without the GUI:

```bash
export WIPECORD_TOKEN="..."      # or you will be prompted, with hidden input
python -m wipecord --headless --channel 123456789012345678
python -m wipecord --headless --channel 123456789012345678 --mode last_n --last 46
python -m wipecord --headless --channel 123456789012345678 \
    --mode date_range --since 2024-01-01 --until 2024-06-30 --json preview.json
```

Headless is **preview-only**. Deleting is destructive and stays behind the GUI's confirmation flow — there is no shell flag for it. The token is not a command-line argument either, because arguments end up in shell history and in the process list where other users can read them.

## Development

```bash
pip install -r requirements-dev.txt
python -m pytest
```

134 tests, no network access in any of them. The layering is `ui/ → engine → scanner → client → ratelimit`; nothing below `ui/` imports tkinter, which is what makes the whole pipeline testable headlessly.

## Licence

MIT. See [LICENSE](LICENSE).

---

# Türkçe

Discord mesajlarınızı (DM veya sunucu kanalı) **kendi bilgisayarınızda**, token'ınızı hiçbir siteye vermeden silmek için bir masaüstü aracı.

> ## ⚠️ Önce bunu okuyun
>
> Wipecord **kişisel kullanıcı token'ınızla** giriş yapar. Discord'un kullanım şartları bir kullanıcı hesabının otomatikleştirilmesini ("self-bot") yasaklar ve bu nedenle kapatılmış hesaplar vardır.
>
> Bu araçtaki gecikmeler sizi Discord'un hız sınırları içinde tutar. Ancak kullanımın bu şartları ihlal etmesi riskini ortadan kaldırmaz, **kaldıramaz. Bu riski sıfırlamanın bir yolu yoktur.** Aksini söyleyen size bir şey satıyordur.
>
> **Silme işlemi kalıcıdır.** Buradaki hiçbir şey geri alınamaz.
>
> Kendi hesabınızda, kendi sorumluluğunuzda kullanın.

## Neden var

Web tabanlı "mesaj temizleyiciler"in hepsi aynı şekilde çalışır: Discord token'ınızı başkasının sitesine yapıştırırsınız. O token hesabın tam erişimidir — bütün DM'lerinizi okumak, sizin adınıza mesaj atmak, e-postanızı değiştirmek. Onu yazmadığınız bir sayfaya yapıştırmak, o token'la yapabileceğiniz en kötü şeydir.

Wipecord aynı işi yerelde yapar. Token'ınız makineden çıkmaz, diske yazılmaz ve uygulamanın bağlandığı tek adres `discord.com`'dur. Kaynak kod, güvenmeden önce okuyabileceğiniz kadar kısadır.

## Ne yapar

- **Yalnızca** token sahibinin yazdığı mesajları siler. Başkalarının mesajları hem sunucu tarafında filtrelenir, hem de silinmeden önce her mesajda tekrar kontrol edilir.
- Üç mod: **tümü**, **son N** mesaj, veya **tarih aralığı**.
- **Önce önizleme.** Sil butonu, bir önizleme çalıştırmadan aktif olmaz; herhangi bir ayarı değiştirdiğiniz anda tekrar kilitlenir.
- Silmeler arasında rastgele, insan ölçeğinde gecikmeler; tam `429` / `Retry-After` uyumu.
- Duraklat, devam et, durdur — durdurma beklemenin ortasında bile anında etkilidir.
- Canlı renkli log, ilerleme çubuğu ve tahmini süre.
- Türkçe ve İngilizce arayüz.

## Kurulum

Python 3.10+ gerekir (3.11 ile geliştirildi).

```bash
git clone https://github.com/DogukanCoskun/Wipecord.git
cd Wipecord
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m wipecord
```

## Kullanım

1. **Token** — yapıştırın, *Doğrula*'ya basın. Alan maskelidir; token sadece bellekte tutulur.
2. **Kanal veya DM ID** — Discord'da *Ayarlar → Gelişmiş → Geliştirici Modu*'nu açın, kanala veya DM'e sağ tıklayıp *Kanal Kimliğini Kopyala* deyin. *Getir*'e basarak doğru sohbette olduğunuzu daha hiçbir şey olmadan doğrulayın.
3. **Mod** — tümü, son N, veya tarih aralığı (tarihler yerel saatinizle ve iki uç da dahildir).
4. **Bul (önizleme)** — tam olarak neyin silineceğini görün. Hiçbir şey değişmez.
5. **Sil** — artık aktif. *Tümü* modunda onaylamak için kanal adını yazmanız istenir.

## Hız yönetimi nasıl çalışır

Asıl önemli kısım bu, o yüzden açıkça yazmaya değer. Devreye giriş sırasıyla dört katman:

1. **Silmeler arası rastgele gecikme** — belirlediğiniz aralıkta, her seferinde yeniden hesaplanır. Taban 1.0 saniyedir ve ne yazarsanız yazın arayüz bunun altına inmez.
2. **Proaktif bucket takibi** — her yanıt `X-RateLimit-Remaining` ve `X-RateLimit-Reset-After` taşır. Bir bucket tükendiğinde Wipecord, istek gönderip 429 toplamak yerine sıfırlanmayı **göndermeden önce** bekler.
3. **Reaktif 429 yönetimi** — yanıt gövdesindeki `retry_after` (header'dan daha hassas) artı jitter kadar beklenir, sonra aynı mesaj tekrar denenir. Üst üste üçte temel gecikme yavaşlar. Üst üste beşte iş durur.
4. **Bağlantı geri çekilmesi** — 5xx ve ağ hataları için üstel tekrar; sonra o mesaj başarısız olarak kaydedilir ve işlem devam eder.

Her 50 silmede bir daha uzun bir mola verilir; çünkü bir saat boyunca kusursuz düzenli trafik, aynı trafiğin bölünmüş halinden daha kötü bir desendir.

**Beşinci 429'da durmak neden önemli:** Cloudflare, 10 dakikada yaklaşık 10.000 başarısız istekten sonra IP'yi banlar. Sıkı döngüde tekrar deneyen bir araç, insanları tam olarak oraya götürür. Wipecord, IP'nizi yakmaktansa işi bırakmayı tercih eder.

## Bilerek yapmadıkları

Bu liste, projenin utanmadan açık kaynak olabilmesinin sebebidir:

- **User-Agent sahteciliği yok.** Wipecord kendini dürüstçe tanıtır, resmi Discord istemcisi taklidi yapmaz.
- **Proxy veya IP rotasyonu yok.**
- **CAPTCHA çözme veya doğrulama atlatma yok.**
- **Çoklu hesap desteği yok.**
- **Telemetri, analitik veya hata raporlama yok.** Bağlanılan tek adres `discord.com`.
- **Token saklama yok.** Ne config dosyası, ne keyring, ne "beni hatırla" kutucuğu.

Ayrım bilinçlidir: hız sınırına uymak, API'ye karşı düzgün davranmaktır. Tespiti atlatmak başka bir şeydir ve bu proje onu yapmaz.

## Arayüzsüz önizleme

Davranışı GUI olmadan doğrulamak için:

```bash
export WIPECORD_TOKEN="..."      # ya da gizli girişle sorulur
python -m wipecord --headless --channel 123456789012345678
python -m wipecord --headless --channel 123456789012345678 --mode last_n --last 46
```

Arayüzsüz mod **yalnızca önizlemedir**. Silme yıkıcı bir işlemdir ve GUI'nin onay akışının arkasında kalır — bunun için bir komut satırı bayrağı yoktur. Token da komut satırı argümanı değildir; argümanlar kabuk geçmişine ve süreç listesine düşer, oradan başka kullanıcılar okuyabilir.

## Geliştirme

```bash
pip install -r requirements-dev.txt
python -m pytest
```

134 test, hiçbirinde ağ erişimi yok. Katmanlama `ui/ → engine → scanner → client → ratelimit`; `ui/` altındaki hiçbir şey tkinter import etmez, bütün akışın arayüzsüz test edilebilmesini sağlayan da budur.

## Lisans

MIT. Bkz. [LICENSE](LICENSE).
