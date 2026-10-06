# St. Augustine marine forecast monitor — beginner setup

Prepared October 6, 2026. Your carrier is **T-Mobile**, and your forecast sample is already in `sample.txt`. There are no bracketed fields to replace in the program. You do not need to learn programming or install Python on your computer. A computer makes the one-time setup much easier than an iPhone; afterward GitHub runs the checks with your computer and phone switched off. Your phone needs Wi-Fi or cellular data to receive a notification.

## What you are building

GitHub checks the official NWS API every three hours. A small Python program reads the Jacksonville coastal forecast, checks your two zones, and sends qualifying forecasts through the free ntfy iPhone app. It saves a fingerprint of the matching forecast in `state.json` inside your GitHub repository. A repository is simply a folder of files stored on GitHub. A workflow is GitHub's instruction sheet for running those files automatically.

The only required account is GitHub Free. The only required phone app is ntfy. No NOAA account, API key, paid server, Twilio subscription, Apple developer account, or ntfy subscription is needed. Notifications arrive in **ntfy**, rather than Apple's Messages app. ntfy does not use your phone number.

The zones are:

| Zone | Area |
| --- | --- |
| AMZ452 | Fernandina Beach to St. Augustine, out 20 nautical miles |
| AMZ454 | St. Augustine to Flagler Beach, out 20 nautical miles |

Either zone can trigger an alert; both zones' forecasts are included in the message. It does not require both zones to qualify.

## What the program reads

1. Ask `https://api.weather.gov/products/types/CWF/locations/JAX` for Jacksonville's coastal forecast products.
2. Select the newest FZUS52/KJAX/CWF product by its issue time.
3. Retrieve `https://api.weather.gov/products/{product-id}` and read its `productText`. This is the official API, not a scraped forecast webpage.
4. Find the AMZ452 and AMZ454 sections. NWS sometimes combines AMZ452 with AMZ450; the parser recognizes shortened zone codes in these combined headers.
5. Separate forecast headings such as TONIGHT, WEDNESDAY NIGHT, THURSDAY AND THURSDAY NIGHT, and FRIDAY THROUGH SATURDAY. Resolve their actual dates using the forecast's issue date in Florida time.
6. Read the main Seas numbers. A 1–2-foot range uses 2 feet for the threshold. If a forecast says seas build from 1–2 to 2–3 feet within one day/night period, the program uses 3 feet and that whole period does not qualify.
7. Read an explicit Dominant period first. You selected the fallback that uses the period of the **tallest Wave Detail component** when no Dominant period appears. This is an estimate, not an NWS statement of dominant period. An asterisk identifies it. When tallest components tie, the shortest period controls; when they change after “becoming,” each stage must meet the period threshold. It never picks a smaller long-period swell just because it passes.
8. Notify when a day or night has Seas at most 2 feet AND period at least 7 seconds. A period range uses its lowest value. Missing periods show “period not listed” and never qualify.

The requested seven-day view means **today plus the next six calendar days**, Florida time. This CWF text often does not reach seven days, and later periods often omit wave periods. Every date is shown; absent dates say “forecast not available.” The program does not invent data or substitute a different forecast. A heading that explicitly covers multiple days supplies the same forecast values to those covered day/night slots. An absent nighttime period is not guessed from a daytime forecast.

Your sample is saved with NWS-style dotted headings instead of the surrounding brackets. Its conditions do not qualify. Friday and later lack listed wave periods. The second sample, `sample-match.txt`, is **invented test data** containing qualifying conditions and missing-period examples. It is never used by scheduled live checks.

“Occasionally to 3 feet” is displayed separately. The trigger still uses the main Seas range, as you requested, so “Seas 1–2 feet, occasionally to 3 feet” qualifies if its period qualifies. NWS Seas represent average heights of the highest third of waves, not a guarantee every wave is below 2 feet. This monitor is a criteria detector, not a declaration that conditions are safe; check winds, warnings, thunderstorms and the full marine forecast before going boating.

## Step 1 — Download and open the files

1. Download `marine-monitor.zip` from this conversation.
2. On Windows, right-click it and choose **Extract All**. On a Mac, double-click it. On an iPhone, save it to Files, then tap the ZIP to extract it.
3. Open the extracted `marine-monitor` folder. It contains the complete program and this guide.
4. Keep the files together. You will upload their contents to GitHub, rather than upload the ZIP itself.

## Step 2 — Install ntfy and choose your private topic

1. On your iPhone, open the App Store and install **ntfy**: https://apps.apple.com/us/app/ntfy/id1625396347 . It is the client for ntfy.sh.
2. Open the app. Allow notifications when asked.
3. Choose a long random topic privately. For example, use a password manager to generate **40 random letters and numbers**. The code requires 32–64 characters; letters, numbers, dashes and underscores are allowed. Do not use your name, phone number, a common phrase, or an example topic shared online. Do not paste the topic in this chat.
4. In ntfy, choose **Add subscription**, **Subscribe**, or the plus button, depending on the app version.
5. Use server **https://ntfy.sh** and paste your exact topic into the topic field. Save/subscribe. No login or paid plan is necessary.
6. Store that topic in your password manager. You will paste the identical value into a GitHub secret later.
7. On the iPhone, open **Settings → Notifications → ntfy**. Enable **Allow Notifications**, Lock Screen, Banners and Sounds. If a Focus mode suppresses notifications, allow ntfy in that Focus. If ntfy is in Scheduled Summary, remove it if you want immediate delivery.

Free anonymous ntfy topics are public to anyone who knows the topic name. The random name acts like a password; it is not an authenticated private channel. Messages contain only public forecast data, never your phone number. If the topic leaks, create a new random topic and change your subscription and GitHub secret. The current service limit is 4,096 bytes per notification and 250 messages per day; this program checks message size before sending. Tap a notification and open ntfy to read the entire summary if iOS truncates the banner.

## Step 3 — Create your free GitHub repository

1. Go to https://github.com and select **Sign up**, or sign in if you already have an account. Choose the free plan and verify your email.
2. Click the plus sign near the top-right and choose **New repository**. You can also visit https://github.com/new .
3. Name it `st-augustine-marine-monitor`.
4. Choose **Public** for unlimited free standard GitHub Actions runner use. The code, public forecast fixture and state fingerprints will be visible. Your GitHub Secrets are separate and are not public source files. Do not invite people to edit this repository unless you trust them with the notification settings.
5. Check **Add a README file** so GitHub creates the default branch immediately.
6. Click **Create repository**.

A private repository is an alternative. GitHub Free currently includes 2,000 Actions minutes per month across your private projects. Eight short runs a day should normally fit, but there is no guarantee and other projects share your quota. For a strictly free private setup, do not add a billing method, or configure a zero spending budget. Public plus standard Ubuntu runners is the simplest free option here.

## Step 4 — Upload the program files

1. In your repository's **Code** tab, select **Add file → Upload files**.
2. Drag these files from inside your extracted folder into the upload area: `monitor.py`, `sample.txt`, `sample-match.txt`, `live-api-fixture.json`, `state.json`, and `README.md`. Upload the **tests folder** too; it should preserve the path `tests/test_monitor.py`.
3. Do not drag the outer `marine-monitor` folder itself. `monitor.py` must be at the repository's top level, not inside an extra folder.
4. In the commit box, enter `Add marine monitor` and choose **Commit changes** directly to the default branch (usually `main`). A commit just means saving a set of file changes.
5. If your browser cannot drag the tests folder: choose **Add file → Create new file**, enter `tests/test_monitor.py` in the filename box, copy all the text from the supplied `tests/test_monitor.py`, and paste it into the editor. Click **Commit changes** and confirm.
6. Create the hidden workflow path separately. Choose **Add file → Create new file** and type exactly `.github/workflows/marine.yml` into the filename box. The leading dot is required.
7. Open the supplied `.github/workflows/marine.yml` in a plain text editor, copy everything, and paste it into GitHub's editor. If your computer hides the `.github` folder, on a Mac press Command+Shift+period; on Windows enable **View → Show → Hidden items**. For convenience an identical visible `marine.yml` is provided at the top level of the download; use its contents for this step. Do not merely upload it at the top level of the repository.
8. Click **Commit changes**, then confirm the save directly to `main`.
9. Check the repository file list: the top level should include `monitor.py`, both samples, the live fixture, `state.json`, `README.md`, `tests`, and `.github`. The workflow belongs in `.github/workflows/marine.yml`.

Do not edit the program's phone or topic settings. They are read from Secrets, not written in code. You do not need to upload `.gitignore`, but it is supplied for anyone later editing with Git.

## Step 5 — Add your notification secrets

1. Open the repository's **Settings** tab.
2. In the sidebar choose **Secrets and variables → Actions**.
3. Under **Repository secrets**, click **New repository secret**.
4. Name it exactly `NTFY_TOPIC`. Paste your random topic, with no surrounding quotes, into the secret value. Click **Add secret**.
5. Create another secret named `NWS_USER_AGENT`. Its value can be `StAugustineMarineMonitor/1.0 (contact: your actual email address)`, replacing the descriptive email words with your email. This identifies the app to NWS; it is not an API key.
6. Leave the carrier/SMTP secrets absent for now. ntfy does not need your phone number.

No ntfy account is required. No GitHub personal access token is required. GitHub supplies its workflow token automatically.

You selected Wave Detail fallback, and it is already the default. To change that later, in the same Settings area choose **Variables → New repository variable**, name it `PERIOD_MODE`, and set it to `strict`. Strict mode ignores Wave Detail for matching. Use `wave_detail` to restore your selected fallback.

## Step 6 — Allow the program to save its memory

1. In repository **Settings**, choose **Actions → General**.
2. Allow GitHub Actions if it is disabled. The workflow uses GitHub's own `actions/checkout` and `actions/setup-python` actions.
3. Find **Workflow permissions**. Select **Read and write permissions**, then click **Save**. This lets the workflow update its own `state.json` and monthly `keepalive.txt`.
4. If GitHub's rules prevent that choice or protect `main` against the workflow's commits, this setup needs an allowed write path. For a new personal repository, leave branch protection off. A failed state save can cause repeated alerts.

## Step 7 — Send a connection test to your iPhone

1. Click your repository's **Actions** tab. If prompted about enabling workflows, enable them.
2. Select **Marine Monitor** on the left. If it is missing, check the workflow filename and default branch in Step 4.
3. Click **Run workflow** on the right.
4. Leave the branch at `main`. In the mode dropdown choose **test**. Click the green **Run workflow** button.
5. Wait for the run to appear, then click it. Click the job named **monitor**. A green check means the tests and publish request completed successfully; it does not prove that your phone displayed the notification.
6. Your iPhone should show **Marine monitor connection test**. Confirm that it arrived with the phone locked and ntfy not in the foreground. Open ntfy to read it.
7. If it does not arrive, make sure the app's subscription matches the `NTFY_TOPIC` secret character for character, uses ntfy.sh, and that notification permissions/Focus/internet are correct. Look for a red failed step in Actions. The logs deliberately do not print your topic or credentials.

Do not rely on the monitor until you have personally received the test. I have tested the code and NWS parsing; I cannot confirm delivery to your particular phone before you set up your private topic.

## Step 8 — Test your supplied forecast, then a qualifying example

1. Repeat **Actions → Marine Monitor → Run workflow**, choosing **sample** this time.
2. Open the run and expand **Check forecast or run selected test**. You will see your sample's seven-date summary, with **Matching periods: 0**. No push should be sent.
3. Repeat with mode **sample-alert**. This sends both zones' summaries using the fictional qualifying example. The notification title and body say **TEST ONLY**. Tuesday night and Wednesday daytime should be marked ✅. Thursday's missing period must not match, and Friday's short period must not match.
4. Test modes do not change real alert memory, so they cannot suppress your first real notification.
5. Run mode **preview** next. This fetches the real current NWS forecast and prints the summary without notifying or changing memory.
6. Finally run **check**. This fetches the real forecast, notifies if it matches, and saves the matching fingerprint. If it does not match, no notification is expected.
7. If a real match exists, run **check** again. Unless qualifying values changed, the log should say **Matching forecast unchanged; duplicate suppressed**.

## Step 9 — Let it run automatically

The workflow checks every three hours at minute 17 in UTC: 00:17, 03:17, 06:17, 09:17, 12:17, 15:17, 18:17 and 21:17. You do not have to leave a browser, computer or iPhone running. ntfy delivers when your phone is reachable; it cannot notify a powered-off phone at that moment.

GitHub may delay scheduled jobs, and at heavy load it may drop queued jobs. Minute 17 avoids the busiest start-of-hour period, but does not guarantee timing. Public repositories' scheduled workflows can be disabled after 60 days without repository activity. This workflow makes a monthly `keepalive.txt` commit and commits changed alert state, which helps keep the repository active. Do not rely on that as an uptime guarantee: once disabled, the workflow cannot wake itself up.

About once a month, check **Actions** for recent successful scheduled runs. If needed, edit a sentence in README and commit it, or edit/save the schedule; if the workflow is disabled, open it in Actions and select **Enable workflow**, then run **check**. Simply opening the page is not the same as saving a change. Configure your GitHub notification preferences to email you about failed Actions runs. If NWS is unavailable or the forecast is over 24 hours old, the run fails rather than send a stale match.

To stop: **Actions → Marine Monitor → three-dot menu → Disable workflow**. Re-enable it there later. To change frequency, edit the workflow's cron line. `17 */6 * * *` means every six hours, for example. Keep the exact spacing.

## How duplicate prevention works

The saved fingerprint includes each qualifying zone/date/day-or-night, Seas range, selected period range, period source and occasional peak. A changed matching date or value sends a new complete summary. A new issue time, formatting change, wind wording or a change to a nonmatching day alone does not send another alert. If all matches disappear, memory resets silently; if conditions later qualify again, a new alert is sent. Losing some matching periods while others remain sends an updated summary because the match set changed. No cancellation message is sent when every match disappears.

State is stored as an actual repository file, not a disposable cache. Workflows are serialized to avoid simultaneous sends. The program saves state only after ntfy accepts the message. There is a small unavoidable duplicate window if ntfy accepts a push but the reply is lost, or if GitHub cannot save the resulting state. Exact-once delivery across two separate free services is not guaranteed. Publishing is not automatically retried, and a failed state-save step is visible in Actions. Check your phone before manually retrying a failed send.

## Optional T-Mobile email-to-text backup

Your carrier selection is T-Mobile. Its official support documentation still lists the legacy format **10-digit-number@tmomail.net**, but this does not establish that it still delivers on your line. I have not verified delivery. Keep this backup disabled unless T-Mobile confirms availability and you personally receive a test. The primary ntfy option works independently of the carrier gateway. Long forecasts can be split or truncated by carrier gateways, so the backup cannot guarantee the full ntfy summary.

If you want to try the free legacy backup:

1. From your existing email account, send a short plain-text test to your own 10-digit phone number followed by `@tmomail.net` (no `+1`, spaces or punctuation in the number). This guide deliberately does not print your number. A successful email send or lack of a bounce does not prove a text arrived.
2. If no text arrives, stop here and use ntfy. There is no guaranteed free SMS service supplied by this project.
3. If a text arrives, ask your email provider how to enable **SMTP over SSL on port 465** using an app password, rather than your regular login password. SMTP is the standard way the program submits an email. This requires an existing free email account that supports SMTP; provider rules vary.
4. For a free personal Gmail account, enable 2-Step Verification and create an app password if your account supports it: https://support.google.com/accounts/answer/185833 . Set host `smtp.gmail.com` and port `465`; use your complete Gmail address for user/from, and the app password for password. Gmail SMTP guidance: https://developers.google.com/workspace/gmail/imap/imap-smtp . Some accounts do not offer app passwords; use ntfy if yours does not. Never paste credentials into source code or chat.
5. Add these **Repository secrets**, following Step 5:

| Secret | Value |
| --- | --- |
| PHONE_NUMBER | Your own 10-digit mobile number, digits only |
| CARRIER_GATEWAY | tmomail.net, only after it was verified on your line |
| SMTP_HOST | Your provider's SSL SMTP hostname |
| SMTP_PORT | 465 |
| SMTP_USER | Your email login address |
| SMTP_PASSWORD | Your email app password |
| SMTP_FROM | The email address you are authorized to send from |

6. Under **Variables**, create `GATEWAY_ENABLED` with value `true`.
7. Run mode **test** again and verify both the ntfy push and carrier text. Run **sample-alert** and check whether the entire multi-day summary survives. If it is cut off, treat it only as a pointer to open ntfy.
8. Set `GATEWAY_ENABLED` to `false` whenever the backup stops delivering. SMTP acceptance proves only email submission, not delivery to Messages.

When enabled, it sends a second copy after ntfy succeeds. It is an additional delivery channel, not automatic failover when ntfy rejects a send. A backup failure cannot unsend the primary alert; live runs report backup errors while preserving primary-send memory. Current ntfy does not permit anonymous email forwarding, so this project uses your own email provider only for the optional backup.

## Files and verification

All working code is in the download. Python uses only its standard library: there is nothing extra to buy or install. `live-api-fixture.json` is a public NWS response captured during development, used only for repeatable parser testing. The tests also cover thresholds, ranges, missing periods, combined zones/headings, tied wave components, changing conditions, midnight dates, duplicate suppression and failed delivery. They run before every workflow execution. There is no real phone-delivery assertion in an automated unit test.

For anyone choosing to run it locally later, open a terminal in this folder and use `python3 -m unittest discover -s tests -v`, `python3 monitor.py --mode sample`, or `python3 monitor.py --mode preview`. Set secrets as environment variables before using a sending mode. The GitHub steps above avoid needing any terminal commands.

Official references checked for this setup:

- NWS zone list: https://www.weather.gov/marine/jaxmz
- NWS API: https://www.weather.gov/documentation/services-web-api
- NWS Wave Detail explanation: https://www.weather.gov/media/sew/2024WaveDetailWR.pdf
- ntfy publishing, topic privacy and limits: https://docs.ntfy.sh/publish/
- ntfy iPhone app: https://apps.apple.com/us/app/ntfy/id1625396347
- GitHub scheduled-workflow limitations: https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule
- GitHub free Actions allowances: https://docs.github.com/en/billing/concepts/product-billing/github-actions
- GitHub Secrets setup: https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets
- T-Mobile's legacy address listing: https://www.t-mobile.com/support/devices/not-sold-by-t-mobile/byod-t-mobile-data-and-apn-settings

If any step is unclear, tell me its step number and the words you see on your screen. Keep secret values private.
