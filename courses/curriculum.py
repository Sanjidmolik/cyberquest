"""
courses/curriculum.py
---------------------
Source of truth for the CyberQuest cyber defence curriculum.

`sync_curriculum()` (run by `manage.py sync_curriculum`, also in build.sh) makes
the database match this file. It is idempotent: running it again updates the
same records instead of creating duplicates.

* Existing courses are found by their stable `code` first (MOD-01 ...), then by
  a title keyword, so IDs, URLs and every CourseProgress/ReadingProgress row
  are kept.
* Phishing & Scam Prevention is PRESERVED: only its display title and shelf
  position are set. Its PDF/text, short description and progress are never
  touched, and no chapters are written for it.
* Cryptography, Steganography and OSINT are moved to the Coming Soon shelf
  (`is_coming_soon=True`). Their records and content are kept for later.

Cast used across the comics:
  Riya   - a first-year student who is new to cybersecurity.
  Tanvir - Riya's classmate. Means well, often clicks first.
  Shield - the CyberQuest mentor who explains each defence.
"""

# Speaker -> (panel colour, bubble side). Narration and activities have their own look.
CAST = {
    "Riya": ("#FFE7A8", "left"),
    "Tanvir": ("#CDEBFF", "right"),
    "Shield": ("#E7D9FF", "right"),
    "Narrator": ("#FFF6DA", "left"),
}
OTHER_SPEAKER = ("#FFD9E3", "left")

N = "Narrator"
R = "Riya"
T = "Tanvir"
S = "Shield"


def activity(title, text):
    return (f"Defence activity: {title}", text)


# --------------------------------------------------------------------------
# Course 1: Cyber Security & Online Safety
# --------------------------------------------------------------------------
ONLINE_SAFETY = [
    {
        "title": "What Is Cybersecurity?",
        "panels": [
            (N, "Riya's first week at university. New laptop, new phone, new accounts for everything: email, the student portal, banking, social media."),
            (R, "Everyone keeps saying 'stay safe online'. But what does cybersecurity actually mean?"),
            (S, "Cybersecurity means protecting your devices, accounts and information from damage, theft or misuse. Think of it as locks, alarms and good habits for your digital life."),
            (S, "It protects three things. Confidentiality: only the right people see your data. Integrity: nobody secretly changes it. Availability: it is there when you need it."),
            (T, "I'm just a student. Why would anyone attack me?"),
            (S, "Most attacks are automated. They try millions of people at once and look for easy targets. Your account, your phone storage and your contacts are all valuable to them."),
            (R, "So good habits are what make me a hard target."),
            (S, "Exactly. In this book you will learn to prevent problems, notice warning signs and know what to do if something goes wrong."),
        ],
        "questions": [
            ("What does cybersecurity protect?",
             ["Only big company servers", "Your devices, accounts and information", "Only your Wi-Fi password", "Only computers, not phones"],
             1, "Cybersecurity covers every device, account and piece of information you use, including your phone."),
            ("Why might an ordinary student be targeted?",
             ["Attackers only choose famous people", "Students are never targeted", "Most attacks are automated and look for any easy target", "Because students use old laptops"],
             2, "Automated attacks try huge numbers of people. Anyone with weak defences can become a victim."),
        ],
    },
    {
        "title": "Common Threats and How They Hurt Us",
        "panels": [
            (N, "In the student lounge, Tanvir looks worried at his phone."),
            (T, "My cousin lost her Facebook account, and then 'she' started asking all her friends for money!"),
            (S, "That is account takeover. Someone stole her login and used her name to trick people. It is one of the most common threats."),
            (S, "Other common threats: phishing messages that trick you, malware that damages devices, scams that steal money, and data leaks that expose personal details."),
            (R, "What does that mean for a normal person?"),
            (S, "Lost money, lost photos and files, embarrassment, stress, and time spent fixing everything. Prevention is much cheaper than recovery."),
            (T, "So the attack on my cousin's account hurt her friends too."),
            (S, "Yes. Protecting yourself also protects the people who trust you."),
        ],
        "questions": [
            ("A friend's account suddenly messages you asking for money. What is the most likely threat?",
             ["Account takeover", "A software update", "A slow internet connection", "A browser warning"],
             0, "Attackers who take over an account often message the victim's friends asking for money."),
            ("Which is a real effect of cyber threats on ordinary users?",
             ["Faster devices", "Lost money, files and time", "Free storage space", "Better passwords"],
             1, "Threats cause financial loss, data loss and stress. That is why prevention matters."),
        ],
    },
    {
        "title": "Safe Browsing and Secure Websites",
        "panels": [
            (R, "I need a cheap textbook. This site has it at 90% off. Looks great!"),
            (S, "Pause first. Check the address bar. Is the domain spelled correctly? Is it a site you or your library already trust?"),
            (S, "Look for https:// at the start. It means the connection is encrypted. But scam sites can use HTTPS too, so it shows privacy, not honesty."),
            (T, "So the padlock does not mean the site is safe?"),
            (S, "Right. It only means nobody in the middle can read the data. You still have to judge who you are talking to."),
            (S, "Red flags: prices that are too good to be true, misspelled domains like amaz0n-deals.shop, pop-ups that rush you, and pages asking for card details or passwords out of nowhere."),
            (R, "And if I'm not sure, I type the shop's address myself or search for it, instead of clicking a link."),
            activity("Safe or suspicious?", "Judge these fictional sites. (1) https://library.university.edu/books - your library's real address. (2) http://free-textbooks-download.xyz asking you to install a 'reader'. (3) https://paypa1-secure-login.com. Only (1) is safe. (2) has no HTTPS and pushes a download; (3) misspells PayPal."),
        ],
        "questions": [
            ("What does HTTPS (the padlock) tell you?",
             ["The site is honest", "The site is run by the government", "The connection is encrypted", "The site has no viruses"],
             2, "HTTPS encrypts the connection. Scam sites can have it too, so you still check the domain and the request."),
            ("Which address is most suspicious?",
             ["https://www.bbc.com/news", "https://paypa1-secure-login.com", "https://portal.university.edu", "https://www.wikipedia.org"],
             1, "'paypa1' uses the number 1 instead of the letter l. Lookalike domains are a classic trick."),
        ],
    },
    {
        "title": "Your Personal Information and Digital Footprint",
        "panels": [
            (N, "Tanvir fills in an online quiz: 'Which superhero are you?'"),
            (T, "It wants my birthday, my first school, and my pet's name. Easy!"),
            (S, "Careful. Those are common security-question answers. A fun quiz can be a way to collect them."),
            (S, "Your digital footprint is everything about you online: posts, photos, comments, accounts, and what others share about you. It stays for a long time."),
            (R, "So I should share less?"),
            (S, "Share on purpose. Keep your ID number, home address, phone number, passwords and bank details private. Think before posting anything you could not take back."),
            (S, "Try searching your own name sometimes. You will see what strangers and future employers can see."),
            (T, "Okay. Quiz closed. My pet's name stays secret."),
        ],
        "questions": [
            ("Why can a 'fun' online quiz be risky?",
             ["It uses too much battery", "It may collect answers to security questions", "It is always a virus", "It deletes your photos"],
             1, "Questions about your first school or pet's name match common security questions attackers can use."),
            ("What is a digital footprint?",
             ["Your phone's screen size", "The record of what you and others share about you online", "Your Wi-Fi speed", "A type of malware"],
             1, "Your footprint includes your posts, photos, accounts and anything others share about you."),
        ],
    },
    {
        "title": "Browser Warnings, Alerts and Suspicious Activity",
        "panels": [
            (N, "Late at night, Riya's screen suddenly turns red."),
            (R, "'Deceptive site ahead'... should I just click 'continue anyway'?"),
            (S, "No. Your browser blocks sites it knows are dangerous. Go back to safety. Warnings exist to protect you."),
            (T, "I once got a pop-up saying 'Your PC has 5 viruses! Call this number now!'"),
            (S, "That is a fake alert, a scam. Real security software does not ask you to call a random number or pay with gift cards. Close the tab. Do not call."),
            (S, "Real alerts from your accounts also matter: 'new sign-in from another country' or 'password changed' when you did nothing. That means act now, through the official app or site."),
            (R, "So: browser warning, go back. Scary pop-up, close it. Real account alert, check it through the official app."),
            activity("Risky situations", "What would you do? (a) A pop-up says your phone is hacked: install 'CleanerPro' - close it, never install. (b) Email says 'new login from Brazil' - open the app yourself, change the password, sign out other sessions. (c) 'Your connection is not private' - go back."),
        ],
        "questions": [
            ("Your browser shows a red 'Deceptive site ahead' page. What should you do?",
             ["Click 'continue anyway'", "Go back to safety", "Turn off the browser's protection", "Enter your password to check"],
             1, "Browser warnings block known dangerous sites. Going back is the safe choice."),
            ("A pop-up says 'Virus found! Call this number now!'. What is it most likely to be?",
             ["A real alert from your antivirus", "A Windows update", "A tech support scam", "A message from your university"],
             2, "Real security tools do not ask you to call random numbers. Close the tab and don't call."),
        ],
    },
    {
        "title": "Your Daily Cybersecurity Checklist",
        "panels": [
            (R, "There is so much to remember. Can we make it simple?"),
            (S, "Let's build a daily checklist. Small habits, done every day, stop most attacks."),
            (S, "1. Lock your phone and laptop when you step away. 2. Install updates when they appear. 3. Think before you click links or open attachments."),
            (S, "4. Use a unique password for important accounts, with MFA turned on. 5. Check the address bar before you type a password. 6. Back up your important files."),
            (T, "And 7: if something feels wrong, stop and ask someone before acting."),
            (S, "Perfect. Rushing is what attackers want. Taking a moment is your strongest defence."),
            activity("Build your checklist", "Write your own 5-point checklist for this week. Example: lock screen ON, updates installed, MFA on email, backup of assignments done, one suspicious message reported. Tick each item every evening."),
            (R, "Checklist saved. Next stop: phishing!"),
        ],
        "questions": [
            ("Which habit belongs on a daily safety checklist?",
             ["Turning off updates", "Locking your devices when you step away", "Using one password everywhere", "Clicking links quickly to save time"],
             1, "Locking your screen stops anyone nearby from using your device or accounts."),
            ("What is the best response when a message feels urgent and strange?",
             ["Act immediately", "Forward it to all friends", "Stop and check before acting", "Reply with your details"],
             2, "Attackers create urgency. Pausing to check is one of the strongest defences."),
            ("Which statement about safe browsing is TRUE?",
             ["The padlock proves a site is honest", "Typing a trusted address yourself is safer than clicking an unknown link", "Pop-up virus alerts are always real", "Browser warnings can be ignored"],
             1, "Typing a known address avoids lookalike links. The padlock shows encryption, not honesty."),
        ],
    },
]

# --------------------------------------------------------------------------
# Course 3: Password & Account Protection
# --------------------------------------------------------------------------
PASSWORDS = [
    {
        "title": "How Passwords and Sign-In Work",
        "panels": [
            (N, "Tanvir tries to log in to the student portal for the fifth time."),
            (T, "Why do websites even need passwords?"),
            (S, "Signing in has two steps. First you say who you are (your username). Then you prove it. That proof is called authentication."),
            (S, "You can prove it with something you know (a password), something you have (your phone or a security key), or something you are (a fingerprint or your face)."),
            (R, "Does the website keep my password in a list?"),
            (S, "A well-built site stores a scrambled version called a hash, not your real password. But if a site is breached, weak passwords can still be guessed from those hashes."),
            (S, "That is why strong passwords and a second proof matter so much."),
        ],
        "questions": [
            ("What is authentication?",
             ["Choosing a username", "Proving you are who you say you are", "Deleting an account", "Updating an app"],
             1, "Authentication is the proof step, like entering a password or approving a login on your phone."),
            ("Which is an example of 'something you have'?",
             ["Your password", "Your fingerprint", "Your phone with an authenticator app", "Your birthday"],
             2, "A phone or security key is something you physically have."),
        ],
    },
    {
        "title": "Strong, Unique Passwords and Passphrases",
        "panels": [
            (T, "My password is Tanvir2005. Nobody will guess that!"),
            (S, "Attackers' tools try names, birth years and common words first. A name plus a year can be cracked in seconds."),
            (S, "Length matters most. A passphrase is several random words joined together, like 'mango-river-lantern-cloud'. It is long, easy to remember and hard to guess."),
            (R, "And I should use a different one for every account?"),
            (S, "Yes. Unique passwords mean one leaked site can't unlock all your other accounts."),
            activity("Rate fictional passwords", "These are made-up examples. Never type your real password into any checker. Rate each: 'password123' - very weak. 'Riya@2006' - weak (name plus year). 'Tr0ub4dor' - weak (short, predictable swaps). 'violet-tiger-paper-moon-42' - strong (long and random)."),
            (T, "Okay, I'm changing Tanvir2005 today."),
        ],
        "questions": [
            ("What makes a password strongest?",
             ["Using your name and birth year", "Length and randomness, like a passphrase of random words", "Replacing 'a' with '@'", "Using the same one everywhere"],
             1, "Long, random passphrases are much harder to guess than short passwords with simple swaps."),
            ("Why should every important account have a unique password?",
             ["So you forget them faster", "So one leaked password can't unlock your other accounts", "Websites require it by law", "It makes login faster"],
             1, "Unique passwords contain the damage when one site is breached."),
        ],
    },
    {
        "title": "Using a Password Manager Safely",
        "panels": [
            (R, "Unique passphrases for 30 accounts? I can't remember all of those!"),
            (S, "That is what a password manager is for. It is an encrypted vault that remembers and fills in your passwords."),
            (S, "You remember one strong master password. The manager can create long random passwords for every site."),
            (S, "It also helps against fake sites. It won't autofill your bank password on a lookalike domain."),
            (T, "What if someone gets my master password?"),
            (S, "Make it a long passphrase you use nowhere else, turn on MFA for the manager, and keep the recovery kit somewhere safe offline. Use a well-known manager from an official app store."),
            (S, "Avoid saving passwords in notes apps, screenshots or sticky notes."),
        ],
        "questions": [
            ("What is the main job of a password manager?",
             ["To share passwords with friends", "To store and fill in strong, unique passwords securely", "To speed up Wi-Fi", "To remove viruses"],
             1, "A password manager keeps an encrypted vault, so every account can have a strong unique password."),
            ("How can a password manager help against phishing?",
             ["It deletes phishing emails", "It won't autofill your password on a lookalike domain", "It blocks all ads", "It changes your email address"],
             1, "Autofill matches the real domain. When it doesn't fill, that is a warning sign."),
        ],
    },
    {
        "title": "Multi-Factor Authentication (MFA)",
        "panels": [
            (N, "Shield shows two locks on a door."),
            (S, "MFA means a second proof after your password, such as a code from an authenticator app, a prompt on your phone, or a security key."),
            (S, "Even if a criminal steals your password, they still can't sign in without your second factor."),
            (R, "Which kind is best?"),
            (S, "Authenticator apps and security keys are stronger than SMS codes, because a SIM can be swapped. But any MFA is much better than none."),
            (S, "One golden rule: never share an MFA code. And never approve a login prompt you did not start yourself."),
            activity("Turn on MFA (simulated)", "Practise the steps in a pretend account: Settings > Security > Two-step verification > choose 'Authenticator app' > scan the QR code with the app > type the 6-digit code to confirm > save your backup codes offline. Done!"),
        ],
        "questions": [
            ("A criminal has your password but you use MFA. What happens?",
             ["They get in immediately", "They still need your second factor to sign in", "Your account is deleted", "MFA turns off"],
             1, "MFA adds a second proof that the attacker doesn't have."),
            ("You get an MFA approval request you didn't start. What do you do?",
             ["Approve it to make it stop", "Deny it and change your password", "Ignore it forever", "Send the code to a friend"],
             1, "An unexpected prompt means someone may know your password. Deny it, then change the password."),
        ],
    },
    {
        "title": "Password Reuse, Credential Theft and Account Takeover",
        "panels": [
            (T, "A gaming site I used was hacked. But it's just a game account, who cares?"),
            (S, "If you used the same password on your email, attackers will try it there too. This is called credential stuffing. Leaked logins are tested on many sites automatically."),
            (S, "Credentials are also stolen through fake login pages, malware that records keystrokes, and people reading passwords over your shoulder."),
            (R, "What does account takeover look like?"),
            (S, "Password-changed emails you didn't expect, friends getting strange messages from you, new devices in your login history, or recovery details changed."),
            (S, "If a site you use is breached, change that password, plus any account where you reused it. You can check breach notification services."),
        ],
        "questions": [
            ("What is credential stuffing?",
             ["Making passwords longer", "Trying leaked usernames and passwords on many other sites", "Storing passwords in a manager", "Turning on MFA"],
             1, "Attackers reuse leaked logins on other sites. That's why reuse is dangerous."),
            ("Which is a sign of account takeover?",
             ["You receive a newsletter", "A 'password changed' email you didn't request", "Your app updates", "Your battery drains"],
             1, "Unexpected security changes are a strong warning sign."),
        ],
    },
    {
        "title": "Recovery Email, Backup Codes and Active Sessions",
        "panels": [
            (S, "Your recovery email and phone number are the master keys to your accounts. Whoever controls them can reset your password."),
            (R, "So my recovery email needs a strong password and MFA too."),
            (S, "Yes. And keep them up to date. An old phone number you no longer have is a risk."),
            (S, "Backup codes are one-time codes for when you lose your phone. Print them or store them in your password manager. Never in a photo in your gallery."),
            (T, "And what are 'active sessions'?"),
            (S, "A list of devices currently signed in to your account. Check it now and then. If you see a device or place you don't recognise, sign it out and change your password."),
        ],
        "questions": [
            ("Why is your recovery email so important?",
             ["It sends newsletters", "Whoever controls it can reset your other passwords", "It makes your account faster", "It stores your photos"],
             1, "Password resets go to your recovery email or phone, so protect it like a master key."),
            ("Where should backup codes be kept?",
             ["In a photo on your phone", "Posted in a group chat", "Printed or in your password manager", "In your email signature"],
             2, "Keep backup codes offline or in a secure vault, separate from the device they protect."),
        ],
    },
    {
        "title": "When an Account Is Compromised",
        "panels": [
            (N, "Riya's friends say 'she' is sending them strange links on Messenger."),
            (R, "Oh no. What do I do first?"),
            (S, "Stay calm and move in order. 1. If you can still log in, change the password from a device you trust. 2. Sign out of all other sessions."),
            (S, "3. Turn on or reset MFA. 4. Check your recovery email and phone. Remove anything you don't recognise. 5. Review connected apps."),
            (S, "6. Tell your friends not to click the links. 7. If you can't log in, use the platform's official recovery page, never a 'recovery helper' who messages you."),
            activity("Recovery scenario", "Put the steps in order for a fictional hacked account: (A) warn your contacts, (B) change the password on a trusted device, (C) sign out all sessions, (D) check recovery details and MFA. Correct order: B, C, D, A."),
            (R, "Account secured. And this time MFA stays on!"),
        ],
        "questions": [
            ("What should you do FIRST if you can still log in to a hacked account?",
             ["Delete all your posts", "Change the password from a trusted device", "Message the attacker", "Wait a week"],
             1, "Changing the password from a clean, trusted device cuts off the attacker's access."),
            ("Someone messages offering to 'recover your hacked account' for a fee. What is this?",
             ["Official support", "A likely recovery scam", "Your bank", "A required step"],
             1, "Use only the platform's official recovery pages. Unsolicited 'helpers' are often scammers."),
            ("Which step stops an attacker who is still signed in?",
             ["Signing out of all other sessions", "Changing your profile picture", "Posting a status", "Clearing your browser history"],
             0, "Signing out other sessions ends any session the attacker still has open."),
        ],
    },
]

# --------------------------------------------------------------------------
# Course 4: Malware & Ransomware Protection
# --------------------------------------------------------------------------
MALWARE = [
    {
        "title": "Meet the Malware Family",
        "panels": [
            (S, "Malware means malicious software: programs made to harm, spy on, or take over your device."),
            (S, "A virus attaches to files and spreads when they are shared. A worm spreads by itself across networks. A Trojan pretends to be useful software."),
            (S, "Spyware secretly watches what you do. Adware floods you with ads. Ransomware locks or encrypts your files and demands payment."),
            (T, "That's a scary family."),
            (S, "The good news: the same defences stop most of them. Safe downloads, updates, security software and backups."),
        ],
        "questions": [
            ("Which malware pretends to be useful software?",
             ["Worm", "Trojan", "Adware", "Firewall"],
             1, "A Trojan disguises itself as something helpful, like a free tool or game crack."),
            ("What does ransomware do?",
             ["Shows extra ads", "Speeds up your PC", "Locks or encrypts files and demands payment", "Updates your apps"],
             2, "Ransomware holds your files hostage. Backups are the best protection."),
        ],
    },
    {
        "title": "How Infections Get In",
        "panels": [
            (N, "Tanvir wants a paid photo editor... for free."),
            (T, "This site has a 'cracked' version. Just one download!"),
            (S, "Cracked software is one of the most common ways in. The 'free' copy often carries a Trojan."),
            (S, "Other routes: email attachments you weren't expecting, fake 'update your player' pop-ups, infected USB drives, and links in messages."),
            (R, "Even files from friends?"),
            (S, "Even those. Their account or device might be infected. If a file is unexpected, check with them another way before opening it."),
            (S, "Watch out for double extensions like 'notes.pdf.exe' and Office files that ask you to 'enable macros'."),
        ],
        "questions": [
            ("Which is a common malware infection route?",
             ["Installing updates from the official settings", "Downloading cracked software", "Locking your screen", "Using a password manager"],
             1, "Pirated or cracked software often comes with hidden malware."),
            ("A friend unexpectedly sends 'invoice.pdf.exe'. What should you do?",
             ["Open it quickly", "Check with the friend another way and don't open it", "Forward it to others", "Rename it to .pdf"],
             1, "A double extension that ends in .exe is a program, not a document. Verify before you open anything."),
        ],
    },
    {
        "title": "Safe Software Installation",
        "panels": [
            (S, "Install apps only from official sources: the Microsoft Store, Apple App Store, Google Play, or the developer's real website."),
            (S, "Before you install, check the developer name, reviews and download count. Read what permissions it asks for."),
            (R, "What about free alternatives?"),
            (S, "Many good free and open-source apps exist. Get them from their official sites, not from random mirrors or download sites full of ads."),
            (S, "During setup, choose 'Custom' install and untick extra toolbars or 'offers' you didn't ask for."),
            activity("Risky downloads", "Which is risky? (1) VLC from videolan.org - safe. (2) 'Photoshop_FULL_crack.zip' from a forum - risky. (3) A 'Flash Player update' pop-up on a movie site - risky (fake update). (4) Zoom from the Microsoft Store - safe."),
        ],
        "questions": [
            ("Where is the safest place to download an app?",
             ["A pop-up on a streaming site", "An official app store or the developer's real website", "A forum link", "A file in a group chat"],
             1, "Official stores and developer sites check and sign their software."),
            ("A movie site says 'Update your video player to continue'. What is it most likely to be?",
             ["A real system update", "A fake update that may install malware", "A free movie", "A browser warning"],
             1, "Real updates come from your system settings or the app itself, not pop-ups on random sites."),
        ],
    },
    {
        "title": "Antivirus, Real-Time Protection and Quarantine",
        "panels": [
            (N, "A notification appears on Riya's laptop."),
            (R, "'Threat quarantined: Trojan:Win32/Fakeinst'. Did I get hacked?"),
            (S, "Your antivirus did its job. Real-time protection scans files as they arrive. Quarantine moves a suspicious file to a locked area so it can't run."),
            (S, "Read the alert. Note the file name and where it came from. Then let the antivirus remove it. Don't restore it unless you are sure it's safe."),
            (S, "Keep your built-in protection on, such as Microsoft Defender on Windows. Keep it updated and run a full scan if you are worried."),
            (T, "And fake antivirus pop-ups in the browser?"),
            (S, "Those are scams. Real alerts come from the security app on your device, not from a website."),
            activity("Read the alert", "Fictional alert: 'Microsoft Defender: Threat found - Trojan in Downloads\\free_game_setup.exe - Action: Quarantined.' What does it mean? A downloaded installer was malicious and has been blocked. Next: remove it, then think about where it came from."),
        ],
        "questions": [
            ("What does 'quarantine' mean in an antivirus alert?",
             ["The file was sent to your friends", "The suspicious file was isolated so it can't run", "Your PC is broken", "The file was made faster"],
             1, "Quarantine locks the file away so it can't harm your device."),
            ("Where do REAL antivirus alerts come from?",
             ["A website pop-up", "A text message from a stranger", "The security app installed on your device", "A phone call"],
             2, "Websites can't scan your device. Alerts inside a browser page are usually scams."),
        ],
    },
    {
        "title": "Signs of a Possible Infection",
        "panels": [
            (T, "My laptop is acting weird. Slow, and there are new toolbars in my browser."),
            (S, "Possible signs of malware: unusual slowness or overheating, pop-ups everywhere, a changed browser homepage, apps you didn't install, security tools that turn off, or friends getting messages you didn't send."),
            (S, "Not every slow device is infected. But several signs together mean you should check."),
            (R, "What should he do?"),
            (S, "Disconnect from the internet, run a full antivirus scan, remove unknown apps and browser extensions, then change important passwords from a different, clean device."),
        ],
        "questions": [
            ("Which could be a sign of malware?",
             ["Your antivirus switches itself off", "Your phone's clock is correct", "An app updates from the store", "Your battery charges normally"],
             0, "Malware often tries to disable security tools. That's a serious sign."),
            ("After you suspect an infection, where should you change passwords?",
             ["On the infected device", "On a different, clean device", "In a public chat", "Nowhere"],
             1, "Malware might record what you type, so use a clean device to change passwords."),
        ],
    },
    {
        "title": "Stopping Ransomware Damage",
        "panels": [
            (N, "A classmate's laptop screen: 'Your files are encrypted. Pay to unlock.'"),
            (R, "Her whole thesis... gone?"),
            (S, "With ransomware, backups are what save you. If you have a clean, recent backup that was not connected, you can restore your files without paying."),
            (S, "Keep at least one backup offline or in versioned cloud storage, so ransomware can't encrypt it too."),
            (S, "Limit damage with restricted permissions. Use a normal user account every day, not an administrator account. Then malware can reach less."),
            (S, "Paying is no guarantee you get files back, and it funds criminals. Report it and get help instead."),
            activity("Ransomware checklist", "Build yours: (1) weekly backup to an external drive that you unplug after. (2) Cloud sync with version history on. (3) Daily use of a standard, non-admin account. (4) Updates on. (5) Know who to call: IT support or a trusted adult."),
        ],
        "questions": [
            ("What is the best protection against losing files to ransomware?",
             ["Paying quickly", "A recent backup that isn't always connected", "Turning off the screen", "Deleting the antivirus"],
             1, "A disconnected or versioned backup lets you restore without paying."),
            ("Why use a standard (non-admin) account every day?",
             ["It is faster", "Malware running in it can reach and change less", "It hides your files", "It's required for Wi-Fi"],
             1, "Restricted permissions limit what malware can damage."),
        ],
    },
    {
        "title": "Responding and Recovering Safely",
        "panels": [
            (S, "If you suspect malware, follow this plan. 1. Disconnect from Wi-Fi and unplug USB drives. 2. Don't pay, don't panic."),
            (S, "3. Tell IT support or a trusted adult. 4. Run a full scan with up-to-date security software. 5. If it's ransomware, take photos of the ransom screen as evidence."),
            (S, "6. If needed, reset the device, then restore files from a clean backup. 7. Change passwords from a clean device and turn on MFA."),
            (T, "And then figure out how it got in, so it doesn't happen again."),
            (S, "Exactly. Every incident is a lesson. Fix the habit that let it in."),
        ],
        "questions": [
            ("What is a good FIRST step when you suspect malware?",
             ["Disconnect the device from the network", "Install more free tools from pop-ups", "Email the file to friends", "Pay the ransom"],
             0, "Disconnecting stops malware from spreading or sending your data out."),
            ("When should you restore files from a backup after an infection?",
             ["Before cleaning the device", "After the device is cleaned or reset", "Never", "While the malware is still running"],
             1, "Restore onto a clean device, or the malware could damage the restored files again."),
            ("Which is true about paying a ransom?",
             ["It always returns your files", "It does not guarantee recovery and funds criminals", "It is required by law", "It removes the malware"],
             1, "Payment is no guarantee. Backups and reporting are safer paths."),
        ],
    },
]

# --------------------------------------------------------------------------
# Course 5: Wi-Fi & Network Safety
# --------------------------------------------------------------------------
NETWORK = [
    {
        "title": "Network Basics: Routers, Wi-Fi, IP and DNS",
        "panels": [
            (R, "How does my phone actually reach a website?"),
            (S, "Your home router is the gateway. It connects your devices to each other by Wi-Fi or cable, and to the internet through your provider."),
            (S, "Every device gets an IP address, a number like 192.168.0.12 that works like a house address for data."),
            (S, "DNS is the internet's phone book. It turns names like university.edu into IP addresses."),
            (T, "So if someone controls my router or DNS, they could send me to the wrong place?"),
            (S, "That's right. That's why securing the router is so important."),
        ],
        "questions": [
            ("What does DNS do?",
             ["Encrypts your files", "Turns website names into IP addresses", "Charges your phone", "Blocks all ads"],
             1, "DNS works like a phone book, turning names into addresses."),
            ("What is a router's main job?",
             ["Store your photos", "Connect your devices to each other and to the internet", "Scan for viruses", "Print documents"],
             1, "The router is the gateway between your home devices and the internet."),
        ],
    },
    {
        "title": "Securing Your Home Wi-Fi",
        "panels": [
            (N, "Tanvir's flat. The Wi-Fi is named 'TP-Link_4F2A' and has no password."),
            (T, "No password is easier for guests!"),
            (S, "And for strangers. They could use your internet for crime, or see your devices. Let's fix it."),
            (S, "In the router settings, choose WPA3 security. If a device doesn't support it, use WPA2 with AES. Avoid WEP, WPA/TKIP and 'open' networks."),
            (S, "Set a long Wi-Fi passphrase, at least 12 characters. And rename the network so it doesn't reveal the router model or your flat number."),
            (S, "Turn off WPS, the quick-connect button feature. It can be abused. Use a separate guest network for visitors."),
        ],
        "questions": [
            ("Which Wi-Fi security setting is best?",
             ["Open (no password)", "WEP", "WPA3 (or WPA2-AES if WPA3 isn't supported)", "WPA-TKIP"],
             2, "WPA3 is current. WPA2-AES is the fallback. WEP and TKIP are outdated."),
            ("Why give visitors a guest network?",
             ["It is faster", "It keeps their devices separate from yours", "It turns off encryption", "It's required by law"],
             1, "A guest network isolates visitors' devices from your personal devices."),
        ],
    },
    {
        "title": "Router Admin, Firmware and Connected Devices",
        "panels": [
            (S, "The router has its own admin login, separate from the Wi-Fi password. Many come with 'admin/admin'. Change it to a unique strong password."),
            (S, "Firmware is the router's software. Install updates, or turn on automatic updates. Old firmware can have known holes."),
            (S, "Turn off remote management from the internet unless you really need it."),
            (R, "And I should look at who's connected?"),
            (S, "Yes. The admin page lists connected devices. Learn what yours are called, and remove anything you don't recognise."),
            activity("Secure a router (simulated)", "Fictional router checklist: change admin password from 'admin' - done. Security: WPA3 - done. WPS: off - done. Firmware: update 2.1.4 to 2.3.0 - install. Remote management: off - done. Guest network: on - done."),
            activity("Review the device list", "Fictional list: 'Riya-iPhone', 'Riya-Laptop', 'LivingRoom-TV', 'android-7f3c2a' (unknown). Does the unknown one belong to a family member? If nobody knows it, block it and change the Wi-Fi passphrase."),
        ],
        "questions": [
            ("A router still uses the admin password 'admin'. What should you do?",
             ["Leave it, it's fine", "Change it to a strong unique password", "Share it with neighbours", "Write it on the router"],
             1, "Default admin passwords are publicly known. Change them first."),
            ("You find an unknown device on your Wi-Fi that nobody recognises. What's the best action?",
             ["Ignore it", "Block it and change the Wi-Fi passphrase", "Rename it", "Turn off your own devices"],
             1, "Remove unknown devices and change the passphrase so they can't rejoin."),
        ],
    },
    {
        "title": "Using Public Wi-Fi Safely",
        "panels": [
            (N, "At a café, Riya sees two networks: 'Cafe_Guest' and 'Free_Cafe_WiFi_Fast'."),
            (R, "Which one is real?"),
            (S, "Ask the staff for the exact network name. Attackers sometimes create lookalike 'evil twin' hotspots."),
            (S, "On public Wi-Fi, stick to HTTPS sites and apps. Avoid banking or entering passwords on sites you don't trust. Your phone's mobile data is safer for sensitive tasks."),
            (S, "Turn off auto-join and file sharing. Choose 'Public network' when your laptop asks. Forget the network when you leave."),
            activity("Public Wi-Fi choices", "Choose safely: (a) Pay a bill on airport Wi-Fi - better to use mobile data. (b) Read the news on café Wi-Fi - fine. (c) A hotspot page asks for your email password to 'log in' - never; leave it."),
        ],
        "questions": [
            ("Two similar Wi-Fi names appear at a café. What should you do?",
             ["Join the fastest-sounding one", "Ask staff for the exact network name", "Join both", "Turn off the firewall"],
             1, "An attacker can set up a lookalike 'evil twin' hotspot. Confirm the real name."),
            ("What is safer for online banking when you're out?",
             ["Any open Wi-Fi", "Your phone's mobile data", "A stranger's hotspot", "A shared library computer"],
             1, "Mobile data avoids shared public networks you can't control."),
        ],
    },
    {
        "title": "HTTPS and Certificate Warnings",
        "panels": [
            (S, "HTTPS encrypts what travels between you and the website. A certificate proves the website really owns that address."),
            (S, "If your browser says 'Your connection is not private', the certificate couldn't be trusted. The site may be fake, or someone may be intercepting the connection."),
            (T, "Can I just click 'Advanced' and continue?"),
            (S, "Not on public Wi-Fi, and never for logins or payments. Go back. Try again later on a trusted network, or contact the site another way."),
            (S, "Sometimes a wrong date on your device causes certificate errors. Check that your clock is right."),
        ],
        "questions": [
            ("What does a certificate warning mean?",
             ["The site loads faster", "The browser can't confirm the site's identity", "The site has a sale", "Your Wi-Fi is off"],
             1, "The browser couldn't verify the site's identity, so the connection may be unsafe."),
            ("You see 'Your connection is not private' on a login page on café Wi-Fi. What should you do?",
             ["Continue and log in", "Go back and don't enter your details", "Disable HTTPS", "Clear your history"],
             1, "Don't enter details. The connection could be intercepted."),
        ],
    },
    {
        "title": "Firewalls: Your Digital Gatekeeper",
        "panels": [
            (R, "What is a firewall? A wall of fire?"),
            (S, "It's a gatekeeper. A firewall checks network traffic and blocks connections that aren't allowed, especially unwanted ones coming in."),
            (S, "Your router has one, and so does your laptop: Windows Defender Firewall, or the macOS firewall. Keep them turned on."),
            (S, "When an app asks to 'allow access through the firewall', only allow it if you know the app and you trust it. On public networks, be extra careful."),
        ],
        "questions": [
            ("What does a firewall do?",
             ["Cools down your laptop", "Blocks network connections that aren't allowed", "Stores your passwords", "Makes Wi-Fi faster"],
             1, "A firewall filters traffic and blocks unwanted connections."),
            ("An unknown app asks to be allowed through your firewall on public Wi-Fi. What should you do?",
             ["Allow it", "Deny it unless you know and trust the app", "Turn off the firewall", "Restart the router"],
             1, "Only allow apps you recognise and trust."),
        ],
    },
    {
        "title": "Spotting Suspicious Network Changes",
        "panels": [
            (N, "Tanvir's internet suddenly feels slow, and his bank site looks a little 'off'."),
            (S, "Warning signs: unknown devices on the network, router settings or the Wi-Fi password changed without you, DNS settings changed, unexpected login pages, or lots of certificate warnings."),
            (T, "What do I do?"),
            (S, "Log in to the router admin page. Check the device list and DNS settings. Change the admin and Wi-Fi passwords, update the firmware, and if things still look wrong, factory reset and set it up securely again."),
            (S, "If you rent or share the network, tell the owner or your ISP."),
        ],
        "questions": [
            ("Which is a suspicious network change?",
             ["Your router's DNS settings changed and you didn't do it", "Your phone's wallpaper changed", "An app updated", "Your Wi-Fi name is the same as yesterday"],
             0, "Unexpected DNS changes can redirect you to fake websites."),
            ("If router settings look tampered with and changing passwords doesn't fix it, what is a strong next step?",
             ["Ignore it", "Factory reset the router and set it up securely again", "Share the Wi-Fi password publicly", "Turn off HTTPS"],
             1, "A reset removes changes the attacker made. Then secure it properly."),
        ],
    },
]

# --------------------------------------------------------------------------
# Course 6: Device & Personal Data Protection
# --------------------------------------------------------------------------
DEVICE = [
    {
        "title": "Screen Locks, Encryption and Physical Security",
        "panels": [
            (N, "Library. Riya leaves her laptop open while she gets coffee."),
            (S, "In two minutes, someone could read her email or copy files. Lock the screen every time you step away: Windows+L, or Control+Command+Q on a Mac."),
            (S, "Use a PIN of at least 6 digits, or a passphrase, plus a fingerprint or face unlock. Set auto-lock to a minute or two."),
            (S, "Turn on device encryption: BitLocker or Device Encryption on Windows, FileVault on Mac. Modern phones encrypt when a lock is set. A stolen device's data then stays unreadable."),
            (R, "And I shouldn't leave it alone in public at all."),
            (S, "Right. Keep devices with you, and use a privacy screen in busy places if you can."),
        ],
        "questions": [
            ("What does device encryption protect against?",
             ["Slow Wi-Fi", "Someone reading your data if the device is stolen", "Spam email", "Low battery"],
             1, "Encryption keeps data unreadable without your unlock code."),
            ("What's the quickest habit to protect a laptop in a library?",
             ["Turning up the brightness", "Locking the screen whenever you step away", "Closing all tabs", "Unplugging the charger"],
             1, "A locked screen stops anyone from using your session."),
        ],
    },
    {
        "title": "Security Updates",
        "panels": [
            (T, "I always click 'remind me later' on updates."),
            (S, "Updates fix security holes that criminals already know about. Delaying them leaves the door open."),
            (S, "Turn on automatic updates for your operating system, browser and apps. Restart when asked. Replace devices that no longer get security updates."),
            (R, "Even phone apps?"),
            (S, "Yes. Update apps from the official store, and delete apps you no longer use."),
        ],
        "questions": [
            ("Why are security updates important?",
             ["They change your wallpaper", "They fix security holes that attackers know about", "They delete your files", "They slow down your device"],
             1, "Updates close known holes before criminals can use them."),
            ("A laptop no longer receives security updates. What is the best long-term action?",
             ["Keep using it for banking", "Plan to replace or upgrade it", "Turn off the antivirus", "Never connect it to power"],
             1, "Unsupported systems stay vulnerable forever."),
        ],
    },
    {
        "title": "Reviewing App Permissions",
        "panels": [
            (N, "Tanvir installs a flashlight app."),
            (T, "It wants my contacts, location, microphone and SMS. For a flashlight?"),
            (S, "That's a red flag. Permissions should match what the app does. A flashlight needs none of those."),
            (S, "Go to Settings > Privacy (or Apps > Permissions). Review location, camera, microphone, contacts and photos. Use 'Only while using the app' and 'Ask every time'."),
            activity("Permission review", "Fictional apps: (1) Maps wants location 'while using' - OK. (2) A calculator wants contacts - deny. (3) A photo editor wants all photos - choose 'selected photos'. (4) A game wants microphone access - deny unless you use voice chat."),
        ],
        "questions": [
            ("A flashlight app asks for your contacts. What should you do?",
             ["Allow it", "Deny it, because it doesn't match what the app does", "Share your contacts manually", "Turn off your phone"],
             1, "Permissions should match an app's purpose. A flashlight doesn't need contacts."),
            ("Which location setting gives an app the least access?",
             ["Always", "Only while using the app (or ask every time)", "Shared with friends", "Precise and always"],
             1, "Limit access to when you are actually using the app."),
        ],
    },
    {
        "title": "Protecting Sensitive Personal Files",
        "panels": [
            (R, "I have scans of my ID card, my transcript and my passport on my desktop."),
            (S, "Those are sensitive files. Criminals use them for identity theft."),
            (S, "Keep them in one protected folder, on an encrypted device or encrypted cloud storage. Don't email them to yourself or keep them in chat apps."),
            (S, "Delete copies you no longer need, including in Downloads and the recycle bin. When you share an ID, add a watermark like 'For university application only'."),
        ],
        "questions": [
            ("Where is the safest place to keep a scan of your ID?",
             ["Your desktop and a group chat", "An encrypted device or encrypted cloud folder", "A public post", "An email to yourself"],
             1, "Keep sensitive files in protected storage, not scattered across apps."),
            ("Why add a watermark like 'For university application only' to a shared ID copy?",
             ["It looks nicer", "It makes the copy harder to misuse for other purposes", "It encrypts the file", "It is required by Wi-Fi"],
             1, "A watermark limits how the copy can be reused by someone else."),
        ],
    },
    {
        "title": "Cloud Storage and Sharing Permissions",
        "panels": [
            (T, "I shared our group project folder with 'anyone with the link'. Easy!"),
            (S, "Easy for anyone who finds the link too. Links get forwarded."),
            (S, "Share with specific people's emails, give 'viewer' rather than 'editor' when possible, and set an expiry date if your service allows it."),
            (S, "Review your shared files every few weeks and remove access that's no longer needed. And protect your cloud account with MFA."),
        ],
        "questions": [
            ("What is the safest way to share a project folder?",
             ["Anyone with the link can edit", "Share with specific people, with only the access they need", "Post the link publicly", "Share your account password"],
             1, "Share with named people and the least access they need."),
            ("Why review shared files regularly?",
             ["To make them load faster", "To remove access people no longer need", "To change file colours", "To delete your account"],
             1, "Old access can expose files long after a project ends."),
        ],
    },
    {
        "title": "Backups and the 3-2-1 Rule",
        "panels": [
            (N, "Midnight before a deadline. Tanvir spills tea on his laptop."),
            (T, "My final project!"),
            (S, "This is why we back up. Follow the 3-2-1 rule: 3 copies of your data, on 2 different types of storage, with 1 copy kept off-site or in the cloud."),
            (S, "For example: the original on your laptop, a copy on an external drive, and a copy in cloud storage with version history."),
            (S, "Automate it if you can, and test a restore sometimes. A backup you've never tried to restore is only a hope."),
            activity("Plan your academic backups", "Design a plan: (1) Assignments folder syncs to cloud storage with version history. (2) Every Sunday, copy it to an external drive, then unplug the drive. (3) Once a month, restore one file to test. Write down where each copy lives."),
        ],
        "questions": [
            ("What does the 3-2-1 backup rule mean?",
             ["3 passwords, 2 phones, 1 laptop", "3 copies, on 2 types of storage, 1 off-site", "Back up every 3 days, 2 hours, 1 minute", "3 apps, 2 accounts, 1 cloud"],
             1, "3 copies on 2 different media, with 1 kept off-site, protect against most disasters."),
            ("Why should you test restoring a backup?",
             ["To use up storage", "To make sure the backup actually works when you need it", "It deletes old files", "It's required for updates"],
             1, "Testing proves you can really recover your files."),
        ],
    },
    {
        "title": "Lost or Stolen Devices",
        "panels": [
            (N, "On the bus home, Riya realises her phone is gone."),
            (R, "My phone! Everything is on it!"),
            (S, "Act quickly. 1. From another device, use Find My (Apple) or Find My Device (Google) to locate, lock or show a message. Don't try to confront a thief yourself."),
            (S, "2. Change your important passwords, especially email, and sign out of the lost device. 3. Call your mobile provider to block the SIM. 4. Tell your bank if banking apps were on it."),
            (S, "5. If it can't be recovered, erase it remotely. 6. Report the theft to the police. Your backups mean you lose the phone, not your data."),
            activity("Device security audit", "Audit a device (simulated): screen lock with 6+ digit PIN - yes. Encryption - on. Auto-updates - on. Find My - on. Backup in the last week - yes. Unused apps - remove two. Score yourself out of 6."),
        ],
        "questions": [
            ("Your phone is stolen. What should you do with the tracking feature?",
             ["Go and confront the thief", "Use it to lock or erase the phone, and report it to the police", "Nothing", "Post the location publicly"],
             1, "Use remote lock or erase and report it. Don't put yourself in danger."),
            ("Which call helps stop someone using your phone number?",
             ["Calling your mobile provider to block the SIM", "Calling a friend", "Calling the café", "Calling the app store"],
             0, "Blocking the SIM stops calls and SMS codes going to the thief."),
            ("Which setting makes a stolen laptop's data unreadable?",
             ["Bright screen", "Device encryption", "Dark mode", "Large fonts"],
             1, "Encryption protects data even if the device is in someone else's hands."),
        ],
    },
]

# --------------------------------------------------------------------------
# Course 7: Social Media & Digital Privacy
# --------------------------------------------------------------------------
PRIVACY = [
    {
        "title": "Digital Footprints and Online Reputation",
        "panels": [
            (N, "Tanvir is applying for an internship. The recruiter searches his name."),
            (T, "Oh no. My old posts from school are all public..."),
            (S, "Your online reputation is how people see you based on your footprint. Recruiters, universities and scammers all look."),
            (S, "Review your old posts. Archive or delete what you wouldn't want an employer to see. Untag yourself from embarrassing photos."),
            (S, "Build a positive footprint too: projects, achievements, kind and thoughtful comments."),
        ],
        "questions": [
            ("Who might look at your online footprint?",
             ["Only your friends", "Recruiters, universities and possibly scammers", "Nobody", "Only your phone company"],
             1, "Many people can see public posts, including employers and criminals."),
            ("What is a good step to improve your online reputation?",
             ["Make every post public", "Review and remove old posts you wouldn't want an employer to see", "Share your password", "Add strangers"],
             1, "Cleaning up old content protects your reputation."),
        ],
    },
    {
        "title": "Privacy Settings and Audience Controls",
        "panels": [
            (S, "Every platform lets you choose who sees your posts: Public, Friends, Close friends, or Only me. Pick the audience every time you post."),
            (S, "Lock down your profile. Hide your phone number, email and birth year. Limit who can find you by phone number, and who can tag you."),
            (R, "Where do I find all that?"),
            (S, "Look for 'Privacy checkup' or 'Account privacy' in the settings. Many apps have a guided tour."),
            activity("Fix a profile (simulated)", "Fictional profile 'Riya.S': posts - Public, change to Friends. Phone number - visible, set to Only me. Birth year - visible, hide it. Tag review - off, turn it on. Find me by phone - Everyone, change to Friends."),
        ],
        "questions": [
            ("Which setting helps limit who sees your posts?",
             ["Audience controls like 'Friends' or 'Close friends'", "Dark mode", "Notifications sound", "Font size"],
             0, "Audience controls decide who can view each post."),
            ("Which detail is best kept as 'Only me'?",
             ["Your favourite movie", "Your phone number", "A public achievement", "Your university club"],
             1, "Phone numbers can be used for scams, SIM swaps and harassment."),
        ],
    },
    {
        "title": "Fake Profiles, Impersonation and Identity Theft",
        "panels": [
            (N, "Riya gets a friend request from 'Tanvir Ahmed'. But she is already friends with Tanvir."),
            (R, "Why would he make a new account?"),
            (S, "It may be an impersonator, someone who copied his name and photos to trick his friends. Ask Tanvir through the account or number you already trust."),
            (S, "Signs of a fake profile: very new account, few posts, copied photos, odd spelling, and quick requests for money, codes or private photos."),
            (S, "Identity theft goes further. Criminals use your personal details to open accounts or borrow money in your name. Guard your ID and documents."),
            activity("Spot the impersonator", "Fictional case: 'Tanvir.Ahmed.official2', created 3 days ago, 2 photos, messages: 'Lost my phone, send me the 6-digit code I'm texting you.' Verdict: impersonation. Don't send the code; report the profile; warn Tanvir."),
            (T, "That's not me! I'll report it, and ask friends to report it too."),
        ],
        "questions": [
            ("You get a request from a second account with your friend's name. What should you do first?",
             ["Accept it", "Check with your friend through a channel you already trust", "Send them money", "Share your code"],
             1, "Verify through the known account or number before trusting a duplicate."),
            ("Someone asks you to send them a 6-digit code that was texted to you. What is likely happening?",
             ["A friendly test", "An attempt to take over your account", "A prize giveaway", "A software update"],
             1, "Login and verification codes must never be shared. This is a takeover trick."),
        ],
    },
    {
        "title": "Location Privacy and Oversharing",
        "panels": [
            (T, "Posting a live story: 'Home alone all weekend! Here's my building!'"),
            (S, "That tells strangers where you live and that the home is empty. Post trips after you return, not during."),
            (S, "Turn off location tagging on posts and in your camera. Check map features like live location sharing, and share only with people you trust."),
            (S, "Watch the background of your photos too: house numbers, school badges, boarding passes, and screens with personal details."),
        ],
        "questions": [
            ("Why is posting 'Home alone this weekend' risky?",
             ["It uses too much data", "It shows strangers your home is empty", "It makes the app slower", "It isn't risky"],
             1, "Live updates about your location and empty home can help burglars or stalkers."),
            ("When is it safer to post holiday photos?",
             ["During the trip, with location on", "After you return home", "Never with friends", "Only with your passport visible"],
             1, "Posting after you return avoids revealing where you are right now."),
        ],
    },
    {
        "title": "Cyberbullying and Harassment",
        "panels": [
            (N, "Riya's classmate receives cruel anonymous messages every night."),
            (S, "Cyberbullying is repeated harmful behaviour online: insults, threats, sharing private images, or spreading lies. It is never the victim's fault."),
            (S, "Don't reply in anger. Take screenshots with the date and username, then block the account and report it using the platform's tools."),
            (S, "Tell someone you trust: a friend, family member, teacher or counsellor. If there are threats of violence or private images being shared, contact the police."),
            (R, "And if I see it happen to someone else, I can support them and report it too."),
        ],
        "questions": [
            ("What should you do before blocking a harasser?",
             ["Reply angrily", "Take screenshots as evidence", "Delete your account", "Share their messages publicly"],
             1, "Evidence helps platforms, schools and police act."),
            ("Which statement about cyberbullying is TRUE?",
             ["It is the victim's fault", "You should keep it secret", "Telling a trusted person and reporting it helps", "Blocking never helps"],
             2, "Support and reporting are key steps in stopping harassment."),
        ],
    },
    {
        "title": "Protecting Photos, Documents and Private Chats",
        "panels": [
            (S, "Once you send a photo, you lose control of it. It can be screenshotted or forwarded. Share private images only if you'd be okay with them spreading."),
            (S, "Use apps with end-to-end encryption for private chats. Turn on disappearing messages for sensitive talks, and lock the chat app."),
            (S, "Never send ID cards, passwords or bank details over chat. If someone pressures you for private photos, that is a serious warning sign. Stop, block and report."),
            (T, "And I shouldn't forward other people's private stuff either."),
            (S, "Exactly. Respect others' privacy like you want yours respected."),
        ],
        "questions": [
            ("What does end-to-end encryption in a chat app mean?",
             ["The app is free", "Only you and the other person can read the messages", "Messages are public", "Photos are bigger"],
             1, "End-to-end encryption keeps messages readable only by the people in the chat."),
            ("Someone is pressuring you to send private photos. What should you do?",
             ["Send them quickly", "Stop, block, report and tell someone you trust", "Negotiate", "Post about it"],
             1, "Pressure for private images is a serious red flag. Get support."),
        ],
    },
    {
        "title": "Recovering a Compromised Social Media Account",
        "panels": [
            (N, "Tanvir's Instagram now has a crypto-scam post, and his password doesn't work."),
            (T, "I'm locked out!"),
            (S, "Use the official recovery option on the login screen ('Forgot password' / 'Get help logging in'). Choose the recovery email or phone you control."),
            (S, "Once you're back in: change the password, turn on MFA, sign out all sessions, check recovery details, remove unknown connected apps and delete the scam posts."),
            (S, "Warn friends that the posts weren't you. Never pay 'account recovery' services that contact you."),
            activity("Incident response (fictional)", "Order the steps: (A) delete scam posts and warn followers, (B) official recovery, (C) turn on MFA and sign out all sessions, (D) check email and phone on the account. Correct: B, C, D, A."),
        ],
        "questions": [
            ("Where should you start recovering a hacked social account?",
             ["A stranger who DMs you offering help", "The platform's official recovery option", "A YouTube comment", "A paid hacker"],
             1, "Only the official recovery process is safe."),
            ("After you get back in, which step keeps the attacker out?",
             ["Signing out all sessions and turning on MFA", "Changing your profile picture", "Posting a selfie", "Following more people"],
             0, "Ending sessions and adding MFA stops the attacker returning."),
            ("Why warn your followers after a takeover?",
             ["So they buy the scam", "So they don't trust scam posts or messages sent from your account", "It's required by the app", "To get more likes"],
             1, "Warning contacts stops the scam from spreading further."),
        ],
    },
]

# --------------------------------------------------------------------------
# Course 8: Cyber Attack Response & Recovery
# --------------------------------------------------------------------------
RESPONSE = [
    {
        "title": "Recognising the Signs of an Incident",
        "panels": [
            (S, "A cyber incident is anything that threatens your accounts, devices or data, like a hacked account, malware, a data leak or a scam payment."),
            (S, "Signs: security alerts you didn't trigger, sent messages you didn't write, missing money, files that won't open, a device acting strangely, or friends saying they received odd links from you."),
            (R, "The earlier I notice, the less damage?"),
            (S, "Yes. Speed matters, but so does staying calm. Panic leads to mistakes."),
        ],
        "questions": [
            ("Which is a sign of a cyber incident?",
             ["A 'new sign-in' alert you didn't trigger", "A normal app update", "A friend's birthday reminder", "A full battery"],
             0, "Unexpected security alerts can mean someone else is using your account."),
            ("Why does noticing early matter?",
             ["It doesn't matter", "The sooner you act, the less damage", "It makes the device faster", "It deletes the attacker"],
             1, "Early action limits what an attacker can do."),
        ],
    },
    {
        "title": "Immediate Actions to Limit Damage",
        "panels": [
            (S, "The first minutes: contain it. Disconnect an infected device from the internet. Don't turn it off if IT support may need to check it. Just disconnect it."),
            (S, "Don't delete messages or files the attacker left. They're evidence. Don't pay or reply to the attacker."),
            (S, "Use a different, clean device to change passwords and contact the right people."),
            (T, "Contain, don't destroy evidence, use a clean device. Got it."),
        ],
        "questions": [
            ("What is the first goal right after an incident?",
             ["Delete everything", "Contain the damage", "Post about it online", "Buy a new phone"],
             1, "Containment, such as disconnecting, stops the problem from spreading."),
            ("Why use a different device to change passwords?",
             ["It's quicker", "The affected device might be recording what you type", "It's required by banks", "There is no reason"],
             1, "Malware on the affected device could capture new passwords."),
        ],
    },
    {
        "title": "Securing Compromised Accounts and Revoking Sessions",
        "panels": [
            (N, "Riya's email sent 200 spam messages overnight."),
            (S, "Email is the master key, because password resets go there. Secure it first."),
            (S, "From a clean device: change the password, sign out of all sessions, turn on MFA, check recovery email and phone, and look for filters or forwarding rules the attacker created."),
            (S, "Then check accounts linked to that email, starting with banking, cloud storage and social media."),
            activity("Compromised email (simulated)", "Fictional mailbox check: unknown session in 'Lagos, Chrome' - sign out. Forwarding rule to 'x8x@mail.ru' - delete. Recovery phone changed - restore yours. MFA - turn on. New password - unique passphrase. Contacts - warn them about the spam."),
        ],
        "questions": [
            ("Why secure your email account first?",
             ["It has the most photos", "Password resets for other accounts go there", "It's the oldest account", "It's the easiest"],
             1, "Control of your email can unlock your other accounts."),
            ("Why check for forwarding rules after an email compromise?",
             ["They make email faster", "Attackers set them up to keep secretly receiving your mail", "They are required", "They delete spam"],
             1, "A hidden forwarding rule can leak your mail even after the password is changed."),
        ],
    },
    {
        "title": "Unauthorised Financial Transactions",
        "panels": [
            (T, "My bank app shows a payment I didn't make!"),
            (S, "Call your bank right away using the number on your card or the official app, not a number from a message. Ask them to block the card and dispute the payment."),
            (S, "Change your banking and email passwords. Check other accounts, wallets and mobile money for strange activity."),
            (S, "Write down the date, amount and merchant. Banks often have deadlines for disputes, so act quickly."),
            (S, "Be careful of 'refund' callers afterwards. Scammers often target victims a second time."),
        ],
        "questions": [
            ("What number should you use to contact your bank?",
             ["The number in a text message", "The number on your card or in the official app", "A number from a social media comment", "A number a caller gives you"],
             1, "Use contact details you know are real to avoid a second scam."),
            ("A caller offers to 'refund' your stolen money if you share your PIN. What is this?",
             ["Bank procedure", "A follow-up scam", "Police support", "A normal refund"],
             1, "Banks never ask for your PIN. Victims are often targeted again."),
        ],
    },
    {
        "title": "Preserving Incident Evidence Safely",
        "panels": [
            (S, "Evidence helps banks, platforms and police help you. Take screenshots of messages, profiles, alerts and transactions, showing the date and time."),
            (S, "Write a simple timeline: what happened, when, and what you did. Save email headers or message links if you can."),
            (S, "Store copies somewhere safe that the attacker can't reach. Don't forward malware files to anyone, and don't 'hack back'."),
            (R, "So I collect facts, not revenge."),
            (S, "Exactly. Stay legal and safe."),
        ],
        "questions": [
            ("Which is good evidence to keep after a scam?",
             ["Screenshots with dates and a timeline of events", "Nothing - delete it all", "A copy of the malware sent to friends", "Your new password"],
             0, "Screenshots and a timeline help others investigate."),
            ("Is it okay to 'hack back' the attacker?",
             ["Yes, always", "No. It is illegal and unsafe; report it instead", "Only at night", "Only if they hacked you first"],
             1, "Attacking back is illegal and risky. Report through proper channels."),
        ],
    },
    {
        "title": "Reporting Cybercrime and Abuse",
        "panels": [
            (S, "Report to the right place. Hacked or fake accounts go to the platform's report tool. Money lost goes to your bank. University accounts go to your university IT or security team."),
            (S, "Threats, extortion, identity theft and fraud go to the police or your country's official cybercrime reporting service. Use official websites and phone numbers."),
            (S, "Phishing emails can be reported with your email app's 'Report phishing' button."),
            activity("Write an incident report", "Use fictional evidence. Report: 'On 12 March at 21:40, I received a fake bank SMS. I clicked and entered my card number. At 21:55, a 4,500 payment appeared. I called the bank at 22:05, and the card was blocked. Evidence attached: SMS screenshot, transaction screenshot.'"),
            (T, "Short, factual, with times and evidence. That's easy to follow."),
        ],
        "questions": [
            ("Where should you report a hacked university account?",
             ["Your university IT or security team", "A random forum", "A gaming chat", "Nobody"],
             0, "The organisation that runs the account can secure it and check for wider damage."),
            ("What makes a good incident report?",
             ["Emotions only", "Clear facts, times, actions taken and evidence", "Your passwords", "Only the attacker's name"],
             1, "Facts, a timeline and evidence help people act quickly."),
        ],
    },
    {
        "title": "Restoring From Verified Clean Backups",
        "panels": [
            (S, "After malware, restore carefully. First make sure the device is clean, by a full scan or a factory reset with a reinstall."),
            (S, "Use a backup from BEFORE the incident, and scan it before restoring. Restoring infected files brings the problem back."),
            (S, "Reinstall apps from official sources, not from old installers. Then update everything."),
            (R, "Clean device first, clean backup second, updates third."),
        ],
        "questions": [
            ("Which backup should you restore after a malware infection?",
             ["The newest one, even if made during the infection", "A verified clean backup from before the incident", "A friend's backup", "None"],
             1, "Backups made during an infection may contain the malware."),
            ("What should happen BEFORE restoring files?",
             ["Make sure the device is clean or reset", "Share the files", "Turn off updates", "Pay the attacker"],
             0, "Restoring onto an infected device can re-infect your files."),
        ],
    },
    {
        "title": "Reviewing and Improving Your Defences",
        "panels": [
            (N, "A week later, Riya and Tanvir review what happened."),
            (S, "After every incident, ask: how did it start? What helped? What would have stopped it earlier?"),
            (T, "Mine started with password reuse. Now I use a password manager and MFA."),
            (R, "Mine was clicking a fake link. Now I check the address and report phishing."),
            (S, "That's the cycle: prevent, detect, respond, recover, improve. You now have the full defence toolkit."),
            activity("Safe recovery scenario", "Fictional case: a laptop got ransomware from a cracked game. Plan: disconnect; photograph the ransom note; tell IT; don't pay; factory reset; restore clean backup from last Sunday; reinstall apps from official stores; turn on auto-updates; use a standard account; no more cracked software."),
        ],
        "questions": [
            ("What is the last step in the defence cycle after recovering?",
             ["Forget it happened", "Review and improve your defences", "Delete your accounts", "Blame someone"],
             1, "Reviewing the incident prevents it from happening again."),
            ("In the ransomware scenario, why reinstall apps from official stores?",
             ["They are prettier", "Old or cracked installers may bring the malware back", "It's faster", "It deletes backups"],
             1, "Official sources avoid reinstalling the thing that caused the infection."),
            ("Which order matches the full defence cycle?",
             ["Recover, prevent, ignore", "Prevent, detect, respond, recover, improve", "Detect, pay, delete", "Respond, post, forget"],
             1, "Prevent, detect, respond, recover and improve is the complete cycle."),
        ],
    },
]


# --------------------------------------------------------------------------
# Course catalogue: exact student-facing order
# --------------------------------------------------------------------------
# `code` is the stable identifier. `match` is a title keyword used only when no
# course with that code exists yet (for example, a database seeded differently).
# `chapters=None` means: never write chapters for this course (Phishing).
ACTIVE_COURSES = [
    {
        "code": "CQ-SAFETY", "match": "online safety", "order": 10,
        "title": "Cyber Security & Online Safety",
        "short_description": "Build safe online habits: secure browsing, warnings, your digital footprint and a daily checklist.",
        "summary": "Start here. Learn what cybersecurity protects, the threats ordinary users face, how to browse safely, read browser warnings and build a cyber safety checklist you can use every day.",
        "chapters": ONLINE_SAFETY,
    },
    {
        "code": "MOD-01", "match": "phish", "order": 20,
        "title": "Phishing & Scam Prevention",
        "preserve": True,
        "chapters": None,
    },
    {
        "code": "MOD-02", "match": "password", "order": 30,
        "title": "Password & Account Protection",
        "short_description": "Prevent unauthorised access with passphrases, password managers, MFA and safe recovery.",
        "summary": "Learn how sign-in works, create strong unique passphrases, use a password manager and MFA, protect recovery options and secure an account after a compromise.",
        "chapters": PASSWORDS,
    },
    {
        "code": "CQ-MALWARE", "match": "malware", "order": 40,
        "title": "Malware & Ransomware Protection",
        "short_description": "Protect devices and files from viruses, Trojans, spyware and ransomware.",
        "summary": "Meet the malware family, learn how infections get in, install software safely, read antivirus alerts, stop ransomware with backups and recover safely.",
        "chapters": MALWARE,
    },
    {
        "code": "MOD-03", "match": "network", "order": 50,
        "title": "Wi-Fi & Network Safety",
        "short_description": "Secure your home Wi-Fi and router, and stay safe on public networks.",
        "summary": "Understand routers, IP and DNS, lock down home Wi-Fi with WPA3 or WPA2-AES, keep the router updated, use public Wi-Fi safely, read certificate warnings and use firewalls.",
        "chapters": NETWORK,
    },
    {
        "code": "CQ-DEVICE", "match": "device", "order": 60,
        "title": "Device & Personal Data Protection",
        "short_description": "Lock, encrypt, update and back up your devices and personal files.",
        "summary": "Protect phones and laptops with screen locks, encryption and updates, review app permissions, secure files and cloud sharing, follow the 3-2-1 backup rule and handle a lost device.",
        "chapters": DEVICE,
    },
    {
        "code": "CQ-PRIVACY", "match": "privacy", "order": 70,
        "title": "Social Media & Digital Privacy",
        "short_description": "Protect your identity, privacy and reputation on social media.",
        "summary": "Manage your digital footprint and privacy settings, spot fake profiles and impersonation, avoid oversharing, handle harassment, and recover a hacked social account.",
        "chapters": PRIVACY,
    },
    {
        "code": "CQ-RESPONSE", "match": "response", "order": 80,
        "title": "Cyber Attack Response & Recovery",
        "short_description": "Respond to incidents, report cybercrime and recover safely.",
        "summary": "Recognise incidents, limit damage, secure accounts, handle unauthorised payments, preserve evidence, report through the right channels, restore clean backups and improve your defences.",
        "chapters": RESPONSE,
    },
]

# Kept for the future, shown as locked cards. Content is left as it is.
COMING_SOON_COURSES = [
    {"code": "MOD-04", "match": "crypt", "order": 900, "title": "Cryptography",
     "short_description": "Encryption, hashing and the maths of keeping secrets. Opening in a future update."},
    {"code": "MOD-05", "match": "steg", "order": 910, "title": "Steganography",
     "short_description": "How information is hidden in plain sight. Opening in a future update."},
    {"code": "MOD-06", "match": "osint", "order": 920, "title": "OSINT (Open-Source Intelligence)",
     "short_description": "Investigating with public information, responsibly. Opening in a future update."},
]


def _find_course(Course, spec):
    course = Course.objects.filter(code=spec["code"]).first()
    if course is None and spec.get("match"):
        course = (
            Course.objects.filter(title__icontains=spec["match"])
            .order_by("order", "id")
            .first()
        )
    return course


def _write_chapters(course, chapters, Chapter, ComicPanel, ChapterQuestion):
    """Update chapters in place by position so any ChapterProgress rows survive."""
    existing = list(course.chapters.order_by("order", "id"))
    for index, spec in enumerate(chapters):
        if index < len(existing):
            chapter = existing[index]
            chapter.title = spec["title"]
            chapter.order = index + 1
            chapter.save(update_fields=["title", "order"])
            chapter.panels.all().delete()
            chapter.questions.all().delete()
        else:
            chapter = Chapter.objects.create(course=course, order=index + 1, title=spec["title"])
        ComicPanel.objects.bulk_create([
            ComicPanel(
                chapter=chapter,
                order=pos,
                caption=speaker,
                speech_bubble=text,
                background_color=CAST.get(speaker, OTHER_SPEAKER)[0],
                bubble_align=CAST.get(speaker, OTHER_SPEAKER)[1],
            )
            for pos, (speaker, text) in enumerate(spec["panels"], start=1)
        ])
        ChapterQuestion.objects.bulk_create([
            ChapterQuestion(
                chapter=chapter, order=pos, prompt=prompt,
                options="\n".join(options), correct_index=correct, explanation=explanation,
            )
            for pos, (prompt, options, correct, explanation) in enumerate(spec.get("questions", []), start=1)
        ])
    for extra in existing[len(chapters):]:
        extra.delete()


def sync_curriculum(Course, Chapter, ComicPanel, ChapterQuestion, log=print):
    """Bring the database in line with this file. Safe to run repeatedly."""
    seen = set()
    for spec in ACTIVE_COURSES:
        course = _find_course(Course, spec)
        created = course is None
        if created:
            course = Course(code=spec["code"])
        if spec.get("preserve") and not created:
            # Phishing: display label and shelf position only.
            course.title = spec["title"]
            course.order = spec["order"]
            course.is_published = True
            course.is_coming_soon = False
            course.save(update_fields=["title", "order", "is_published", "is_coming_soon"])
            log(f"kept    {course.code}: {course.title} (content untouched)")
        else:
            course.title = spec["title"]
            course.order = spec["order"]
            course.is_published = True
            course.is_coming_soon = False
            if spec.get("short_description"):
                course.short_description = spec["short_description"]
                course.summary = spec["summary"]
            elif created:
                course.short_description = spec["title"]
            course.save()
            if spec.get("chapters"):
                _write_chapters(course, spec["chapters"], Chapter, ComicPanel, ChapterQuestion)
                if course.pdf_file:
                    log(f"WARNING {course.code}: a PDF is attached, and a PDF wins over chapters. "
                        "Remove it in the admin to show the new comic chapters.")
            log(f"{'created' if created else 'updated'} {course.code}: {course.title}")
        seen.add(course.pk)

    for spec in COMING_SOON_COURSES:
        course = _find_course(Course, spec)
        if course is None:
            course = Course.objects.create(
                code=spec["code"], title=spec["title"], short_description=spec["short_description"],
                order=spec["order"], is_published=True, is_coming_soon=True,
            )
            log(f"created {course.code}: {course.title} (coming soon)")
        else:
            # Existing description and content are kept for when the course opens.
            course.title = spec["title"]
            course.short_description = course.short_description or spec["short_description"]
            course.order = spec["order"]
            course.is_published = True
            course.is_coming_soon = True
            course.save(update_fields=["title", "short_description", "order", "is_published", "is_coming_soon"])
            log(f"locked  {course.code}: {course.title} (coming soon)")
        seen.add(course.pk)

    extras = Course.objects.active().exclude(pk__in=seen)
    for course in extras:
        log(f"WARNING {course.code}: {course.title} is published but not part of the curriculum. "
            "Unpublish it or mark it Coming Soon in the admin to keep exactly eight active courses.")
