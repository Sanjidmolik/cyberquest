"""
Domain scenarios for the reusable simulation console engine.
Fictional/safe data only — no real targets, credentials, or attack how-tos.
"""

DOMAINS = [
    {
        "slug": "phishing",
        "label": "Phishing",
        "full_label": "Phishing",
        "game_key": "phishing_simulator",
        "game_url": "games:phishing_simulator",
        "emoji": "📧",
        "color": "#ff2ec4",
    },
    {
        "slug": "password",
        "label": "Password Security",
        "full_label": "Password Security",
        "game_key": "password_cracker",
        "game_url": "games:password_cracker",
        "emoji": "🔑",
        "color": "#ff9800",
    },
    {
        "slug": "network",
        "label": "Network Defense",
        "full_label": "Network Defense",
        "game_key": "network_defense",
        "game_url": "games:network_defense",
        "emoji": "🛡️",
        "color": "#3aa0ff",
    },
    {
        "slug": "cryptography",
        "label": "Cryptography",
        "full_label": "Cryptography",
        "game_key": "cryptography",
        "game_url": "games:cryptography",
        "emoji": "🔐",
        "color": "#39ff88",
    },
    {
        "slug": "osint",
        "label": "OSINT",
        "full_label": "OSINT Investigation",
        "game_key": "osint",
        "game_url": "games:osint",
        "emoji": "🕵️",
        "color": "#ffd23f",
    },
]

DOMAIN_BY_SLUG = {d["slug"]: d for d in DOMAINS}


def _inv(label, score, title, fields, feedback):
    return {
        "kind": "investigate",
        "label": label,
        "score": score,
        "reveal": {"title": title, "fields": fields, "feedback": feedback},
    }


def _dec(label, quality, score, consequence_title, consequence, response):
    return {
        "kind": "decide",
        "label": label,
        "quality": quality,  # correct | unsafe | poor
        "score": score,
        "consequence_title": consequence_title,
        "consequence": consequence,
        "response": response,
    }


SCENARIOS = {
    # ---------- PHISHING: Email Security Console ----------
    "phishing_microsoft_disable": {
        "key": "phishing_microsoft_disable",
        "domain": "phishing",
        "environment": "Email Security Console",
        "workspace_type": "email",
        "incident_code": "CQ-PH-001",
        "severity": "HIGH",
        "title": "Suspicious email reported by employee",
        "briefing": {
            "employee": "Rahim Ahmed",
            "department": "Finance",
            "subject": "Your Microsoft account will be disabled",
            "time": "09:42 AM",
            "summary": (
                "An employee reported a suspicious account-security email. "
                "Open the console, investigate progressively, then decide."
            ),
        },
        "workspace": {
            "from_display": "Microsoft Security",
            "to": "rahim.ahmed@acme-fictional.example",
            "subject": "Your Microsoft account will be disabled",
            "time": "Today 09:38",
            "body": (
                "Dear User,\n\nWe detected unusual activity on your account. "
                "Click Verify Account below within 30 minutes or access will be disabled.\n\n"
                "— Microsoft Security Team"
            ),
            "link_display": "Verify Account → https://account-security.example/",
        },
        "required_evidence": ["inspect_sender", "inspect_domain", "inspect_link"],
        "missing_evidence_penalty": -10,
        "investigations": {
            "inspect_sender": _inv(
                "Inspect Sender", 10, "Sender Analysis",
                [
                    {"label": "Display name", "value": "Microsoft Security"},
                    {"label": "Sender address", "value": "Microsoft-Security@micros0ft-help.example"},
                ],
                "Sender address uses a lookalike domain (micros0ft-help.example), not a trusted vendor domain.",
            ),
            "inspect_domain": _inv(
                "Inspect Domain", 10, "Domain Check",
                [
                    {"label": "Domain", "value": "micros0ft-help.example"},
                    {"label": "Age (simulated)", "value": "Registered 2 days ago"},
                    {"label": "Reputation", "value": "Unknown / untrusted"},
                ],
                "Brand-new domains mimicking vendors are a common phishing signal.",
            ),
            "inspect_link": _inv(
                "Inspect Link", 10, "Link Analysis",
                [
                    {"label": "Displayed URL", "value": "https://account-security.example/"},
                    {"label": "Actual destination", "value": "https://fictional-login.example/session"},
                ],
                "Displayed text and destination do not match. Do not open the link.",
            ),
            "view_headers": _inv(
                "View Headers", 8, "Message Headers",
                [
                    {"label": "Reply-To", "value": "support@micros0ft-help.example"},
                    {"label": "Received path", "value": "external relay → corporate gateway"},
                ],
                "Reply-To stays on the suspicious domain.",
            ),
            "check_timeline": _inv(
                "Check Timeline", 7, "Incident Timeline",
                [
                    {"label": "09:38", "value": "Email delivered to Finance mailbox"},
                    {"label": "09:42", "value": "Employee reported without clicking"},
                ],
                "Employee reported quickly — good containment opportunity.",
            ),
        },
        "decisions": {
            "report_phishing": _dec(
                "Report as Phishing", "correct", 40,
                "Incident contained",
                "The suspicious email has been reported and isolated from the mailbox.",
                "Incident contained",
            ),
            "ignore": _dec(
                "Ignore", "unsafe", -30,
                "Threat remains active",
                "The email remains available to the employee and may be clicked later.",
                "No containment applied",
            ),
            "forward_employee": _dec(
                "Forward to Employee", "poor", -20,
                "Risk increased",
                "Forwarding returns the message to the user and may encourage interaction.",
                "Unsafe handling",
            ),
            "open_link": _dec(
                "Open Link", "unsafe", -30,
                "Incident escalated",
                "The simulated employee account is now considered potentially compromised.",
                "Account potentially compromised",
            ),
        },
    },

    # ---------- PASSWORD: Auth / Login Security Console ----------
    "password_auth_alert": {
        "key": "password_auth_alert",
        "domain": "password",
        "environment": "Authentication Security Console",
        "workspace_type": "auth",
        "incident_code": "CQ-PW-001",
        "severity": "HIGH",
        "title": "Authentication alert — unusual login pattern",
        "briefing": {
            "employee": "employee01",
            "department": "Operations",
            "subject": "Failed login storm + unusual success",
            "time": "03:14 AM",
            "summary": (
                "Monitoring flagged repeated failed logins followed by a successful sign-in "
                "from an unexpected location. Investigate, then choose a protective action."
            ),
        },
        "workspace": {
            "account": "employee01@acme-fictional.example",
            "failed_attempts": "17",
            "alert_time": "03:14 AM",
            "source_ip": "203.0.113.77 (fictional TEST-NET)",
            "status": "Account currently ACTIVE",
            "mfa": "Disabled",
        },
        "required_evidence": ["view_login_history", "inspect_source", "check_location"],
        "missing_evidence_penalty": -10,
        "investigations": {
            "view_login_history": _inv(
                "View Login History", 10, "Login History",
                [
                    {"label": "02:58–03:12", "value": "17 failed password attempts"},
                    {"label": "03:13", "value": "1 successful login"},
                ],
                "Burst failures then success often indicate credential stuffing or password guessing.",
            ),
            "inspect_source": _inv(
                "Inspect Source", 10, "Source Analysis",
                [
                    {"label": "Source IP", "value": "203.0.113.77 (fictional)"},
                    {"label": "ASN / note", "value": "Unfamiliar hosting range (simulated)"},
                ],
                "Source does not match the user's known office or home ranges.",
            ),
            "check_user_activity": _inv(
                "Check User Activity", 8, "User Activity",
                [
                    {"label": "Last trusted login", "value": "Yesterday 18:02 (office network)"},
                    {"label": "Password age", "value": "412 days (stale)"},
                ],
                "Long-lived password and sudden night activity raise risk.",
            ),
            "check_location": _inv(
                "Check Location", 10, "Location Check",
                [
                    {"label": "Typical location", "value": "Dhaka HQ (simulated)"},
                    {"label": "Alert location", "value": "Distant region never used by this account"},
                ],
                "Impossible-travel style signal for this fictional account.",
            ),
            "review_policy": _inv(
                "Review Security Policy", 7, "Policy Review",
                [
                    {"label": "MFA", "value": "Not enforced for this role"},
                    {"label": "Lockout", "value": "Soft lockout after 20 failures"},
                ],
                "Weak policy allowed continued attempts until success.",
            ),
        },
        "decisions": {
            "lock_account": _dec(
                "Lock Account", "correct", 35,
                "Account locked",
                "The account is locked pending verified recovery. Session risk is reduced.",
                "Protective lock applied",
            ),
            "require_reset": _dec(
                "Require Password Reset", "correct", 40,
                "Reset required",
                "Password reset forced through a trusted channel; stale credential invalidated.",
                "Credential refreshed",
            ),
            "ignore": _dec(
                "Ignore", "unsafe", -30,
                "Threat remains active",
                "The unusual session remains usable. Account takeover risk continues.",
                "No protective action",
            ),
            "escalate": _dec(
                "Escalate", "poor", 15,
                "Escalated without containment",
                "Ticket created, but the account was left unlocked during investigation.",
                "Escalated only",
            ),
        },
    },

    # ---------- NETWORK: Mini SOC / Network Monitor ----------
    "network_workstation_exfil": {
        "key": "network_workstation_exfil",
        "domain": "network",
        "environment": "Network Security Monitor",
        "workspace_type": "network",
        "incident_code": "CQ-NW-001",
        "severity": "HIGH",
        "title": "Unusual outbound traffic from internal host",
        "briefing": {
            "employee": "Asset WORKSTATION-07",
            "department": "Marketing",
            "subject": "Anomalous upload volume",
            "time": "02:07 AM",
            "summary": (
                "Sensors show unusual outbound traffic from WORKSTATION-07. "
                "Inspect the mini-SOC view, gather evidence, then contain appropriately."
            ),
        },
        "workspace": {
            "topology": [
                {"name": "Internet", "alert": False},
                {"name": "Firewall", "alert": False},
                {"name": "WEB-SERVER", "alert": False},
                {"name": "DATABASE", "alert": False},
                {"name": "WORKSTATION-07", "alert": True},
                {"name": "FILE-SERVER", "alert": False},
            ],
            "alert_banner": "Suspicious outbound connections from WORKSTATION-07",
            "bytes_out": "1.8 GB in 22 minutes (baseline: ~40 MB)",
        },
        "required_evidence": ["view_traffic", "inspect_source_host", "inspect_destination"],
        "missing_evidence_penalty": -10,
        "investigations": {
            "view_traffic": _inv(
                "View Traffic", 10, "Traffic Summary",
                [
                    {"label": "Direction", "value": "Internal → External"},
                    {"label": "Volume", "value": "1.8 GB outbound (anomalous)"},
                    {"label": "Ports", "value": "443/TCP bursts"},
                ],
                "High-volume outbound HTTPS from a workstation is abnormal overnight.",
            ),
            "inspect_source_host": _inv(
                "Inspect Source Host", 10, "Source Host",
                [
                    {"label": "Host", "value": "WORKSTATION-07"},
                    {"label": "Owner", "value": "Marketing laptop (offline per user)"},
                    {"label": "Process (sim)", "value": "unknown_uploader.exe"},
                ],
                "Owner reports they are asleep — host activity is unexpected.",
            ),
            "inspect_destination": _inv(
                "Inspect Destination", 10, "Destination",
                [
                    {"label": "Remote IP", "value": "198.51.100.23 (fictional TEST-NET)"},
                    {"label": "Category", "value": "Unclassified external host"},
                ],
                "Destination is not on the allowlist for Marketing assets.",
            ),
            "view_timeline": _inv(
                "View Timeline", 8, "Event Timeline",
                [
                    {"label": "01:55", "value": "New process spawned"},
                    {"label": "02:07", "value": "Outbound transfer accelerated"},
                ],
                "Process start precedes the transfer spike.",
            ),
            "check_protocol": _inv(
                "Check Protocol", 7, "Protocol Notes",
                [
                    {"label": "Protocol", "value": "TLS 1.2"},
                    {"label": "Note", "value": "Encrypted channel — content not readable"},
                ],
                "Encryption hides payload; containment decisions rely on metadata.",
            ),
        },
        "decisions": {
            "isolate_host": _dec(
                "Isolate Host", "correct", 40,
                "Host isolated",
                "WORKSTATION-07 was segmented from the network. Outbound transfer stopped.",
                "Containment successful",
            ),
            "block_connection": _dec(
                "Block Connection", "correct", 30,
                "Connection blocked",
                "Firewall rule blocked the destination. Host still online for forensics.",
                "Traffic blocked",
            ),
            "continue_monitoring": _dec(
                "Continue Monitoring", "poor", -10,
                "Delay in containment",
                "Monitoring continued while data transfer persisted.",
                "Insufficient response",
            ),
            "escalate": _dec(
                "Escalate", "poor", 10,
                "Escalated late",
                "Incident ticket opened, but no immediate containment action was taken.",
                "Escalated without isolate",
            ),
        },
    },

    # ---------- CRYPTO: Secure Communication Audit Console ----------
    "crypto_message_audit": {
        "key": "crypto_message_audit",
        "domain": "cryptography",
        "environment": "Secure Communication Audit Console",
        "workspace_type": "crypto",
        "incident_code": "CQ-CR-001",
        "severity": "MEDIUM",
        "title": "Fictional secure-message workflow review",
        "briefing": {
            "employee": "Partner Integrations Team",
            "department": "Engineering",
            "subject": "Customer data sharing method",
            "time": "11:05 AM",
            "summary": (
                "A team claims their message workflow is 'secure'. Audit the configuration, "
                "identify weaknesses, and choose the correct corrective action."
            ),
        },
        "workspace": {
            "system_name": "PartnerDrop (fictional)",
            "claim": "We encrypt everything before sharing",
            "channel": "Shared team chat + download link",
            "data_type": "Customer contact exports (fictional sample)",
        },
        "required_evidence": ["encryption_method", "key_management", "authentication"],
        "missing_evidence_penalty": -10,
        "investigations": {
            "encryption_method": _inv(
                "Encryption Method", 10, "Encryption Review",
                [
                    {"label": "Claimed method", "value": "Reversible 'password encryption' cipher"},
                    {"label": "Password storage claim", "value": "Encrypted (reversible)"},
                ],
                "Passwords should be salted+hashed, not reversibly encrypted.",
            ),
            "key_management": _inv(
                "Key Management", 10, "Key Handling",
                [
                    {"label": "Key location", "value": "Same shared document as ciphertext"},
                    {"label": "Access control", "value": "Entire chat channel can read it"},
                ],
                "Keys stored with ciphertext defeat the purpose of encryption.",
            ),
            "authentication": _inv(
                "Authentication", 10, "Auth Check",
                [
                    {"label": "Sender verification", "value": "None (shared link only)"},
                    {"label": "Recipient proof", "value": "Anyone with the link"},
                ],
                "No authentication means confidentiality depends on link secrecy alone.",
            ),
            "integrity_check": _inv(
                "Integrity Check", 8, "Integrity",
                [
                    {"label": "Checksum / MAC", "value": "Not used"},
                    {"label": "Tamper detection", "value": "None"},
                ],
                "Without integrity checks, silent modification is possible.",
            ),
            "security_config": _inv(
                "Security Configuration", 8, "Transport Config",
                [
                    {"label": "Download transport", "value": "http://files.partnerdrop-fictional.example"},
                    {"label": "TLS", "value": "Not enforced"},
                ],
                "Sensitive downloads need encrypted transport (HTTPS/TLS).",
            ),
        },
        "decisions": {
            "recommend_secure_practice": _dec(
                "Recommend Secure Practice", "correct", 40,
                "Secure redesign accepted",
                "You required hashing for secrets, separated keys, TLS, and authenticated access.",
                "Corrective action applied",
            ),
            "approve_as_is": _dec(
                "Approve As-Is", "unsafe", -30,
                "Insecure workflow approved",
                "Customer data remains exposed to chat members and plain HTTP downloads.",
                "Risk accepted incorrectly",
            ),
            "only_add_tls": _dec(
                "Only Enable TLS", "poor", 5,
                "Partial fix",
                "TLS helps transport, but key co-location and reversible password storage remain.",
                "Incomplete remediation",
            ),
            "escalate_only": _dec(
                "Escalate Without Guidance", "poor", 0,
                "No clear remediation",
                "Ticket filed without identifying the cryptographic mistakes.",
                "Escalated without findings",
            ),
        },
    },

    # ---------- OSINT: Investigation Workspace ----------
    "osint_identity_case": {
        "key": "osint_identity_case",
        "domain": "osint",
        "environment": "Investigation Workspace",
        "workspace_type": "osint",
        "incident_code": "CQ-OS-001",
        "severity": "MEDIUM",
        "title": "Fictional online identity verification",
        "briefing": {
            "employee": "Tipster (anonymous)",
            "department": "Trust & Safety (fictional)",
            "subject": "Claimed link between public profile and internal incident",
            "time": "04:20 PM",
            "summary": (
                "An anonymous tip claims a public profile proves involvement in a fictional incident. "
                "Collect and compare open sources, assess reliability, then submit a finding. "
                "Use only fictional public-safe data — no targeting of real people."
            ),
        },
        "workspace": {
            "case_name": "CASE-OSINT-441",
            "subject_handle": "@nova_analyst_fictional",
            "claim": "This public profile proves the person caused the breach.",
            "rule": "Corroborate before concluding. Weak evidence ≠ proof.",
        },
        "required_evidence": ["public_profile", "username_history", "public_post", "verify_source"],
        "missing_evidence_penalty": -10,
        "investigations": {
            "public_profile": _inv(
                "Public Profile", 10, "Public Profile",
                [
                    {"label": "Display name", "value": "Nova Analyst"},
                    {"label": "Claimed role", "value": "Security intern (unverified)"},
                    {"label": "Location", "value": "Not listed"},
                ],
                "Profile alone does not prove involvement in any incident.",
            ),
            "website": _inv(
                "Website", 8, "Linked Website",
                [
                    {"label": "URL", "value": "https://nova-portfolio-fictional.example"},
                    {"label": "Content", "value": "Generic template portfolio"},
                ],
                "Site provides no corroborating incident evidence.",
            ),
            "username_history": _inv(
                "Username History", 10, "Username Comparison",
                [
                    {"label": "Handle A", "value": "@nova_analyst_fictional"},
                    {"label": "Handle B (tip)", "value": "@nova_a (different platform)"},
                    {"label": "Overlap", "value": "Partial name only — weak link"},
                ],
                "Username similarity is weak evidence without more correlation.",
            ),
            "public_post": _inv(
                "Public Post", 10, "Public Post Review",
                [
                    {"label": "Post date", "value": "3 months before the fictional incident"},
                    {"label": "Content", "value": "Generic cybersecurity meme"},
                ],
                "Timeline undermines the tip — post predates the event.",
            ),
            "domain_information": _inv(
                "Domain Information", 7, "Domain Notes",
                [
                    {"label": "Domain age", "value": "4 years"},
                    {"label": "Registrant", "value": "Privacy-protected (common)"},
                ],
                "Domain age neither confirms nor denies the tip.",
            ),
            "verify_source": _inv(
                "Assess Tip Reliability", 10, "Source Reliability",
                [
                    {"label": "Tip channel", "value": "Anonymous forum DM"},
                    {"label": "Corroboration", "value": "None provided"},
                ],
                "Unverified anonymous tips require high caution.",
            ),
            "timeline": _inv(
                "Timeline", 8, "Correlation Timeline",
                [
                    {"label": "Incident (fictional)", "value": "12 Sep"},
                    {"label": "Cited post", "value": "01 Jun — earlier"},
                ],
                "No temporal correlation supporting the claim.",
            ),
        },
        "decisions": {
            "submit_insufficient_evidence": _dec(
                "Submit: Insufficient Evidence", "correct", 40,
                "Finding documented",
                "You correctly concluded public data does not reliably support the tip.",
                "Responsible finding submitted",
            ),
            "confirm_involvement": _dec(
                "Confirm Involvement", "unsafe", -30,
                "False confidence",
                "You asserted guilt from weak public signals — risk of harming an innocent person.",
                "Unsafe conclusion",
            ),
            "dismiss_without_notes": _dec(
                "Dismiss Without Documentation", "poor", -10,
                "Incomplete casework",
                "Closing without notes loses the reliability assessment trail.",
                "Poor documentation",
            ),
            "request_private_data": _dec(
                "Seek Private Data", "unsafe", -30,
                "Out of scope",
                "Practice stops at public/fictional sources. Seeking private data is not allowed here.",
                "Policy violation in simulation",
            ),
        },
    },
}

DOMAIN_SCENARIO = {s["domain"]: key for key, s in SCENARIOS.items()}


def get_scenario(key):
    return SCENARIOS.get(key)


def get_domain_scenario(domain_slug):
    key = DOMAIN_SCENARIO.get(domain_slug)
    return SCENARIOS.get(key) if key else None
