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

## Download (Windows)

Grab **`Wipecord.exe`** from the [latest release](https://github.com/dogukanncoskunn/Wipecord/releases/latest). It is a single file — no installer, no Python, nothing written outside the folder you put it in.

Verify what you downloaded before running it:

```powershell
Get-FileHash .\Wipecord.exe -Algorithm SHA256
```

Compare that against the `SHA256` published on the release page. If it does not match, do not run it.

> **Windows will probably warn you about this file.** It is an unsigned PyInstaller executable, and a handful of antivirus engines flag *every* PyInstaller build as suspicious because the bootloader unpacks itself to a temp directory — the same thing packers do. The build was submitted to VirusTotal: **5 of 75 engines flagged it, 63 clean.** Every one of the five is a generic machine-learning or heuristic verdict — not one is a signature match. The full report and reasoning are in [`security/SECURITY-AUDIT.md`](security/SECURITY-AUDIT.md), and the exe is reproducible from this source with `scripts\build-exe.ps1`. If you would rather not trust a binary at all, run from source below — that is the honest recommendation.

To dismiss the SmartScreen prompt: **More info → Run anyway**.

## Install from source

Requires Python 3.10+ (developed on 3.11).

```bash
git clone https://github.com/dogukanncoskunn/Wipecord.git
cd Wipecord
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
python -m wipecord
```

### A desktop shortcut (Windows)

To launch it by double-clicking an icon instead of a terminal:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-shortcut.ps1
```

This puts a **Wipecord** icon on your Desktop that opens the app with no console window. Add `-StartMenu` to also place it in the Start Menu. The shortcut just points at the local install — there is no separate copy of the code, and nothing is installed system-wide.

## Using it

1. **Token** — paste it, press *Verify*. The field is masked; the token is held in memory only. Don't know where to find it? The **How do I get my token?** link right under the field walks you through reading it from your browser.
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

166 tests, no network access in any of them. The layering is `ui/ → engine → scanner → client → ratelimit`; nothing below `ui/` imports tkinter, which is what makes the whole pipeline testable headlessly.

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

## İndir (Windows)

**`Wipecord.exe`** dosyasını [son sürümden](https://github.com/dogukanncoskunn/Wipecord/releases/latest) indirin. Tek dosyadır — kurulum yok, Python gerekmez, koyduğunuz klasörün dışına hiçbir şey yazmaz.

Çalıştırmadan önce indirdiğiniz dosyayı doğrulayın:

```powershell
Get-FileHash .\Wipecord.exe -Algorithm SHA256
```

Çıkan değeri sürüm sayfasındaki `SHA256` ile karşılaştırın. Tutmuyorsa çalıştırmayın.

> **Windows bu dosya için büyük ihtimalle uyarı verecek.** İmzasız bir PyInstaller çalıştırılabiliridir ve birkaç antivirüs motoru *bütün* PyInstaller derlemelerini şüpheli işaretler; çünkü bootloader kendini geçici bir klasöre açar — packer'ların yaptığı şeyin aynısı. Derleme VirusTotal'a gönderildi: **75 motordan 5'i işaretledi, 63'ü temiz.** Beşinin de sonucu genel makine-öğrenmesi veya sezgisel tahmin — hiçbiri imza eşleşmesi değil. Tam rapor ve gerekçe [`security/SECURITY-AUDIT.md`](security/SECURITY-AUDIT.md) içinde; exe bu kaynaktan `scripts\build-exe.ps1` ile yeniden üretilebilir. Bir ikiliye hiç güvenmek istemiyorsanız aşağıdan kaynaktan çalıştırın — dürüst tavsiye budur.

SmartScreen uyarısını geçmek için: **Ek bilgi → Yine de çalıştır**.

## Kaynaktan kurulum

Python 3.10+ gerekir (3.11 ile geliştirildi).

```bash
git clone https://github.com/dogukanncoskunn/Wipecord.git
cd Wipecord
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m wipecord
```

### Masaüstü kısayolu (Windows)

Terminal yerine bir ikona çift tıklayarak açmak için:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-shortcut.ps1
```

Bu, masaüstüne konsol penceresi açmadan uygulamayı başlatan bir **Wipecord** ikonu koyar. Başlat menüsüne de eklemek için `-StartMenu` ekleyin. Kısayol yalnızca yerel kuruluma işaret eder — kodun ayrı bir kopyası oluşmaz, sisteme hiçbir şey kurulmaz.

## Kullanım

1. **Token** — yapıştırın, *Doğrula*'ya basın. Alan maskelidir; token sadece bellekte tutulur. Nerede bulacağınızı bilmiyorsanız, alanın hemen altındaki **Token'ımı nasıl alırım?** bağlantısı onu tarayıcınızdan okumayı adım adım anlatır.
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

166 test, hiçbirinde ağ erişimi yok. Katmanlama `ui/ → engine → scanner → client → ratelimit`; `ui/` altındaki hiçbir şey tkinter import etmez, bütün akışın arayüzsüz test edilebilmesini sağlayan da budur.

## Lisans

MIT. Bkz. [LICENSE](LICENSE).
