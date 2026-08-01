"""
games/data.py
----------------
Static content for the Phishing Simulator. Kept in its own file so the
quiz questions can be edited/expanded WITHOUT touching any view logic.

Each item is a simulated email. `is_phishing` is the correct answer.
`red_flags` are shown as feedback AFTER the user answers.
"""

PHISHING_QUESTIONS = [
    {
        "id": 1,
        "sender": "security@paypa1-support.com",
        "subject": "Urgent: Your account has been suspended",
        "body": "We detected unusual activity. Click here immediately to verify "
                "your identity or your account will be permanently closed within 24 hours.",
        "is_phishing": True,
        "red_flags": [
            "Sender domain 'paypa1-support.com' uses a '1' instead of an 'l' (typosquatting).",
            "Creates false urgency with a 24-hour countdown.",
            "Generic threat of account closure to provoke panic clicks.",
        ],
    },
    {
        "id": 2,
        "sender": "newsletter@nationalgeographic.com",
        "subject": "This week: Inside the Amazon rainforest",
        "body": "Explore our latest photo essay documenting wildlife conservation "
                "efforts across South America. Read the full story on our website.",
        "is_phishing": False,
        "red_flags": [
            "Legitimate, well-known domain.",
            "No urgency, no request for credentials or personal info.",
            "Consistent with a normal newsletter subscription.",
        ],
    },
    {
        "id": 3,
        "sender": "it-helpdesk@yourcompany-support.net",
        "subject": "Password Expiry Notice",
        "body": "Your company password expires today. Log in now using the link below "
                "with your current username and password to keep your access active.",
        "is_phishing": True,
        "red_flags": [
            "Domain doesn't match a real internal IT domain (uses '-support.net').",
            "Asks you to 're-enter' credentials via an email link, not your normal portal.",
            "Same-day urgency is a classic pressure tactic.",
        ],
    },
    {
        "id": 4,
        "sender": "no-reply@github.com",
        "subject": "[GitHub] A new SSH key was added to your account",
        "body": "A new SSH key was added to your account. If you did not do this, "
                "please review your security settings from your account dashboard.",
        "is_phishing": False,
        "red_flags": [
            "Real GitHub security domain.",
            "Directs you to check settings yourself rather than clicking an embedded login link.",
            "Standard, expected security notification format.",
        ],
    },
    {
        "id": 5,
        "sender": "billing@amaz0n-orders.com",
        "subject": "Your order could not be processed",
        "body": "There was an issue charging your card for order #58231. Update your "
                "payment details within 12 hours to avoid order cancellation.",
        "is_phishing": True,
        "red_flags": [
            "Domain uses a zero instead of 'o' in 'amazon' (typosquatting).",
            "Vague order number designed to seem specific without being verifiable.",
            "Short deadline (12 hours) pressures quick action.",
        ],
    },
]


"""
Static content for the Password Cracker Challenge.
Each item is a candidate password. `strength` is the correct classification
("weak", "medium", "strong"). `explanation` is shown as feedback AFTER
the user answers, teaching WHY it falls into that category.
"""

PASSWORD_QUESTIONS = [
    {
        "id": 1,
        "password": "123456",
        "strength": "weak",
        "explanation": [
            "One of the most common passwords in every major breach dataset.",
            "Purely sequential digits -- cracked instantly by any password-cracking tool.",
            "Contains no letters, symbols, or unpredictability whatsoever.",
        ],
    },
    {
        "id": 2,
        "password": "Summer2024",
        "strength": "medium",
        "explanation": [
            "Better than pure digits -- mixes uppercase, lowercase, and numbers.",
            "Still built from a dictionary word plus a predictable year, a very common pattern.",
            "Vulnerable to 'mangled dictionary' attacks that try common words with number suffixes.",
        ],
    },
    {
        "id": 3,
        "password": "P@ssw0rd!",
        "strength": "weak",
        "explanation": [
            "Classic 'leetspeak' substitution (a->@, o->0) that cracking tools check for by default.",
            "Still fundamentally the word 'password' -- one of the first guesses in any attack.",
            "Length alone (9 characters) doesn't save it since the pattern is so predictable.",
        ],
    },
    {
        "id": 4,
        "password": "correct-horse-battery-staple",
        "strength": "strong",
        "explanation": [
            "Long passphrase (28+ characters) -- length is one of the strongest defenses against brute force.",
            "Four unrelated words create high entropy despite being memorable.",
            "Not based on personal information or a single dictionary word.",
        ],
    },
    {
        "id": 5,
        "password": "Tr@ining!2024#Cyber",
        "strength": "strong",
        "explanation": [
            "Long (19 characters), mixes uppercase, lowercase, numbers, and multiple symbols.",
            "Not a single dictionary word with simple substitutions -- structure is harder to predict.",
            "High overall entropy makes brute-force and dictionary attacks impractical.",
        ],
    },
]
