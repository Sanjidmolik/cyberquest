"""
Practice scenarios for the five defence courses that had none:
Online Safety, Malware & Ransomware, Device & Data, Social Media & Privacy,
and Attack Response & Recovery.

Same engine as every other scenario (briefing -> investigate -> decide ->
consequence). They use the flexible "panels" workspace so each course looks
different: browser bars, alert tables, settings, chat threads, timelines.

Fictional people, organisations and example domains only. Every activity
is defensive: spot, contain, protect, report, recover.
"""

from .scenario_pool import _dec, _inv, _n, _scene


def _rows(title, rows, kind="rows"):
    """rows: list of (label, value) or (label, value, flagged)."""
    return {
        "title": title,
        "kind": kind,
        "rows": [{"label": r[0], "value": r[1], "flag": bool(r[2]) if len(r) > 2 else False} for r in rows],
    }


def _table(title, head, rows, flagged=()):
    return {"title": title, "kind": "table", "head": head, "rows": rows, "flagged": list(flagged)}


def _messages(title, items):
    """items: list of (sender, text) or (sender, text, flagged)."""
    return {
        "title": title,
        "kind": "messages",
        "items": [{"from": i[0], "text": i[1], "flag": bool(i[2]) if len(i) > 2 else False} for i in items],
    }


DEFENCE_SCENARIOS = {
    # =================================================================
    # Course 1 - Cyber Security & Online Safety  (domain: safety)
    # =================================================================
    "safety_fake_download": {
        "key": "safety_fake_download",
        "domain": "safety",
        "activity_type": "simulation",
        "difficulty": "beginner",
        "environment": "Safe Browsing Lab",
        "workspace_type": "panels",
        "incident_code": "CQ-OS-001",
        "severity": "MEDIUM",
        "title": "Free textbook download with a browser warning",
        "objective": "Check the address, the file and the browser warning before anything is installed.",
        "briefing": {
            "employee": "Riya (first-year student)",
            "department": "Northbridge University (fictional)",
            "subject": "\"Free PDF of the course textbook\"",
            "time": "11:40 PM",
            "summary": "Riya found a site offering the expensive course textbook for free. It wants her to install a 'PDF Reader Pro' first, and the browser just showed a yellow warning. Inspect the page before she clicks Install.",
        },
        "workspace": {"panels": [
            _rows("Address bar", [
                ("Address", "http://free-textbooks-download.example/reader", True),
                ("Connection", "Not secure (no HTTPS)", True),
            ], kind="url"),
            _rows("Page content", [
                ("Headline", "DOWNLOAD ANY TEXTBOOK FREE - 2 SECONDS LEFT!", True),
                ("Button", "Install PDF Reader Pro to open the book"),
                ("Pop-up", "Your PC may be slow. Allow notifications to continue."),
            ]),
            _rows("Browser download bar", [
                ("File", "textbook.pdf.exe (18 MB)", True),
                ("Browser says", "This type of file can harm your device. Keep anyway?", True),
            ]),
        ]},
        "hint": "Look at three things in order: the real web address, the file's last extension, and what the browser itself is telling you.",
        "takeaways": [
            "A real PDF never needs you to install a special program first.",
            "Read the last extension of a file: '.pdf.exe' is a program, not a document.",
            "Browser warnings come from your own browser and are worth trusting. Pop-ups inside a page are not.",
        ],
        "required_evidence": ["check_address", "check_file", "read_warning"],
        "missing_evidence_penalty": -10,
        "investigations": {
            "check_address": _inv("Check the Address Bar", 12, "Address Check", [
                {"label": "Domain", "value": "free-textbooks-download.example"},
                {"label": "Owner", "value": "Not the publisher or the university library"},
                {"label": "HTTPS", "value": "None - data is sent unencrypted"},
            ], "The site is unrelated to the publisher or library and does not even use HTTPS."),
            "check_file": _inv("Inspect the Download", 12, "File Details", [
                {"label": "Full name", "value": "textbook.pdf.exe"},
                {"label": "Real type", "value": "Windows program (.exe)"},
                {"label": "Signed by", "value": "Unknown publisher"},
            ], "The '.pdf' is a disguise. The file is an unsigned program."),
            "read_warning": _inv("Read the Browser Warning", 12, "Browser Protection", [
                {"label": "Source", "value": "Built-in browser download protection"},
                {"label": "Message", "value": "This file is not commonly downloaded and may be dangerous"},
            ], "This warning comes from the browser itself, not the website, so it is trustworthy."),
            "check_library": _inv("Search the Library Catalogue", 10, "Safe Alternative", [
                {"label": "University library", "value": "E-book available free for enrolled students"},
                {"label": "Access", "value": "Sign in through the official library portal"},
            ], "A legitimate free copy already exists through the library."),
            "check_popup": _inv("Inspect the Pop-up", 8, "Pop-up Analysis", [
                {"label": "Request", "value": "Allow notifications"},
                {"label": "Effect if allowed", "value": "Site can push ads and fake alerts to the desktop"},
            ], "Allowing notifications from this site would let it spam fake alerts later."),
        },
        "decisions": {
            "leave_use_library": _dec(
                "Leave the Site and Use the Library E-book", "correct", 40,
                "Device stays clean",
                "Riya closes the tab, deletes nothing because nothing was downloaded, and opens the free library copy instead.",
                "Safe source used, nothing installed"),
            "install_anyway": _dec(
                "Click 'Keep anyway' and Install", "unsafe", -30,
                "Unknown program running",
                "The 'reader' was adware with a hidden installer. The laptop is now showing pop-ups and needs a full scan.",
                "Malware installed from a fake download"),
            "allow_notifications": _dec(
                "Allow Notifications, but Don't Install", "poor", -15,
                "Spam alerts begin",
                "Nothing was installed, but the site can now push fake 'virus found' alerts to the desktop.",
                "Partial: no install, but a new scam channel opened"),
            "scan_then_open": _dec(
                "Download It, Then Scan It Before Opening", "poor", -10,
                "Risky shortcut",
                "Antivirus may catch it, but a fresh threat might slip through. Downloading untrusted programs at all is the mistake.",
                "Relied on the scanner instead of the safe source"),
        },
        "scene": _scene([
            _n("browser", "Riya's browser", 8, 22, 12),
            _n("site", "Free-textbook site", 38, 30, 20),
            _n("file", "textbook.pdf.exe", 68, 20, 18),
            _n("library", "Library e-book", 74, 64, 10),
        ], ["site", "file"], {
            "check_address": "site", "check_file": "file", "read_warning": "browser",
            "check_library": "library", "check_popup": "site",
        }),
    },
    "safety_fake_alert": {
        "key": "safety_fake_alert",
        "domain": "safety",
        "activity_type": "incident",
        "difficulty": "intermediate",
        "environment": "Safe Browsing Lab",
        "workspace_type": "panels",
        "incident_code": "CQ-OS-002",
        "severity": "HIGH",
        "title": "Full-screen 'virus detected' alert and a call-now number",
        "objective": "Tell a scam pop-up apart from a real security alert, and respond without calling or paying.",
        "briefing": {
            "employee": "Tanvir (second-year student)",
            "department": "Northbridge University (fictional)",
            "subject": "\"5 VIRUSES FOUND - CALL SUPPORT NOW\"",
            "time": "09:12 PM",
            "summary": "While streaming a match, Tanvir's browser went full screen with a red alert, a siren sound and a phone number for 'Windows Support'. He is about to call. Investigate what is really happening.",
        },
        "workspace": {"panels": [
            _rows("Browser window", [
                ("Address", "https://pc-security-alert.example/scan?id=4471", True),
                ("Display", "Full screen, siren audio playing", True),
            ], kind="url"),
            _rows("Alert text", [
                ("Headline", "WARNING! 5 VIRUSES DETECTED ON YOUR PC", True),
                ("Instruction", "Call Microsoft Support at +1-555-0142 immediately", True),
                ("Threat", "Your bank details will be stolen in 3 minutes"),
            ]),
            _table("Your real security app (Windows Security)", ["Check", "Status"], [
                ["Real-time protection", "On"],
                ["Last scan", "Today 08:30 - no threats"],
                ["Current threats", "None"],
            ]),
        ]},
        "hint": "Ask yourself who is showing this alert: the website in your browser, or the security app installed on your device?",
        "takeaways": [
            "Websites cannot scan your computer. Alerts inside a browser page are advertising or scams.",
            "Real companies never put a phone number in a pop-up and ask you to call.",
            "Close the tab (or press Esc / Ctrl+W, or end the browser in Task Manager), then check your real security app.",
        ],
        "required_evidence": ["check_source", "check_number", "check_av"],
        "missing_evidence_penalty": -10,
        "investigations": {
            "check_source": _inv("Check Where the Alert Comes From", 12, "Alert Source", [
                {"label": "Shown by", "value": "A website tab (pc-security-alert.example)"},
                {"label": "Can a website scan your PC?", "value": "No"},
            ], "The alert is a web page pretending to be a system message."),
            "check_number": _inv("Look Up the Support Number", 12, "Number Lookup", [
                {"label": "Number in alert", "value": "+1-555-0142"},
                {"label": "Official support contact", "value": "Microsoft does not list phone numbers in pop-ups"},
                {"label": "Known pattern", "value": "Tech-support scam: remote access + payment by gift card"},
            ], "Calling connects to scammers who ask for remote access and payment."),
            "check_av": _inv("Open Windows Security", 12, "Real Security Status", [
                {"label": "Real-time protection", "value": "On"},
                {"label": "Threats found", "value": "None"},
            ], "Your real security app shows no threats, which contradicts the pop-up."),
            "check_urgency": _inv("Read the Pressure Tactics", 8, "Manipulation Check", [
                {"label": "Countdown claim", "value": "'Bank details stolen in 3 minutes'"},
                {"label": "Siren + full screen", "value": "Designed to cause panic"},
            ], "Panic and urgency are tools to stop you thinking clearly."),
            "check_history": _inv("Check How You Got Here", 8, "Browsing History", [
                {"label": "Previous page", "value": "Free sports-streaming site"},
                {"label": "Redirect", "value": "Ad click opened the alert page"},
            ], "A malicious ad on the streaming site redirected to the scam page."),
        },
        "decisions": {
            "close_and_check": _dec(
                "Close the Tab, Then Run a Quick Scan", "correct", 40,
                "Scam closed, device confirmed clean",
                "Tanvir closes the page (Ctrl+W, or ends the browser in Task Manager), runs a quick scan that finds nothing, and avoids the streaming site.",
                "Scam dismissed safely"),
            "call_number": _dec(
                "Call the Number on Screen", "unsafe", -35,
                "Scammer gains remote access",
                "The 'technician' asks to install remote-access software and charges for a fake repair with gift cards.",
                "Remote access and money lost"),
            "pay_for_cleaner": _dec(
                "Buy the 'Cleaner' the Page Offers", "unsafe", -30,
                "Fake software purchased",
                "The 'cleaner' is useless software, and the card number was entered on a scam site.",
                "Card details exposed"),
            "restart_only": _dec(
                "Just Restart the Laptop", "poor", -10,
                "Pop-up gone, cause unknown",
                "Restarting closes the page, but without checking the real security app or avoiding the site, it can happen again.",
                "Partial: closed but not verified"),
        },
        "scene": _scene([
            _n("stream", "Streaming site ad", 8, 22, 10),
            _n("popup", "Fake alert page", 40, 26, 22),
            _n("phone", "Scam phone number", 72, 18, 16),
            _n("av", "Windows Security", 70, 66, 10),
        ], ["popup", "phone"], {
            "check_source": "popup", "check_number": "phone", "check_av": "av",
            "check_urgency": "popup", "check_history": "stream",
        }),
    },

    # =================================================================
    # Course 4 - Malware & Ransomware Protection  (domain: malware)
    # =================================================================
    "malware_av_alert": {
        "key": "malware_av_alert",
        "domain": "malware",
        "activity_type": "simulation",
        "difficulty": "beginner",
        "environment": "Endpoint Protection Console",
        "workspace_type": "panels",
        "incident_code": "CQ-MW-001",
        "severity": "MEDIUM",
        "title": "Antivirus quarantined a cracked game installer",
        "objective": "Read a real antivirus alert, find where the file came from, and choose a safe clean-up.",
        "briefing": {
            "employee": "Tanvir's laptop (LAPTOP-TANVIR)",
            "department": "Personal device (fictional)",
            "subject": "Microsoft Defender: Threat quarantined",
            "time": "06:05 PM",
            "summary": "Tanvir downloaded a 'free' cracked copy of a paid game. Seconds later his antivirus showed an alert. He wants to restore the file so the game works. Inspect the alert first.",
        },
        "workspace": {"panels": [
            _table("Protection history", ["Time", "Item", "Action"], [
                ["18:05", "Trojan:Win32/FakeInst in Downloads\\game_crack_setup.exe", "Quarantined"],
                ["Yesterday", "Scheduled scan", "No threats"],
            ], flagged=[0]),
            _rows("Alert details", [
                ("Severity", "Severe", True),
                ("Category", "Trojan"),
                ("Options offered", "Remove / Restore / Allow on device"),
            ]),
            _rows("Download source", [
                ("Site", "games-free-crack.example/download", True),
                ("File signed by", "Unknown publisher", True),
            ]),
        ]},
        "hint": "The antivirus already did its job. Your choice is what to do with the quarantined file and the habit that brought it in.",
        "takeaways": [
            "Quarantine means the file is locked away and cannot run. Restoring it undoes that protection.",
            "Cracked and 'free' paid software is one of the most common ways malware gets in.",
            "After a detection, remove the threat, run a full scan, and change how you download software.",
        ],
        "required_evidence": ["read_alert", "check_source", "check_other_items"],
        "missing_evidence_penalty": -10,
        "investigations": {
            "read_alert": _inv("Read the Alert", 12, "Threat Details", [
                {"label": "Name", "value": "Trojan:Win32/FakeInst"},
                {"label": "Behaviour", "value": "Pretends to install a game, then installs other programs"},
                {"label": "Current state", "value": "Quarantined - cannot run"},
            ], "This is a Trojan disguised as a game installer, and it is already contained."),
            "check_source": _inv("Check the Download Source", 12, "Source Check", [
                {"label": "Website", "value": "games-free-crack.example (not the game publisher)"},
                {"label": "Signature", "value": "Unsigned"},
            ], "The file came from a piracy site, not the official store."),
            "check_other_items": _inv("Check Other Downloads", 10, "Downloads Folder", [
                {"label": "Other new files", "value": "None since 17:50"},
                {"label": "New startup programs", "value": "None"},
            ], "No other suspicious files were added, so the quarantine caught it early."),
            "run_full_scan": _inv("Run a Full Scan", 10, "Full Scan Result", [
                {"label": "Items scanned", "value": "412,903"},
                {"label": "Threats found", "value": "0 active (1 already in quarantine)"},
            ], "The rest of the device is clean."),
        },
        "decisions": {
            "remove_and_buy_official": _dec(
                "Remove the Threat and Get the Game Officially", "correct", 40,
                "Threat removed, device clean",
                "Tanvir removes the quarantined file, confirms a clean full scan, and buys or downloads the game only from the official store.",
                "Threat removed, safer habit adopted"),
            "restore_file": _dec(
                "Restore the File So the Game Works", "unsafe", -35,
                "Trojan released",
                "Restoring takes the Trojan out of quarantine. It installs adware and a browser hijacker on the next run.",
                "Malware re-activated by the user"),
            "allow_on_device": _dec(
                "Mark It 'Allowed' to Stop Future Alerts", "unsafe", -30,
                "Protection weakened",
                "Allowing the file tells the antivirus to ignore it, and similar threats, in future.",
                "Antivirus told to ignore real malware"),
            "ignore_alert": _dec(
                "Do Nothing - It's Quarantined Anyway", "poor", -10,
                "Contained, but the habit continues",
                "The file stays contained, but no scan was run and the risky download habit isn't addressed.",
                "Partial response"),
        },
        "scene": _scene([
            _n("site", "Crack website", 8, 20, 10),
            _n("file", "game_crack_setup.exe", 40, 30, 22),
            _n("av", "Antivirus quarantine", 70, 20, 16),
            _n("laptop", "LAPTOP-TANVIR", 72, 64, 12),
        ], ["site", "file"], {
            "read_alert": "av", "check_source": "site", "check_other_items": "laptop", "run_full_scan": "laptop",
        }),
    },
    "malware_ransomware_note": {
        "key": "malware_ransomware_note",
        "domain": "malware",
        "activity_type": "incident",
        "difficulty": "intermediate",
        "environment": "Endpoint Protection Console",
        "workspace_type": "panels",
        "incident_code": "CQ-MW-002",
        "severity": "CRITICAL",
        "title": "Ransomware note on the student-society laptop",
        "objective": "Contain a ransomware infection, protect the backups and recover without paying.",
        "briefing": {
            "employee": "Debate Society shared laptop (SOC-LAPTOP-02)",
            "department": "Student union, Northbridge University (fictional)",
            "subject": "\"YOUR FILES ARE ENCRYPTED\"",
            "time": "08:47 AM",
            "summary": "The society's shared laptop shows a ransom note and every file ends in '.locked'. A USB backup drive is still plugged in, and the laptop is on campus Wi-Fi. The treasurer wants to pay so the event files come back today.",
        },
        "workspace": {"panels": [
            _messages("Ransom note on screen", [
                ("LOCKBYTE", "All your documents are encrypted. Pay 0.05 BTC within 48 hours or the key is deleted.", True),
                ("LOCKBYTE", "Do not contact anyone. Do not turn off the computer.", True),
            ]),
            _table("Device status", ["Item", "Status"], [
                ["Network", "Connected to campus Wi-Fi"],
                ["USB backup drive (E:)", "Plugged in - files changing"],
                ["Files in Documents", "1,204 renamed to *.locked"],
                ["Cloud folder", "Syncing changes"],
            ], flagged=[0, 1, 3]),
            _rows("Backups available", [
                ("Cloud version history", "Keeps copies for 30 days"),
                ("Offline USB from last Friday", "In the treasurer's drawer, unplugged"),
            ]),
        ]},
        "hint": "Ransomware spreads to anything connected. Think 'disconnect first', then 'which copy is still clean?'",
        "takeaways": [
            "First disconnect: unplug network and USB drives so the damage cannot spread.",
            "Do not pay. Payment does not guarantee recovery and funds more attacks.",
            "Recover from a clean, offline or versioned backup after the device is wiped or reset.",
        ],
        "required_evidence": ["check_connections", "check_backups", "check_entry"],
        "missing_evidence_penalty": -15,
        "investigations": {
            "check_connections": _inv("Check What Is Connected", 12, "Live Connections", [
                {"label": "USB backup (E:)", "value": "Being encrypted right now"},
                {"label": "Wi-Fi", "value": "Connected - other devices reachable"},
                {"label": "Cloud sync", "value": "Uploading .locked files"},
            ], "Everything connected is at risk. Disconnecting is urgent."),
            "check_backups": _inv("Check the Backups", 12, "Backup Review", [
                {"label": "Offline USB (last Friday)", "value": "Unplugged - not affected"},
                {"label": "Cloud version history", "value": "Can roll back to before 08:30"},
            ], "Clean copies exist, so paying is unnecessary."),
            "check_entry": _inv("Find How It Got In", 12, "Entry Point", [
                {"label": "Downloads folder", "value": "Invoice_Debate_Venue.zip opened 08:28"},
                {"label": "Email", "value": "From a lookalike venue address"},
            ], "A phishing attachment started the infection."),
            "check_note": _inv("Read the Ransom Note Carefully", 8, "Note Analysis", [
                {"label": "Threat", "value": "Pay in 48 hours, tell no one"},
                {"label": "Guarantee", "value": "None - criminals may never send a key"},
            ], "The note uses secrecy and deadlines to pressure victims."),
            "photograph_note": _inv("Photograph the Note for Evidence", 8, "Evidence Saved", [
                {"label": "Saved", "value": "Photo of the note, time, and file extension"},
            ], "Evidence helps IT support and any report to the authorities."),
        },
        "decisions": {
            "isolate_report_restore": _dec(
                "Disconnect, Report to IT, Wipe and Restore from Clean Backups", "correct", 40,
                "Files recovered without paying",
                "The laptop is unplugged from Wi-Fi and USB, IT resets it, and the event files are restored from cloud version history and Friday's offline copy.",
                "Contained and recovered"),
            "pay_ransom": _dec(
                "Pay the Ransom to Get Files Back Today", "unsafe", -40,
                "Paid, no key arrived",
                "The payment is sent. No decryption key arrives, and the society is now marked as willing to pay.",
                "Money lost, files still locked"),
            "restore_while_connected": _dec(
                "Restore Backups Straight onto the Infected Laptop", "unsafe", -30,
                "Backups encrypted too",
                "The malware is still running, so it encrypts the freshly restored files and the backup drive.",
                "Clean backups destroyed"),
            "unplug_only": _dec(
                "Unplug Everything and Wait", "poor", -10,
                "Contained but not recovered",
                "Disconnecting stops the spread, but nobody reports it, the device isn't cleaned, and the files stay locked.",
                "Partial containment"),
        },
        "scene": _scene([
            _n("mail", "Phishing attachment", 8, 22, 10),
            _n("laptop", "SOC-LAPTOP-02", 40, 28, 22),
            _n("usb", "USB backup (E:)", 70, 18, 16),
            _n("cloud", "Cloud versions", 72, 64, 12),
        ], ["laptop", "usb"], {
            "check_connections": "usb", "check_backups": "cloud", "check_entry": "mail",
            "check_note": "laptop", "photograph_note": "laptop",
        }),
    },

    # =================================================================
    # Course 6 - Device & Personal Data Protection  (domain: device)
    # =================================================================
    "device_app_permissions": {
        "key": "device_app_permissions",
        "domain": "device",
        "activity_type": "simulation",
        "difficulty": "beginner",
        "environment": "Device Settings Audit",
        "workspace_type": "panels",
        "incident_code": "CQ-DV-001",
        "severity": "MEDIUM",
        "title": "Flashlight app with far too many permissions",
        "objective": "Audit app permissions and remove access an app does not need.",
        "briefing": {
            "employee": "Riya's phone",
            "department": "Personal device (fictional)",
            "subject": "Battery draining, unknown texts sent",
            "time": "Tuesday, 07:30 PM",
            "summary": "Riya's phone battery drains fast and two friends got strange texts 'from her'. She recently installed 'Super Bright Torch'. Open the settings audit and check what that app can do.",
        },
        "workspace": {"panels": [
            _table("Super Bright Torch - permissions", ["Permission", "Status"], [
                ["Camera (flash)", "Allowed"],
                ["Contacts", "Allowed"],
                ["SMS - send and read", "Allowed"],
                ["Location - always", "Allowed"],
                ["Microphone", "Allowed"],
            ], flagged=[1, 2, 3, 4]),
            _rows("App details", [
                ("Developer", "TorchFast Labs (unverified)", True),
                ("Installed from", "APK link in a group chat", True),
                ("Background data", "220 MB this week", True),
            ]),
            _table("Other apps (sample)", ["App", "Location"], [
                ["Maps", "While using"],
                ["Campus Bus", "While using"],
                ["Weather", "Always"],
            ], flagged=[2]),
        ]},
        "hint": "For each permission ask: does a flashlight need this to make light?",
        "takeaways": [
            "Permissions should match an app's job. A flashlight needs the camera flash and nothing else.",
            "Install apps only from the official store, never from links in chats.",
            "Review permissions regularly and use 'While using the app' or 'Ask every time' for location.",
        ],
        "required_evidence": ["review_permissions", "check_install_source", "check_sms_log"],
        "missing_evidence_penalty": -10,
        "investigations": {
            "review_permissions": _inv("Review Each Permission", 12, "Permission Audit", [
                {"label": "Needed for a torch", "value": "Camera (flash) only"},
                {"label": "Not needed", "value": "Contacts, SMS, location always, microphone"},
            ], "Four of five permissions have nothing to do with a flashlight."),
            "check_install_source": _inv("Check Where It Came From", 12, "Install Source", [
                {"label": "Source", "value": "APK file from a group-chat link"},
                {"label": "Official store listing", "value": "None"},
            ], "Sideloaded apps skip the store's safety checks."),
            "check_sms_log": _inv("Check the Sent Messages", 12, "SMS Log", [
                {"label": "Sent by app", "value": "2 texts with a download link to contacts"},
                {"label": "Time", "value": "03:12 AM, while Riya was asleep"},
            ], "The app used SMS access to spread itself to her contacts."),
            "check_battery": _inv("Check Battery and Data Use", 8, "Battery Usage", [
                {"label": "Top battery user", "value": "Super Bright Torch (38%)"},
                {"label": "Background data", "value": "220 MB"},
            ], "A torch should not run in the background using data."),
            "check_other_apps": _inv("Review Other Apps' Location Access", 8, "Location Review", [
                {"label": "Weather", "value": "Always - could be 'While using'"},
            ], "Tightening location for other apps reduces tracking too."),
        },
        "decisions": {
            "uninstall_warn_review": _dec(
                "Uninstall the App, Warn Contacts, Tighten Other Permissions", "correct", 40,
                "Phone back under control",
                "Riya uninstalls the torch, messages her friends not to tap the link, sets Weather to 'While using', and uses the built-in flashlight.",
                "Malicious app removed, exposure contained"),
            "deny_some": _dec(
                "Keep the App but Turn Off SMS Only", "poor", -15,
                "Still over-privileged",
                "SMS is blocked, but the app still reads contacts, tracks location and records audio permission.",
                "Partial: the risky app remains"),
            "ignore": _dec(
                "Ignore It - Battery Drain Is Normal", "unsafe", -30,
                "More friends targeted",
                "The app keeps texting her contacts and tracking her location.",
                "No action taken"),
            "factory_reset_first": _dec(
                "Factory Reset Straight Away Without Backing Up", "poor", -10,
                "Overkill and data lost",
                "The app is gone, but so are Riya's photos and notes, and her friends still have the bad link.",
                "Removed, but with unnecessary loss"),
        },
        "scene": _scene([
            _n("chat", "Group-chat APK link", 8, 20, 10),
            _n("app", "Super Bright Torch", 40, 30, 22),
            _n("sms", "SMS to contacts", 70, 18, 16),
            _n("phone", "Riya's phone", 72, 64, 12),
        ], ["app", "sms"], {
            "review_permissions": "app", "check_install_source": "chat", "check_sms_log": "sms",
            "check_battery": "phone", "check_other_apps": "phone",
        }),
    },
    "device_sharing_backup": {
        "key": "device_sharing_backup",
        "domain": "device",
        "activity_type": "incident",
        "difficulty": "intermediate",
        "environment": "Device Settings Audit",
        "workspace_type": "panels",
        "incident_code": "CQ-DV-002",
        "severity": "HIGH",
        "title": "Thesis folder shared with 'anyone with the link'",
        "objective": "Fix cloud sharing, check backups against the 3-2-1 rule and secure a lost laptop.",
        "briefing": {
            "employee": "Tanvir (final-year project)",
            "department": "Northbridge University (fictional)",
            "subject": "Laptop left on the bus",
            "time": "05:55 PM",
            "summary": "Tanvir left his laptop on the bus. His thesis folder is in cloud storage, but he once shared it with 'anyone with the link'. His only other copy is on a USB stick in the same bag. Audit what's exposed and what can be recovered.",
        },
        "workspace": {"panels": [
            _table("Cloud folder: Thesis_Final", ["Shared with", "Access"], [
                ["Anyone with the link", "Can edit"],
                ["supervisor@northbridge.example", "Can comment"],
                ["Old group-project chat (link posted)", "Can edit"],
            ], flagged=[0, 2]),
            _table("Backups", ["Copy", "Where", "Last updated"], [
                ["Laptop", "Lost on bus", "Today"],
                ["USB stick", "Same bag as laptop", "3 weeks ago"],
                ["Cloud folder", "Online", "Today (version history on)"],
            ], flagged=[0, 1]),
            _rows("Laptop security", [
                ("Disk encryption", "On (BitLocker)"),
                ("Screen lock", "PIN, 6 digits"),
                ("Find My Device", "On - last seen 17:41, bus depot"),
            ]),
        ]},
        "hint": "Split it into three questions: who can see the files right now, which copies still exist, and can the lost laptop be locked?",
        "takeaways": [
            "Share with named people and the least access they need. Review old links.",
            "3-2-1: three copies, two kinds of storage, one kept elsewhere. A USB in the same bag does not count.",
            "Encryption plus a screen lock keeps a lost device's data safe. Use Find My Device to lock or erase it.",
        ],
        "required_evidence": ["review_sharing", "review_backups", "check_device_security"],
        "missing_evidence_penalty": -10,
        "investigations": {
            "review_sharing": _inv("Review Sharing Settings", 12, "Sharing Audit", [
                {"label": "Public link", "value": "Anyone can edit - 41 views from unknown accounts"},
                {"label": "Old chat link", "value": "Still active"},
            ], "Strangers can open and even change the thesis."),
            "review_backups": _inv("Check the Backups", 12, "Backup Review", [
                {"label": "Copies left", "value": "Cloud only (USB lost with the bag)"},
                {"label": "3-2-1 status", "value": "Fails: one copy, one place"},
            ], "Only one safe copy remains. The backup plan needs fixing."),
            "check_device_security": _inv("Check the Lost Laptop's Protection", 12, "Device Protection", [
                {"label": "Encryption", "value": "On - files unreadable without the PIN"},
                {"label": "Find My Device", "value": "Available to lock or erase remotely"},
            ], "The data is protected, and the device can be locked remotely."),
            "check_version_history": _inv("Check Cloud Version History", 8, "Version History", [
                {"label": "Edits by unknown users", "value": "None so far"},
                {"label": "Restore points", "value": "Daily, last 30 days"},
            ], "No damage yet, and earlier versions can be restored if needed."),
            "contact_lost_property": _inv("Check the Bus Lost-Property Page", 8, "Lost Property", [
                {"label": "Report", "value": "Can be filed online with a description"},
            ], "Reporting the loss gives a chance to get the laptop back."),
        },
        "decisions": {
            "fix_lock_backup": _dec(
                "Remove Public Links, Lock the Laptop Remotely, Set Up a 3-2-1 Backup", "correct", 40,
                "Thesis safe, exposure closed",
                "Tanvir switches sharing to his supervisor only, locks the laptop with Find My Device, reports it lost, and adds an external drive plus cloud copy kept at home.",
                "Exposure removed and recovery plan in place"),
            "erase_only": _dec(
                "Erase the Laptop Remotely and Stop There", "poor", -15,
                "Laptop wiped, folder still public",
                "The device is safe, but strangers can still edit the thesis through the public link.",
                "Partial: sharing still open"),
            "wait_for_bus": _dec(
                "Wait to See if the Bus Company Finds It", "unsafe", -25,
                "Exposure continues",
                "The public link stays open and nothing is locked while he waits.",
                "No containment"),
            "delete_cloud_folder": _dec(
                "Delete the Cloud Folder to Hide It", "unsafe", -30,
                "Last copy deleted",
                "Deleting the folder removes the only remaining copy of the thesis.",
                "Data lost"),
        },
        "scene": _scene([
            _n("link", "Public share link", 8, 20, 10),
            _n("cloud", "Thesis cloud folder", 40, 30, 22),
            _n("laptop", "Lost laptop", 70, 18, 16),
            _n("usb", "USB in same bag", 72, 64, 12),
        ], ["link", "usb"], {
            "review_sharing": "link", "review_backups": "usb", "check_device_security": "laptop",
            "check_version_history": "cloud", "contact_lost_property": "laptop",
        }),
    },

    # =================================================================
    # Course 7 - Social Media & Digital Privacy  (domain: privacy)
    # =================================================================
    "privacy_impersonator": {
        "key": "privacy_impersonator",
        "domain": "privacy",
        "activity_type": "simulation",
        "difficulty": "beginner",
        "environment": "Social Profile Investigator",
        "workspace_type": "panels",
        "incident_code": "CQ-PV-001",
        "severity": "MEDIUM",
        "title": "A second 'Tanvir' asks for a verification code",
        "objective": "Investigate a duplicate profile and handle a social-engineering message safely.",
        "briefing": {
            "employee": "Riya",
            "department": "Northbridge University (fictional)",
            "subject": "\"Hey it's me, new account, send me the code?\"",
            "time": "10:20 PM",
            "summary": "Riya got a friend request and messages from 'Tanvir Ahmed'. She is already friends with Tanvir. The new account asks her to forward a 6-digit code she just received by SMS.",
        },
        "workspace": {"panels": [
            _rows("Profile: tanvir.ahmed.official2", [
                ("Created", "3 days ago", True),
                ("Photos", "2 (same as the real Tanvir's profile)", True),
                ("Friends", "14, mostly from Riya's class"),
            ]),
            _messages("Direct messages", [
                ("tanvir.ahmed.official2", "hey!! lost my old account, this is my new one"),
                ("tanvir.ahmed.official2", "i sent a code to your number by mistake, can you send it to me? urgent", True),
                ("SMS to Riya", "Your login code is 482913. Do not share it with anyone.", True),
            ]),
        ]},
        "hint": "Who is the code for, according to the SMS itself? And how could you check with the real Tanvir?",
        "takeaways": [
            "Never share a login or verification code. It is the key to your account.",
            "Check a 'new account' with the person through a channel you already trust.",
            "Report and block impersonators, and warn friends who may have accepted them.",
        ],
        "required_evidence": ["check_profile", "read_sms", "verify_friend"],
        "missing_evidence_penalty": -10,
        "investigations": {
            "check_profile": _inv("Inspect the Profile", 12, "Profile Check", [
                {"label": "Account age", "value": "3 days"},
                {"label": "Photos", "value": "Copied from the real Tanvir"},
                {"label": "Handle", "value": "'.official2' added to the name"},
            ], "A brand-new copy of a real friend's profile is a classic impersonation."),
            "read_sms": _inv("Read the SMS Carefully", 12, "Code Check", [
                {"label": "Code is for", "value": "Riya's own account login"},
                {"label": "Warning in SMS", "value": "Do not share it with anyone"},
            ], "The code would let the stranger take over Riya's account."),
            "verify_friend": _inv("Message the Real Tanvir", 12, "Out-of-band Check", [
                {"label": "Real Tanvir replies", "value": "That isn't me! I never lost my account."},
            ], "Checking through a trusted channel confirms the impersonation."),
            "check_mutuals": _inv("Check Mutual Friends", 8, "Mutual Friends", [
                {"label": "Accepted the fake", "value": "6 classmates"},
            ], "Other classmates may also be targeted."),
        },
        "decisions": {
            "report_block_warn": _dec(
                "Don't Send the Code; Report, Block and Warn Classmates", "correct", 40,
                "Takeover stopped",
                "Riya ignores the code, reports and blocks the fake profile, and posts a warning in the class group so others remove it too.",
                "Impersonation reported, account safe"),
            "send_code": _dec(
                "Send the Code - It's Tanvir", "unsafe", -35,
                "Account taken over",
                "The attacker logs into Riya's account and starts messaging her contacts for money.",
                "Account takeover"),
            "block_only": _dec(
                "Block the Account Quietly", "poor", -10,
                "Riya safe, classmates not",
                "Blocking protects Riya, but without reporting or warning others the fake keeps targeting her class.",
                "Partial response"),
            "argue": _dec(
                "Reply and Argue With the Account", "poor", -15,
                "Engaging the attacker",
                "Replying confirms the account is active and gives the attacker more chances to manipulate.",
                "Engaged with the scammer"),
        },
        "scene": _scene([
            _n("fake", "Fake profile", 8, 22, 14),
            _n("dm", "DM asking for code", 40, 28, 20),
            _n("sms", "Login code SMS", 70, 18, 16),
            _n("real", "Real Tanvir", 72, 64, 10),
        ], ["fake", "dm"], {
            "check_profile": "fake", "read_sms": "sms", "verify_friend": "real", "check_mutuals": "fake",
        }),
    },
    "privacy_oversharing": {
        "key": "privacy_oversharing",
        "domain": "privacy",
        "activity_type": "incident",
        "difficulty": "intermediate",
        "environment": "Social Profile Investigator",
        "workspace_type": "panels",
        "incident_code": "CQ-PV-002",
        "severity": "HIGH",
        "title": "Public profile reveals home, schedule and ID card",
        "objective": "Find what a stranger can learn from a public profile, then lock down sharing settings.",
        "briefing": {
            "employee": "Mina (club president)",
            "department": "Northbridge University (fictional)",
            "subject": "Creepy comment: \"see you at the gym at 7 :)\"",
            "time": "08:05 AM",
            "summary": "Mina got an anonymous comment that knows where she will be tonight. She doesn't know the person. Review her own public profile the way a stranger would, then fix it.",
        },
        "workspace": {"panels": [
            _table("Recent public posts", ["Post", "Audience"], [
                ["Photo outside my building (house number visible)", "Public"],
                ["'Gym every Mon/Wed 7pm!' with location tag", "Public"],
                ["New student ID card - finally!", "Public"],
                ["Club fundraiser poster", "Public"],
            ], flagged=[0, 1, 2]),
            _table("Privacy settings", ["Setting", "Current"], [
                ["Who can see future posts", "Public"],
                ["Who can find me by phone number", "Everyone"],
                ["Location tagging", "On by default"],
                ["Tag review", "Off"],
            ], flagged=[0, 1, 2, 3]),
            _messages("Comments", [
                ("anon_8812", "see you at the gym at 7 :)", True),
            ]),
        ]},
        "hint": "Read the profile like a stranger: where does she live, where will she be, and what could someone copy from her ID?",
        "takeaways": [
            "Small posts add up: an address, a routine and an ID photo together reveal a lot.",
            "Set default audience to Friends, turn off location tags and phone-number search, and turn on tag review.",
            "Don't engage a stranger who shows they're watching. Save evidence, block, report, and tell someone you trust.",
        ],
        "required_evidence": ["audit_posts", "audit_settings", "check_commenter"],
        "missing_evidence_penalty": -10,
        "investigations": {
            "audit_posts": _inv("Audit Public Posts as a Stranger", 12, "Exposure Review", [
                {"label": "Home", "value": "Building and house number visible"},
                {"label": "Routine", "value": "Gym Mon/Wed 7pm, location tagged"},
                {"label": "ID card", "value": "Name, student number and photo readable"},
            ], "Together these posts reveal where she lives, where she'll be, and identity details."),
            "audit_settings": _inv("Review Privacy Settings", 12, "Settings Review", [
                {"label": "Default audience", "value": "Public"},
                {"label": "Phone search", "value": "Anyone can find her by number"},
                {"label": "Location tags", "value": "Added automatically"},
            ], "The settings make everything public by default."),
            "check_commenter": _inv("Look at the Commenter's Account", 12, "Commenter Check", [
                {"label": "Account age", "value": "2 days, no photo, no friends"},
                {"label": "Other comments", "value": "Only on Mina's posts"},
            ], "A throwaway account focused on one person is a warning sign."),
            "screenshot": _inv("Save Evidence", 8, "Evidence Saved", [
                {"label": "Saved", "value": "Screenshot of the comment with date, time and username"},
            ], "Evidence matters if this needs reporting to the platform, campus security or police."),
        },
        "decisions": {
            "lockdown_report": _dec(
                "Lock Down Settings, Remove Risky Posts, Report and Tell Campus Security", "correct", 40,
                "Exposure reduced, support in place",
                "Mina sets posts to Friends, turns off location tags and phone search, deletes the ID and address photos, reports and blocks the account, and tells campus security and a friend before going to the gym.",
                "Privacy locked down and the threat reported"),
            "reply_back": _dec(
                "Reply 'Who Is This?'", "poor", -15,
                "Engagement encourages them",
                "Replying confirms she saw it and invites more contact. Nothing about her exposure has changed.",
                "Engaged without protecting herself"),
            "delete_comment_only": _dec(
                "Delete the Comment and Carry On", "unsafe", -25,
                "Evidence gone, exposure remains",
                "The comment disappears along with the evidence, while her address, routine and ID are still public.",
                "No protection, evidence lost"),
            "delete_account": _dec(
                "Delete the Whole Account Immediately", "poor", -10,
                "Overreaction, evidence lost",
                "The posts vanish, but so does the evidence. Reporting and fixing settings would protect her without losing her club page.",
                "Partial"),
        },
        "scene": _scene([
            _n("posts", "Public posts", 8, 22, 12),
            _n("settings", "Privacy settings", 40, 30, 20),
            _n("stranger", "anon_8812", 70, 18, 16),
            _n("mina", "Mina", 72, 64, 10),
        ], ["posts", "stranger"], {
            "audit_posts": "posts", "audit_settings": "settings", "check_commenter": "stranger", "screenshot": "mina",
        }),
    },

    # =================================================================
    # Course 8 - Cyber Attack Response & Recovery  (domain: response)
    # =================================================================
    "response_email_compromise": {
        "key": "response_email_compromise",
        "domain": "response",
        "activity_type": "simulation",
        "difficulty": "beginner",
        "environment": "Incident Response Desk",
        "workspace_type": "panels",
        "incident_code": "CQ-IR-001",
        "severity": "HIGH",
        "title": "Compromised university email sending spam",
        "objective": "Secure a hijacked email account in the right order and check for hidden attacker changes.",
        "briefing": {
            "employee": "Riya's university email",
            "department": "Northbridge University (fictional)",
            "subject": "200 spam messages sent overnight",
            "time": "07:10 AM",
            "summary": "Riya woke up to replies asking why she sent a 'shared document' link to her whole contact list. She can still log in. Triage the account and secure it.",
        },
        "workspace": {"panels": [
            _table("Recent sign-ins", ["Time", "Location", "Device"], [
                ["02:14", "Unknown country", "Linux, unknown browser"],
                ["Yesterday 18:02", "Campus Wi-Fi", "Riya's laptop"],
            ], flagged=[0]),
            _table("Mailbox rules", ["Rule", "Action"], [
                ["'Forward all'", "Forward every message to collect-box@mail.example"],
                ["'Hide replies'", "Move replies containing 'spam' to Archive"],
            ], flagged=[0, 1]),
            _rows("Security settings", [
                ("Recovery phone", "Changed at 02:20 to an unknown number", True),
                ("MFA", "Off", True),
            ]),
        ]},
        "hint": "Order matters: first shut the attacker out, then remove what they left behind, then tell the people affected.",
        "takeaways": [
            "Change the password from a clean device, then sign out all sessions and turn on MFA.",
            "Attackers hide forwarding rules and change recovery details, so check both.",
            "Warn contacts and report to the university IT team so they can protect others.",
        ],
        "required_evidence": ["review_signins", "review_rules", "review_recovery"],
        "missing_evidence_penalty": -10,
        "investigations": {
            "review_signins": _inv("Review Sign-ins", 12, "Sign-in Log", [
                {"label": "Suspicious session", "value": "02:14, unknown country, still active"},
            ], "Someone else is signed in right now."),
            "review_rules": _inv("Review Mailbox Rules", 12, "Hidden Rules", [
                {"label": "Forward all", "value": "Copies every email to an outside address"},
                {"label": "Hide replies", "value": "Hides complaints about the spam"},
            ], "The attacker set up secret forwarding and hid the evidence."),
            "review_recovery": _inv("Check Recovery Details", 12, "Recovery Check", [
                {"label": "Recovery phone", "value": "Changed by the attacker at 02:20"},
            ], "With this number the attacker could reset the password again."),
            "check_sent": _inv("Check Sent Items", 8, "Sent Items", [
                {"label": "Messages sent", "value": "203 with a fake 'shared document' link"},
            ], "Contacts received a phishing link from a trusted address."),
            "check_entry": _inv("Find the Cause", 8, "Root Cause", [
                {"label": "Last week", "value": "Signed in on a fake 'library login' page"},
                {"label": "Password", "value": "Same as an old gaming account"},
            ], "A phishing page captured the password, and it was reused elsewhere."),
        },
        "decisions": {
            "secure_in_order": _dec(
                "New Password, Sign Out All Sessions, Turn On MFA, Remove Rules, Fix Recovery, Warn Contacts", "correct", 40,
                "Account recovered",
                "The attacker is signed out, MFA blocks new attempts, the forwarding rule and fake recovery number are removed, contacts are warned and IT is told.",
                "Account secured and cleaned"),
            "password_only": _dec(
                "Change the Password Only", "poor", -15,
                "Attacker still reading mail",
                "The new password stops new logins, but the forwarding rule still copies every email to the attacker.",
                "Partial: hidden access remains"),
            "delete_spam": _dec(
                "Delete the Sent Spam and Hope Nobody Clicked", "unsafe", -30,
                "Attacker still in control",
                "The session, rule and recovery number all remain. The attacker sends a second wave.",
                "No containment"),
            "new_account": _dec(
                "Abandon the Account and Make a New One", "poor", -15,
                "Problem moved, not solved",
                "The hijacked account keeps spamming classmates under Riya's name.",
                "Compromised account left active"),
        },
        "scene": _scene([
            _n("attacker", "Unknown session", 8, 20, 14),
            _n("mailbox", "Riya's mailbox", 40, 30, 22),
            _n("rule", "Forwarding rule", 70, 18, 16),
            _n("contacts", "203 contacts", 72, 64, 10),
        ], ["attacker", "rule"], {
            "review_signins": "attacker", "review_rules": "rule", "review_recovery": "mailbox",
            "check_sent": "contacts", "check_entry": "mailbox",
        }),
    },
    "response_club_breach": {
        "key": "response_club_breach",
        "domain": "response",
        "activity_type": "incident",
        "difficulty": "intermediate",
        "environment": "Incident Response Desk",
        "workspace_type": "panels",
        "incident_code": "CQ-IR-002",
        "severity": "CRITICAL",
        "title": "Club payment page breach: triage, contain, recover",
        "objective": "Triage a breach timeline, preserve evidence, contain it, report it and plan recovery.",
        "briefing": {
            "employee": "Robotics Club website (fictional)",
            "department": "Club committee, Northbridge University",
            "subject": "Members report card charges after paying dues",
            "time": "Thursday, 04:30 PM",
            "summary": "Three members saw unknown card charges after paying club dues on the website. The site is run with a shared admin password. You are the committee's incident lead: work out what happened and respond.",
        },
        "workspace": {"panels": [
            _table("Timeline", ["When", "Event"], [
                ["Mon 21:10", "Admin login from unfamiliar device"],
                ["Mon 21:14", "Payment page script edited"],
                ["Tue-Thu", "47 members paid dues"],
                ["Thu 15:50", "3 members report card fraud"],
            ], flagged=[0, 1]),
            _rows("Site facts", [
                ("Admin accounts", "1 shared login used by 6 people", True),
                ("Admin password", "RoboClub2023 - also used on the old forum", True),
                ("MFA", "Off", True),
                ("Backups", "Nightly, kept 14 days"),
            ]),
            _messages("Committee chat", [
                ("Treasurer", "Should we just delete the site and pretend it didn't happen?", True),
                ("Secretary", "Members are asking if they should cancel their cards."),
            ]),
        ]},
        "hint": "Follow the incident cycle: identify, contain, preserve evidence, report and notify, recover, then improve.",
        "takeaways": [
            "Contain first (take the payment page offline) but keep evidence: logs and the edited script.",
            "Tell affected people quickly and clearly so they can protect themselves.",
            "Recover from a clean backup taken before the change, then fix the cause: unique passwords, personal accounts and MFA.",
        ],
        "required_evidence": ["review_timeline", "inspect_script", "check_access"],
        "missing_evidence_penalty": -15,
        "investigations": {
            "review_timeline": _inv("Review the Timeline", 12, "Timeline Analysis", [
                {"label": "First bad event", "value": "Mon 21:10 admin login from an unknown device"},
                {"label": "Exposure window", "value": "Mon 21:14 to now"},
            ], "Every member who paid since Monday night may be affected."),
            "inspect_script": _inv("Inspect the Edited Payment Script", 12, "Script Review", [
                {"label": "Change", "value": "Extra code sends card details to cardstats.example"},
                {"label": "Evidence", "value": "Copy saved with the edit time"},
            ], "The change copied card details to an outside server."),
            "check_access": _inv("Check How the Attacker Got In", 12, "Access Review", [
                {"label": "Password", "value": "Same as the old forum, which leaked last year"},
                {"label": "Shared login + no MFA", "value": "No way to tell who logged in"},
            ], "A reused, shared password with no MFA let the attacker in."),
            "check_backups": _inv("Check Backups", 8, "Backup Review", [
                {"label": "Clean backup", "value": "Monday 02:00, before the change"},
            ], "A clean copy from before the attack can be restored."),
            "list_affected": _inv("List Affected Members", 8, "Impact List", [
                {"label": "Paid during window", "value": "47 members"},
            ], "These are the people who need to be told."),
        },
        "decisions": {
            "full_response": _dec(
                "Take Payments Offline, Save Evidence, Notify Members and the University, Restore Clean Backup, Fix Access", "correct", 40,
                "Breach contained and recovered",
                "The payment page is disabled, logs and the script are preserved, the 47 members and the university IT and student-union teams are told to contact their banks, the site is restored from Monday's backup, and each admin gets a personal account with MFA.",
                "Full incident response cycle"),
            "delete_site": _dec(
                "Delete the Website and Say Nothing", "unsafe", -40,
                "Evidence destroyed, members unprotected",
                "Deleting the site destroys the evidence, and members never learn they should contact their banks.",
                "Cover-up"),
            "password_change_only": _dec(
                "Just Change the Admin Password", "poor", -15,
                "Card skimming continues",
                "The edited script is still live, so new payments are still stolen.",
                "Cause partly fixed, harm continues"),
            "restore_without_evidence": _dec(
                "Restore the Backup Immediately, Skip the Evidence", "poor", -10,
                "Fixed, but nothing to report",
                "The site is clean again, but without logs or the script nobody can explain what happened or help the bank investigation.",
                "Recovered, evidence lost"),
        },
        "scene": _scene([
            _n("forum", "Leaked forum password", 8, 20, 10),
            _n("admin", "Shared admin login", 38, 30, 20),
            _n("script", "Edited payment script", 68, 20, 22),
            _n("members", "47 members", 74, 64, 12),
        ], ["admin", "script"], {
            "review_timeline": "admin", "inspect_script": "script", "check_access": "forum",
            "check_backups": "admin", "list_affected": "members",
        }),
    },
}
