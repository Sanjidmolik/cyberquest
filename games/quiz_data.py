"""
games/quiz_data.py
----------------------
Content for the generic multiple-choice quiz games: Cryptography,
OSINT, Steganography, and Network Defense.

Each entry in QUIZ_GAMES is a self-contained game definition. To add a
FIFTH quiz-style game later, an admin/developer just adds one more
entry here -- no new views, templates, or URL routes needed (see the
generic quiz_game() view in views.py that reads this dict).
"""

QUIZ_GAMES = {
    "cryptography": {
        "title": "Cryptography Challenge",
        "emoji": "🔐",
        "intro": "Test your understanding of encryption, hashing, and classic ciphers.",
        "questions": [
            {
                "id": 1,
                "prompt": "What does encrypting a message primarily protect against?",
                "options": [
                    "Someone reading the message if they intercept it",
                    "The message being deleted accidentally",
                    "The message taking up too much storage space",
                    "The recipient forgetting the message",
                ],
                "correct_index": 0,
                "explanation": "Encryption scrambles data so that only someone with the correct key can read it, protecting confidentiality if it's intercepted.",
            },
            {
                "id": 2,
                "prompt": "'WKLV LV D VHFUHW' was encrypted by shifting each letter forward by 3. What kind of cipher is this?",
                "options": ["A Caesar cipher", "AES encryption", "A hash function", "Base64 encoding"],
                "correct_index": 0,
                "explanation": "A Caesar cipher shifts each letter by a fixed number of positions in the alphabet — simple, and trivially broken today.",
            },
            {
                "id": 3,
                "prompt": "Which statement about hashing is TRUE?",
                "options": [
                    "A good hash function is designed to be reversible with the right key",
                    "Hashing and encryption are the same thing",
                    "A good hash function is designed to be a one-way function — you can't get the original data back from the hash",
                    "Hashes are only used for encrypting emails",
                ],
                "correct_index": 2,
                "explanation": "Hashing is one-way by design — it's used to verify data (like passwords) without ever storing or recovering the original value.",
            },
            {
                "id": 4,
                "prompt": "You see the text 'SGVsbG8gV29ybGQ=' in a system log. What is this most likely an example of?",
                "options": [
                    "Strong military-grade encryption",
                    "Base64 encoding — NOT encryption, just a way to represent data as text",
                    "A secure password hash",
                    "A broken file",
                ],
                "correct_index": 1,
                "explanation": "Base64 is encoding, not encryption — it's trivially reversible by anyone and provides no real confidentiality.",
            },
            {
                "id": 5,
                "prompt": "Why is AES-256 considered strong encryption today?",
                "options": [
                    "It uses a very large key space, making brute-force attacks impractical with current technology",
                    "It hides the fact that a message was encrypted at all",
                    "It never needs a key to decrypt",
                    "It's the fastest algorithm to compute",
                ],
                "correct_index": 0,
                "explanation": "AES-256's key space is astronomically large — even with massive computing power, brute-forcing it isn't feasible with today's technology.",
            },
        ],
    },
    "osint": {
        "title": "OSINT Investigation",
        "emoji": "🕵️",
        "intro": "Open-Source Intelligence: gathering information from publicly available sources, ethically.",
        "questions": [
            {
                "id": 1,
                "prompt": "What does OSINT stand for?",
                "options": [
                    "Open-Source Intelligence",
                    "Online Security Interface",
                    "Operational System Integration",
                    "Offline Signal Interception",
                ],
                "correct_index": 0,
                "explanation": "OSINT means gathering intelligence from publicly available sources — social media, public records, websites, etc.",
            },
            {
                "id": 2,
                "prompt": "Which of these is a legitimate, ethical OSINT technique?",
                "options": [
                    "Guessing someone's password using leaked credential lists",
                    "Searching a person's public social media posts for information they chose to share",
                    "Calling someone and pretending to be tech support to get their password",
                    "Installing spyware on someone's device without consent",
                ],
                "correct_index": 1,
                "explanation": "Ethical OSINT only uses information that is already publicly and legitimately available — never deception, hacking, or unauthorized access.",
            },
            {
                "id": 3,
                "prompt": "A reverse image search is commonly used in OSINT to:",
                "options": [
                    "Encrypt an image so it can't be searched",
                    "Find where else an image appears online, or its original source",
                    "Automatically delete metadata from a photo",
                    "Convert an image into a password",
                ],
                "correct_index": 1,
                "explanation": "Reverse image search helps verify if a photo is genuine, original, or has been reused/faked elsewhere online.",
            },
            {
                "id": 4,
                "prompt": "Why might metadata in a photo (EXIF data) be relevant to an OSINT investigation?",
                "options": [
                    "It can reveal the exact time and GPS location the photo was taken",
                    "It changes the image's colors",
                    "It automatically encrypts the photo",
                    "It has no practical use in investigations",
                ],
                "correct_index": 0,
                "explanation": "EXIF metadata can include GPS coordinates, timestamps, and device info — valuable in investigations, but also a privacy risk if shared unknowingly.",
            },
            {
                "id": 5,
                "prompt": "What is a key ethical/legal boundary OSINT investigators must respect?",
                "options": [
                    "There are no boundaries if the information is technically online",
                    "Only using information gathered legally and publicly, and respecting applicable privacy laws",
                    "It's fine to access private accounts if the password is easy to guess",
                    "Selling gathered personal data is always acceptable",
                ],
                "correct_index": 1,
                "explanation": "Legitimate OSINT stays within legal and ethical bounds — public data only, no unauthorized access, and respect for privacy regulations.",
            },
        ],
    },
    "steganography": {
        "title": "Steganography Hunt",
        "emoji": "🖼️",
        "intro": "The art of hiding information in plain sight — inside images, audio, or other files.",
        "questions": [
            {
                "id": 1,
                "prompt": "What is steganography?",
                "options": [
                    "The practice of hiding a secret message inside another file so its existence isn't obvious",
                    "A type of firewall",
                    "A password-cracking technique",
                    "Encrypting an email's subject line",
                ],
                "correct_index": 0,
                "explanation": "Unlike encryption (which hides the CONTENT of a message), steganography hides the fact that a hidden message exists at all.",
            },
            {
                "id": 2,
                "prompt": "How does the main difference between steganography and encryption?",
                "options": [
                    "They are exactly the same thing",
                    "Encryption hides content but the message is obviously present; steganography hides that a message exists at all",
                    "Steganography is always stronger than encryption",
                    "Encryption only works on images",
                ],
                "correct_index": 1,
                "explanation": "Encryption scrambles a message you know exists. Steganography conceals a message inside something innocent-looking, so an observer may not even suspect it's there.",
            },
            {
                "id": 3,
                "prompt": "A common technique for hiding data inside an image is:",
                "options": [
                    "Deleting random pixels",
                    "Slightly modifying the least significant bits of pixel data — changes too small for the human eye to notice",
                    "Changing the file extension only",
                    "Making the image black and white",
                ],
                "correct_index": 1,
                "explanation": "LSB (Least Significant Bit) steganography hides data by making tiny, visually undetectable changes to pixel values.",
            },
            {
                "id": 4,
                "prompt": "Why might an attacker use steganography in a real attack?",
                "options": [
                    "To make malware or stolen data look like an ordinary, harmless image file and evade detection",
                    "To make files load faster",
                    "To automatically encrypt a hard drive",
                    "To improve image quality",
                ],
                "correct_index": 0,
                "explanation": "Attackers can hide malicious payloads inside seemingly normal images to sneak them past filters and security scans.",
            },
            {
                "id": 5,
                "prompt": "Which of these could be a red flag that an image file might contain hidden data?",
                "options": [
                    "The image displays normally",
                    "An unusually large file size compared to a normal image of the same dimensions/quality",
                    "The image has bright colors",
                    "The image is a JPEG",
                ],
                "correct_index": 1,
                "explanation": "A suspiciously large file size for what should be a simple image can indicate extra hidden data embedded within it.",
            },
        ],
    },
    "network_defense": {
        "title": "Network Defense",
        "emoji": "🛡️",
        "intro": "Simulate key decisions defenders make when protecting a live network.",
        "questions": [
            {
                "id": 1,
                "prompt": "What is the primary purpose of a firewall?",
                "options": [
                    "To speed up internet connection",
                    "To control and filter incoming/outgoing network traffic based on defined security rules",
                    "To store backup copies of files",
                    "To automatically write antivirus software",
                ],
                "correct_index": 1,
                "explanation": "A firewall acts as a gatekeeper, allowing or blocking traffic based on rules — a core building block of network defense.",
            },
            {
                "id": 2,
                "prompt": "You notice one internal computer suddenly sending huge amounts of data to an unfamiliar external IP address at 3 AM. What should a defender do first?",
                "options": [
                    "Ignore it, probably nothing",
                    "Investigate the traffic and isolate the machine if it looks malicious",
                    "Turn off the entire network permanently",
                    "Email the unfamiliar IP address to ask what's happening",
                ],
                "correct_index": 1,
                "explanation": "Unusual outbound traffic, especially at odd hours, is a classic sign of a compromised machine (e.g., data exfiltration) — isolate and investigate quickly.",
            },
            {
                "id": 3,
                "prompt": "What does 'principle of least privilege' mean in network security?",
                "options": [
                    "Everyone should have administrator access for convenience",
                    "Users and systems should only have the minimum access necessary to do their job",
                    "Only the IT department is allowed to use the network",
                    "Privileges should be given randomly",
                ],
                "correct_index": 1,
                "explanation": "Least privilege limits damage if an account is compromised — an attacker only gets whatever limited access that account had.",
            },
            {
                "id": 4,
                "prompt": "An Intrusion Detection System (IDS) is best described as:",
                "options": [
                    "A tool that monitors network traffic for suspicious activity and alerts defenders",
                    "A type of encryption algorithm",
                    "A backup power supply",
                    "A password manager",
                ],
                "correct_index": 0,
                "explanation": "An IDS watches network activity and flags patterns that look like attacks, giving defenders visibility to respond.",
            },
            {
                "id": 5,
                "prompt": "Why is network segmentation (dividing a network into separate zones) a good defensive practice?",
                "options": [
                    "It makes the network slower on purpose",
                    "If one segment is compromised, segmentation helps contain the breach instead of letting it spread everywhere",
                    "It removes the need for passwords",
                    "It's only useful for very small networks",
                ],
                "correct_index": 1,
                "explanation": "Segmentation limits how far an attacker can move if they breach one part of the network — containment instead of total compromise.",
            },
        ],
    },
}


# Folded into the generic engine for consistency with the other 4 games
# (originally had bespoke views/templates -- now driven by the same
# QUIZ_GAMES data structure as everything else).
QUIZ_GAMES["phishing_simulator"] = {
    "title": "Phishing Simulator",
    "emoji": "📧",
    "intro": "Spot the fake emails before they get you.",
    "questions": [
        {
            "id": 1,
            "prompt": "From: support@paypa1-security.com\nSubject: Urgent: Verify your account now\n\n"
                      "\"Click here immediately or your account will be suspended.\"",
            "options": ["This is a phishing email", "This is a legitimate email"],
            "correct_index": 0,
            "explanation": "Misspelled domain ('paypa1', not 'paypal') and false urgency are classic phishing red flags.",
        },
        {
            "id": 2,
            "prompt": "From: billing@spotify.com\nSubject: Your receipt for August\n\n"
                      "\"Thanks for your payment. View your invoice in your account.\"",
            "options": ["This is a phishing email", "This is a legitimate email"],
            "correct_index": 1,
            "explanation": "Legitimate sender domain, and no urgent action or sensitive info requested.",
        },
        {
            "id": 3,
            "prompt": "From: hr@yourcompany-portal.net\nSubject: Update your payroll info\n\n"
                      "\"Click this link to update your direct deposit details today.\"",
            "options": ["This is a phishing email", "This is a legitimate email"],
            "correct_index": 0,
            "explanation": "A suspicious external domain for internal HR, requesting sensitive financial details -- a common payroll-diversion scam.",
        },
        {
            "id": 4,
            "prompt": "From: no-reply@github.com\nSubject: New sign-in to your account\n\n"
                      "\"We noticed a new sign-in. If this was you, no action is needed.\"",
            "options": ["This is a phishing email", "This is a legitimate email"],
            "correct_index": 1,
            "explanation": "A standard security notification with no urgent action demanded -- typical of real account alerts.",
        },
        {
            "id": 5,
            "prompt": "From: prize@lottery-winner-intl.com\nSubject: You've won $1,000,000!\n\n"
                      "\"Claim your prize now by sending your bank details.\"",
            "options": ["This is a phishing email", "This is a legitimate email"],
            "correct_index": 0,
            "explanation": "A too-good-to-be-true prize asking for bank details directly is a textbook advance-fee scam.",
        },
    ],
}

QUIZ_GAMES["password_cracker"] = {
    "title": "Password Cracker Challenge",
    "emoji": "🔑",
    "intro": "For each password, decide how it would hold up against a real attacker.",
    "questions": [
        {
            "id": 1, "prompt": "Password: 123456",
            "options": ["Weak", "Medium", "Strong"], "correct_index": 0,
            "explanation": "One of the most common passwords in every breach dataset -- purely sequential digits, cracked instantly.",
        },
        {
            "id": 2, "prompt": "Password: Summer2024",
            "options": ["Weak", "Medium", "Strong"], "correct_index": 1,
            "explanation": "Better than pure digits, but still a dictionary word plus a predictable year -- a very common pattern.",
        },
        {
            "id": 3, "prompt": "Password: P@ssw0rd!",
            "options": ["Weak", "Medium", "Strong"], "correct_index": 0,
            "explanation": "Classic leetspeak substitution (a→@, o→0) that cracking tools check for by default -- still fundamentally 'password'.",
        },
        {
            "id": 4, "prompt": "Password: correct-horse-battery-staple",
            "options": ["Weak", "Medium", "Strong"], "correct_index": 2,
            "explanation": "A long passphrase (28+ characters) with unrelated words creates high entropy despite being memorable.",
        },
        {
            "id": 5, "prompt": "Password: Tr@ining!2024#Cyber",
            "options": ["Weak", "Medium", "Strong"], "correct_index": 2,
            "explanation": "Long, mixes uppercase/lowercase/numbers/symbols, and isn't a single predictable dictionary word.",
        },
    ],
}
