"""Additional practice scenarios. Fictional organizations and TEST-NET addresses only."""


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
        "quality": quality,
        "score": score,
        "consequence_title": consequence_title,
        "consequence": consequence,
        "response": response,
    }


def _scene(nodes, suspicious, evidence_nodes):
    return {"nodes": nodes, "suspicious": suspicious, "evidence_nodes": evidence_nodes}


def _n(node_id, label, x, y, z=12):
    return {"id": node_id, "label": label, "x": x, "y": y, "z": z}


EXTRA_SCENARIOS = {
    "phishing_google_login": {
        "key": "phishing_google_login",
        "domain": "phishing",
        "activity_type": "simulation",
        "difficulty": "intermediate",
        "environment": "Email Security Console",
        "workspace_type": "email",
        "incident_code": "CQ-PH-002",
        "severity": "HIGH",
        "title": "Fake Google login page",
        "objective": "Compare a displayed vendor link with the real destination before anyone signs in.",
        "briefing": {
            "employee": "Lina Cho",
            "department": "Design, Harbor & Co.",
            "subject": "Shared drive access expired",
            "time": "10:16 AM",
            "summary": "A designer received a drive-share notice that asks her to sign in again. Inspect the message before she uses the link.",
        },
        "workspace": {
            "from_display": "Google Drive",
            "to": "lina.cho@harborco.example",
            "subject": "Shared drive access expired",
            "time": "Today 10:14",
            "body": "Hi Lina,\n\nYour access to the Brand Assets drive expired. Sign in to restore access before the client review.\n\n— Drive Notifications",
            "link_display": "Restore access → https://drive.google.com/",
        },
        "required_evidence": ["inspect_sender", "inspect_link", "inspect_page"],
        "missing_evidence_penalty": -10,
        "investigations": {
            "inspect_sender": _inv("Inspect Sender", 10, "Sender Analysis", [
                {"label": "Display name", "value": "Google Drive"},
                {"label": "Sender address", "value": "notify@drive-access-harbor.example"},
            ], "The display name is a brand. The mailbox domain is not a Google domain."),
            "inspect_link": _inv("Inspect Link", 10, "Link Analysis", [
                {"label": "Displayed URL", "value": "https://drive.google.com/"},
                {"label": "Actual destination", "value": "https://drive-google.signin-harbor.example/login"},
            ], "The visible text and the destination host do not match."),
            "inspect_page": _inv("Preview Landing Page", 10, "Page Preview", [
                {"label": "Form fields", "value": "Email, password, and backup codes"},
                {"label": "Certificate name", "value": "signin-harbor.example"},
            ], "A real drive login would not ask for backup codes on an unrelated host."),
            "view_headers": _inv("View Headers", 8, "Message Headers", [
                {"label": "Reply-To", "value": "collect@signin-harbor.example"},
            ], "Replies would leave the company and go to the lookalike host."),
        },
        "decisions": {
            "report_phishing": _dec("Report as Phishing", "correct", 40, "Lookalike page blocked", "The message was quarantined and the lookalike host was added to the block list.", "Quarantine applied"),
            "open_link": _dec("Open Link", "unsafe", -30, "Credentials requested", "Opening the page would present a fake sign-in that collects a password and backup codes.", "User exposed to credential theft"),
            "ignore": _dec("Ignore", "unsafe", -30, "Message still in inbox", "The designer can still open the link during the client review.", "No containment"),
            "forward_team": _dec("Forward to the Design Team", "poor", -15, "More people received the lure", "Forwarding spreads the fake sign-in to the rest of the team.", "Exposure widened"),
        },
        "scene": _scene([
            _n("sender", "Lookalike sender", 8, 18, 8),
            _n("mail", "Mail gateway", 38, 28, 20),
            _n("user", "Lina's laptop", 68, 22, 16),
            _n("page", "Fake login", 78, 62, 28),
        ], ["page", "sender"], {
            "inspect_sender": "sender", "inspect_link": "page", "inspect_page": "page", "view_headers": "mail",
        }),
    },
    "phishing_invoice_attachment": {
        "key": "phishing_invoice_attachment",
        "domain": "phishing",
        "activity_type": "incident",
        "difficulty": "intermediate",
        "environment": "Email Security Console",
        "workspace_type": "email",
        "incident_code": "CQ-PH-003",
        "severity": "HIGH",
        "title": "Malicious invoice attachment",
        "objective": "Treat an unexpected invoice file as untrusted until the sender and file type are verified.",
        "briefing": {
            "employee": "Owen Blake",
            "department": "Accounts payable, Lumen Ledger",
            "subject": "Overdue invoice INV-8841",
            "time": "08:03 AM",
            "summary": "Accounts payable received a vendor invoice they do not recognize. The attachment has not been opened. Decide how to handle the file.",
        },
        "workspace": {
            "from_display": "Northwind Supplies",
            "to": "ap@lumenledger.example",
            "subject": "Overdue invoice INV-8841",
            "time": "Today 07:58",
            "body": "Please pay the attached invoice today to avoid a service interruption.\n\nEnable editing if the document looks blank.",
            "link_display": "Attachment: INV-8841.docm",
        },
        "required_evidence": ["inspect_sender", "inspect_attachment", "check_vendor"],
        "missing_evidence_penalty": -10,
        "investigations": {
            "inspect_sender": _inv("Inspect Sender", 10, "Sender Analysis", [
                {"label": "Sender address", "value": "billing@northwind-supplies.example"},
                {"label": "Known vendor domain", "value": "northwind.example"},
            ], "The company does buy from Northwind, but this domain only looks similar."),
            "inspect_attachment": _inv("Inspect Attachment", 10, "File Analysis", [
                {"label": "File name", "value": "INV-8841.docm"},
                {"label": "File type", "value": "Macro-enabled document"},
            ], "A payment PDF would not need macros. The file asks the user to enable them."),
            "check_vendor": _inv("Check Vendor Record", 10, "Vendor Record", [
                {"label": "Open purchase order", "value": "None for INV-8841"},
                {"label": "Accounts contact", "value": "ap@northwind.example"},
            ], "There is no matching purchase order, and the real accounts address is different."),
            "check_mailbox": _inv("Check Other Mailboxes", 7, "Spread Check", [
                {"label": "Similar messages", "value": "Three more arrived this morning"},
            ], "The same lure reached several payable clerks."),
        },
        "decisions": {
            "quarantine_file": _dec("Quarantine the File", "correct", 40, "Attachment contained", "The macro document was removed from every mailbox that received it.", "File quarantined"),
            "open_attachment": _dec("Open the Attachment", "unsafe", -30, "Macro prompt reached the clerk", "Opening the document would ask the clerk to enable content from an untrusted file.", "Unsafe file handling"),
            "pay_invoice": _dec("Approve Payment", "unsafe", -30, "Payment requested from a fake invoice", "Paying from an unmatched invoice would send funds to the attacker’s instructions.", "Fraud not stopped"),
            "ask_employee_to_check": _dec("Ask the Clerk to Check It", "poor", -10, "User left with the lure", "The clerk still has the macro file and no containment guidance.", "Decision deferred to the target"),
        },
        "scene": _scene([
            _n("vendor", "Lookalike vendor", 10, 20, 10),
            _n("file", "INV-8841.docm", 40, 48, 24),
            _n("ap", "Accounts payable", 72, 24, 14),
            _n("bank", "Payment desk", 78, 68, 8),
        ], ["file"], {
            "inspect_sender": "vendor", "inspect_attachment": "file", "check_vendor": "bank", "check_mailbox": "ap",
        }),
    },
    "phishing_bec_payment": {
        "key": "phishing_bec_payment",
        "domain": "phishing",
        "activity_type": "incident",
        "difficulty": "advanced",
        "environment": "Email Security Console",
        "workspace_type": "email",
        "incident_code": "CQ-PH-004",
        "severity": "HIGH",
        "title": "Urgent executive payment request",
        "objective": "Verify a payment-instruction change out of band before money moves.",
        "briefing": {
            "employee": "Marta Ellis",
            "department": "Finance, Cobalt Ferry",
            "subject": "Wire the deposit today — confidential",
            "time": "04:41 PM",
            "summary": "The finance manager received a message that looks like the CEO asking for a same-day wire. No one has called the CEO yet.",
        },
        "workspace": {
            "from_display": "A. Rahman, CEO",
            "to": "marta.ellis@cobaltferry.example",
            "subject": "Wire the deposit today — confidential",
            "time": "Today 16:36",
            "body": "Marta, I am boarding a flight. Wire the harbor deposit to the new supplier account below. Do not discuss this on chat until it is done.",
            "link_display": "New account ending 4419, Bank of Fiction",
        },
        "required_evidence": ["inspect_sender", "inspect_reply_path", "check_change_policy"],
        "missing_evidence_penalty": -10,
        "investigations": {
            "inspect_sender": _inv("Inspect Sender", 10, "Sender Analysis", [
                {"label": "Display name", "value": "A. Rahman, CEO"},
                {"label": "Sender address", "value": "a.rahman@cobalt-ferry.example"},
            ], "The CEO’s real mailbox is ar@cobaltferry.example. This one adds a hyphen."),
            "inspect_reply_path": _inv("Inspect Reply Path", 10, "Reply Path", [
                {"label": "Reply-To", "value": "rahman.desk@mail-relay.example"},
                {"label": "CEO mailbox login", "value": "No unusual sign-in today"},
            ], "The CEO account itself was not taken over. The request came from a lookalike address."),
            "check_change_policy": _inv("Check Payment Policy", 10, "Payment Policy", [
                {"label": "Account changes", "value": "Require a phone callback to a known number"},
                {"label": "Callback done", "value": "No"},
            ], "A new beneficiary cannot be paid from email instructions alone."),
            "search_thread": _inv("Search Prior Thread", 8, "Thread History", [
                {"label": "Earlier CEO mail", "value": "Last real thread used ar@cobaltferry.example"},
            ], "This message does not continue a genuine thread."),
        },
        "decisions": {
            "callback_and_hold": _dec("Hold the Wire and Call the CEO", "correct", 40, "Wire held", "Finance held the transfer and confirmed by phone that the CEO did not request it.", "Out-of-band check completed"),
            "send_wire": _dec("Send the Wire", "unsafe", -30, "Funds sent to a new account", "The payment would leave using instructions that never passed the callback rule.", "Payment fraud completed"),
            "reply_in_email": _dec("Reply to Confirm", "poor", -10, "Confirmation stayed on the lure", "Replying reaches the lookalike mailbox, which can simply say yes.", "Weak verification"),
            "ignore": _dec("Ignore", "unsafe", -20, "Request still pending", "The urgent message remains, and the flight story pressures Marta to act later.", "No hold placed"),
        },
        "scene": _scene([
            _n("ceo", "Lookalike CEO", 8, 16, 12),
            _n("mail", "Mail gateway", 36, 36, 18),
            _n("finance", "Finance desk", 66, 20, 14),
            _n("bank", "Wire desk", 80, 64, 22),
        ], ["ceo", "bank"], {
            "inspect_sender": "ceo", "inspect_reply_path": "mail", "check_change_policy": "bank", "search_thread": "finance",
        }),
    },
    "password_reuse_review": {
        "key": "password_reuse_review",
        "domain": "password",
        "activity_type": "simulation",
        "difficulty": "intermediate",
        "environment": "Authentication Security Console",
        "workspace_type": "auth",
        "incident_code": "CQ-PW-002",
        "severity": "MEDIUM",
        "title": "Password reuse investigation",
        "objective": "Separate a reused password from a healthy unique credential, then force a reset only where reuse is real.",
        "briefing": {
            "employee": "dev.studio",
            "department": "Engineering, Paper Kite Clinic",
            "subject": "Same password seen on two systems",
            "time": "01:22 PM",
            "summary": "A quarterly credential review suggests one studio account reused a password. Confirm the evidence before you disrupt the team.",
        },
        "workspace": {
            "account": "dev.studio@paperkite.example",
            "failed_attempts": "0 today",
            "alert_time": "01:22 PM",
            "source_ip": "198.51.100.14 (clinic VPN, fictional)",
            "status": "Account ACTIVE",
            "mfa": "Enabled on clinic VPN only",
        },
        "required_evidence": ["compare_hashes", "check_other_systems", "review_mfa"],
        "missing_evidence_penalty": -10,
        "investigations": {
            "compare_hashes": _inv("Compare Password Records", 10, "Credential Comparison", [
                {"label": "Clinic VPN", "value": "Unique salted hash"},
                {"label": "Legacy wiki", "value": "Same password as a personal forum dump (simulated)"},
            ], "The VPN password is unique. The old wiki password matches a public dump."),
            "check_other_systems": _inv("Check Other Systems", 10, "System List", [
                {"label": "Wiki", "value": "Still accepts the reused password"},
                {"label": "Email", "value": "Different password, MFA on"},
            ], "Reuse is limited to the legacy wiki, which is still reachable."),
            "review_mfa": _inv("Review MFA", 10, "MFA Coverage", [
                {"label": "VPN and email", "value": "MFA required"},
                {"label": "Wiki", "value": "Password only"},
            ], "The exposed password protects a system that has no second factor."),
            "ask_user_history": _inv("Ask Account Owner", 7, "Owner Note", [
                {"label": "Owner statement", "value": "Used an old personal password on the wiki years ago"},
            ], "The owner can explain the wiki, not the VPN."),
        },
        "decisions": {
            "reset_wiki_only": _dec("Reset the Wiki Password", "correct", 40, "Reused credential retired", "The wiki password was reset and that login now requires MFA. The healthy VPN password was left alone.", "Targeted reset"),
            "reset_everything": _dec("Reset Every Password", "poor", 10, "Broader reset than the evidence supports", "You disrupted VPN and email even though those secrets were unique and already behind MFA.", "Over-broad reset"),
            "ignore": _dec("Ignore", "unsafe", -30, "Wiki password remains public", "The dumped password still opens the wiki.", "Exposure left in place"),
            "disable_mfa": _dec("Disable MFA to Simplify Login", "unsafe", -30, "Second factor removed", "Removing MFA would make the stronger systems depend on a single secret.", "Protection weakened"),
        },
        "scene": _scene([
            _n("user", "Studio laptop", 12, 24, 10),
            _n("vpn", "Clinic VPN", 40, 18, 22),
            _n("wiki", "Legacy wiki", 70, 30, 16),
            _n("dump", "Public dump", 74, 68, 8),
        ], ["wiki", "dump"], {
            "compare_hashes": "dump", "check_other_systems": "wiki", "review_mfa": "vpn", "ask_user_history": "user",
        }),
    },
    "password_leaked_credentials": {
        "key": "password_leaked_credentials",
        "domain": "password",
        "activity_type": "incident",
        "difficulty": "intermediate",
        "environment": "Authentication Security Console",
        "workspace_type": "auth",
        "incident_code": "CQ-PW-003",
        "severity": "HIGH",
        "title": "Leaked staff credentials",
        "objective": "Contain accounts whose current passwords appear in a fresh leak before those passwords are tried.",
        "briefing": {
            "employee": "12 staff accounts",
            "department": "Harbor & Co. identity team",
            "subject": "Fresh leak includes company email addresses",
            "time": "06:05 AM",
            "summary": "A threat-intel feed lists Harbor mailboxes with passwords. Determine which leaked secrets are still valid, then contain those accounts.",
        },
        "workspace": {
            "account": "12 mailboxes at harborco.example",
            "failed_attempts": "Not started yet",
            "alert_time": "06:05 AM",
            "source_ip": "No attacker login observed",
            "status": "Leak list received",
            "mfa": "Optional for staff mail",
        },
        "required_evidence": ["match_leak", "test_validity", "check_mfa_gap"],
        "missing_evidence_penalty": -10,
        "investigations": {
            "match_leak": _inv("Match the Leak", 10, "Leak Match", [
                {"label": "Rows", "value": "12 company emails, passwords present"},
                {"label": "Age", "value": "Posted overnight (simulated feed)"},
            ], "The addresses belong to current staff, so this is not an old alumni list."),
            "test_validity": _inv("Check If Secrets Still Match", 10, "Validity Check", [
                {"label": "Still valid", "value": "4 mailboxes"},
                {"label": "Already changed", "value": "8 mailboxes"},
            ], "Only four leaked passwords still match current hashes."),
            "check_mfa_gap": _inv("Check MFA Gap", 10, "MFA Gap", [
                {"label": "Valid and no MFA", "value": "4 mailboxes"},
                {"label": "Attacker logins", "value": "None yet"},
            ], "Those four accounts can be opened with the leaked password alone."),
            "notify_owners": _inv("Draft Owner Notice", 7, "Notice Draft", [
                {"label": "Message", "value": "Reset through the company portal, not a link in this alert"},
            ], "Owners need a trusted reset path, not another email link."),
        },
        "decisions": {
            "reset_valid_four": _dec("Force Reset on the Four Valid Accounts", "correct", 40, "Leaked secrets invalidated", "The four matching passwords were expired and MFA enrollment was required. The other eight were already safe.", "Precise containment"),
            "wait_for_login": _dec("Wait for a Suspicious Login", "unsafe", -30, "Valid leaked passwords remain usable", "Waiting gives anyone with the dump a window to sign in first.", "No preventive reset"),
            "reset_entire_company": _dec("Reset Every Employee", "poor", 8, "Company-wide reset", "You expired passwords that the evidence already showed were changed.", "Broader than necessary"),
            "email_the_dump": _dec("Email the Passwords to Staff", "unsafe", -30, "Secrets copied into mail", "Sending the leaked passwords repeats the exposure inside the company.", "Secret handling failure"),
        },
        "scene": _scene([
            _n("feed", "Leak feed", 10, 22, 12),
            _n("dir", "Staff directory", 38, 40, 18),
            _n("mail", "4 open mailboxes", 68, 22, 20),
            _n("idp", "Identity provider", 76, 66, 10),
        ], ["mail", "feed"], {
            "match_leak": "feed", "test_validity": "dir", "check_mfa_gap": "mail", "notify_owners": "idp",
        }),
    },
    "password_weak_admin": {
        "key": "password_weak_admin",
        "domain": "password",
        "activity_type": "incident",
        "difficulty": "advanced",
        "environment": "Authentication Security Console",
        "workspace_type": "auth",
        "incident_code": "CQ-PW-004",
        "severity": "HIGH",
        "title": "Weak administrator password",
        "objective": "Recognize a shared, guessable admin secret and replace it without locking out recovery.",
        "briefing": {
            "employee": "breakglass.admin",
            "department": "IT, Lumen Ledger",
            "subject": "Admin login used a seasonal password",
            "time": "11:48 PM",
            "summary": "The after-hours change window used a shared administrator password. Investigate how it is stored and who can use it.",
        },
        "workspace": {
            "account": "breakglass.admin",
            "failed_attempts": "2 guesses, then success",
            "alert_time": "11:48 PM",
            "source_ip": "203.0.113.40 (office jump host, fictional)",
            "status": "Privileged session OPEN",
            "mfa": "Bypassed by a shared emergency note",
        },
        "required_evidence": ["read_password_note", "list_who_knows", "review_session"],
        "missing_evidence_penalty": -10,
        "investigations": {
            "read_password_note": _inv("Read the Emergency Note", 10, "Shared Secret", [
                {"label": "Password pattern", "value": "Company name plus the current season"},
                {"label": "Stored in", "value": "A chat message pinned for the whole IT channel"},
            ], "The emergency password is guessable and visible to everyone in the channel."),
            "list_who_knows": _inv("List Who Can See It", 10, "Exposure", [
                {"label": "Channel members", "value": "18 people, including two contractors"},
                {"label": "Unique owner", "value": "None — the password is shared"},
            ], "A break-glass account needs a sealed secret, not a shared seasonal word."),
            "review_session": _inv("Review the Open Session", 10, "Session Review", [
                {"label": "Actions so far", "value": "Listed servers, no changes yet"},
                {"label": "Operator", "value": "Contractor laptop on the jump host"},
            ], "The session is real work, but it proves the weak shared password is in active use."),
            "check_vault": _inv("Check the Secret Vault", 8, "Vault Status", [
                {"label": "Break-glass entry", "value": "Missing"},
            ], "There is no sealed copy to fall back on after a reset."),
        },
        "decisions": {
            "seal_and_rotate": _dec("Rotate Into a Sealed Vault", "correct", 40, "Shared admin password retired", "The seasonal password was replaced, stored in the vault, and the open session was re-authenticated.", "Privileged secret sealed"),
            "leave_until_morning": _dec("Leave It Until Morning", "unsafe", -30, "Guessable admin password stays valid", "Anyone who saw the pinned note can open the admin account overnight.", "Exposure continues"),
            "post_new_password": _dec("Post a Stronger Password in Chat", "poor", 5, "New secret shared again", "A stronger word still fails once the whole channel can read it.", "Same handling mistake"),
            "delete_admin": _dec("Delete the Admin Account", "poor", -10, "Recovery path removed", "Deleting break-glass during a change window removes emergency access without a replacement.", "Recovery broken"),
        },
        "scene": _scene([
            _n("chat", "IT chat note", 12, 20, 8),
            _n("admin", "breakglass.admin", 42, 36, 24),
            _n("jump", "Jump host", 70, 18, 14),
            _n("vault", "Secret vault", 76, 66, 18),
        ], ["chat", "admin"], {
            "read_password_note": "chat", "list_who_knows": "admin", "review_session": "jump", "check_vault": "vault",
        }),
    },
    "network_port_scan": {
        "key": "network_port_scan",
        "domain": "network",
        "activity_type": "simulation",
        "difficulty": "intermediate",
        "environment": "Network Security Monitor",
        "workspace_type": "network",
        "incident_code": "CQ-NW-002",
        "severity": "MEDIUM",
        "title": "Port scan response",
        "objective": "Tell a broad external scan from an authorized internal inventory scan before blocking the wrong source.",
        "briefing": {
            "employee": "Edge firewall",
            "department": "Network operations, Cobalt Ferry",
            "subject": "Many closed ports contacted",
            "time": "09:12 AM",
            "summary": "The firewall logged a sweep of closed ports. Identify who scanned, then choose a response that matches the evidence.",
        },
        "workspace": {
            "topology": [
                {"name": "Internet", "alert": True},
                {"name": "Firewall", "alert": True},
                {"name": "WEB-SERVER", "alert": False},
                {"name": "SCAN-HOST", "alert": False},
            ],
            "alert_banner": "Sequential probes against closed ports",
            "bytes_out": "Low volume — probes only",
        },
        "required_evidence": ["view_scan_pattern", "identify_source", "check_change_ticket"],
        "missing_evidence_penalty": -10,
        "investigations": {
            "view_scan_pattern": _inv("View Scan Pattern", 10, "Scan Pattern", [
                {"label": "Pattern", "value": "Ports 1–1024, one host, then the next"},
                {"label": "Hits", "value": "Closed ports only, no successful session"},
            ], "This is reconnaissance, not an active transfer."),
            "identify_source": _inv("Identify Source", 10, "Source", [
                {"label": "External IP", "value": "198.51.100.80 (fictional)"},
                {"label": "Internal scanner", "value": "SCAN-HOST is idle"},
            ], "The sweep came from outside. The approved inventory scanner did not run."),
            "check_change_ticket": _inv("Check Change Ticket", 10, "Change Record", [
                {"label": "Approved scan today", "value": "None"},
                {"label": "Vendor window", "value": "Next Tuesday"},
            ], "No one inside the company authorized this sweep."),
            "sample_payload": _inv("Sample a Probe", 7, "Probe Sample", [
                {"label": "Payload", "value": "Empty SYN packets"},
            ], "The probes do not carry a file or a login."),
        },
        "decisions": {
            "block_external_ip": _dec("Block the External Source", "correct", 40, "Scan source blocked", "The firewall dropped 198.51.100.80. Internal systems were not blamed.", "External source blocked"),
            "isolate_web_server": _dec("Isolate the Web Server", "poor", 5, "Public site taken down", "The web server never accepted a session. Isolating it causes an outage without stopping the scanner.", "Wrong asset contained"),
            "ignore": _dec("Ignore", "unsafe", -20, "Sweep continues", "The external host can keep mapping closed and open ports.", "Recon not stopped"),
            "block_internal_scanner": _dec("Disable SCAN-HOST", "poor", -10, "Inventory scanner disabled", "SCAN-HOST was idle. Disabling it removes a legitimate tool.", "Wrong source blamed"),
        },
        "scene": _scene([
            _n("internet", "External scanner", 8, 18, 10),
            _n("fw", "Firewall", 40, 34, 22),
            _n("web", "Web server", 72, 20, 12),
            _n("scan", "SCAN-HOST", 74, 66, 8),
        ], ["internet"], {
            "view_scan_pattern": "fw", "identify_source": "internet", "check_change_ticket": "scan", "sample_payload": "web",
        }),
    },
    "network_dns_beacon": {
        "key": "network_dns_beacon",
        "domain": "network",
        "activity_type": "incident",
        "difficulty": "intermediate",
        "environment": "Network Security Monitor",
        "workspace_type": "network",
        "incident_code": "CQ-NW-003",
        "severity": "HIGH",
        "title": "DNS beacon investigation",
        "objective": "Spot a workstation using DNS queries as a hidden signal and contain that host, not all DNS.",
        "briefing": {
            "employee": "WORKSTATION-12",
            "department": "Clinic reception, Paper Kite",
            "subject": "Repeating lookups to one unusual name",
            "time": "02:40 AM",
            "summary": "DNS logs show WORKSTATION-12 asking for a long, repeating name every minute. Reception is closed.",
        },
        "workspace": {
            "topology": [
                {"name": "Internet", "alert": False},
                {"name": "Firewall", "alert": False},
                {"name": "DNS", "alert": True},
                {"name": "WORKSTATION-12", "alert": True},
            ],
            "alert_banner": "Regular DNS queries to an unapproved name",
            "bytes_out": "Small queries, every 60 seconds",
        },
        "required_evidence": ["read_dns_log", "inspect_host", "compare_baseline"],
        "missing_evidence_penalty": -10,
        "investigations": {
            "read_dns_log": _inv("Read DNS Log", 10, "DNS Log", [
                {"label": "Query", "value": "a9f3.update.paperkite-sync.example"},
                {"label": "Interval", "value": "Every 60 seconds since 02:11"},
            ], "Business apps do not beacon a single unapproved name every minute."),
            "inspect_host": _inv("Inspect Workstation", 10, "Host", [
                {"label": "Host", "value": "WORKSTATION-12, reception desk"},
                {"label": "Process", "value": "helper-update.exe, not installed by IT"},
            ], "An unapproved process is making the lookups while the desk is empty."),
            "compare_baseline": _inv("Compare Baseline", 10, "Baseline", [
                {"label": "Other reception PCs", "value": "No queries to that name"},
                {"label": "Corporate DNS", "value": "Healthy"},
            ], "The resolver is fine. One host is the outlier."),
            "check_answers": _inv("Check DNS Answers", 8, "Answers", [
                {"label": "Answer", "value": "TXT records with short random text"},
            ], "The replies look like a signal channel, not a website lookup."),
        },
        "decisions": {
            "isolate_workstation": _dec("Isolate WORKSTATION-12", "correct", 40, "Beacon host isolated", "The reception PC was removed from the network. DNS for the rest of the clinic stayed up.", "Host contained"),
            "block_all_dns": _dec("Block All DNS", "poor", -10, "Clinic name resolution stopped", "Blocking every lookup takes down legitimate access and is broader than the one host.", "Over-blocking"),
            "ignore_until_open": _dec("Wait Until Reception Opens", "unsafe", -30, "Beacon continues overnight", "The unapproved process keeps signaling for hours.", "Delay"),
            "reimage_dns_server": _dec("Rebuild the DNS Server", "poor", 0, "Healthy resolver disrupted", "The log shows the resolver is doing its job. Rebuilding it does not remove the program.", "Wrong system"),
        },
        "scene": _scene([
            _n("pc", "WORKSTATION-12", 10, 28, 14),
            _n("dns", "DNS resolver", 42, 22, 20),
            _n("name", "Unusual name", 72, 30, 16),
            _n("net", "Rest of clinic", 70, 68, 8),
        ], ["pc", "name"], {
            "read_dns_log": "dns", "inspect_host": "pc", "compare_baseline": "net", "check_answers": "name",
        }),
    },
    "network_lateral_move": {
        "key": "network_lateral_move",
        "domain": "network",
        "activity_type": "incident",
        "difficulty": "advanced",
        "environment": "Network Security Monitor",
        "workspace_type": "network",
        "incident_code": "CQ-NW-004",
        "severity": "HIGH",
        "title": "Lateral movement",
        "objective": "Follow an admin login that jumps from a compromised PC toward a server, and cut that path.",
        "briefing": {
            "employee": "FILE-SERVER",
            "department": "Harbor & Co. IT",
            "subject": "Admin logon from a reception PC",
            "time": "07:55 PM",
            "summary": "FILE-SERVER accepted an administrator logon from WORKSTATION-03. That PC does not administer servers.",
        },
        "workspace": {
            "topology": [
                {"name": "WORKSTATION-03", "alert": True},
                {"name": "Firewall", "alert": False},
                {"name": "FILE-SERVER", "alert": True},
                {"name": "DATABASE", "alert": False},
            ],
            "alert_banner": "Privileged logon from an unexpected workstation",
            "bytes_out": "Admin session, directory listing started",
        },
        "required_evidence": ["trace_logon", "check_admin_group", "inspect_workstation"],
        "missing_evidence_penalty": -10,
        "investigations": {
            "trace_logon": _inv("Trace the Logon", 10, "Logon Path", [
                {"label": "Source", "value": "WORKSTATION-03"},
                {"label": "Account", "value": "svc.backup, interactive"},
            ], "A service account used for backups was used interactively from a user PC."),
            "check_admin_group": _inv("Check Admin Rights", 10, "Rights", [
                {"label": "svc.backup", "value": "Local admin on FILE-SERVER"},
                {"label": "Normal use", "value": "Scheduled task from BACKUP-01 only"},
            ], "The account is powerful, but this is not the host that should use it."),
            "inspect_workstation": _inv("Inspect WORKSTATION-03", 10, "Source PC", [
                {"label": "User present", "value": "No — desk empty"},
                {"label": "New tool", "value": "Remote admin utility saved this afternoon"},
            ], "Someone left a remote-admin tool on an empty desk PC and used it to reach the file server."),
            "check_database": _inv("Check the Database", 8, "Database", [
                {"label": "New logons", "value": "None"},
            ], "The jump has reached the file server only. The database is not in this path yet."),
        },
        "decisions": {
            "cut_path": _dec("Disable the Session and the Desk PC", "correct", 40, "Jump path cut", "The file-server session was revoked and WORKSTATION-03 was isolated. BACKUP-01 was left for the scheduled job.", "Lateral path contained"),
            "shut_down_database": _dec("Shut Down the Database", "poor", 0, "Uninvolved system taken offline", "The database shows no new logon. Shutting it down creates an outage beside the real path.", "Wrong target"),
            "watch_only": _dec("Keep Watching", "unsafe", -30, "Admin session remains", "The unexpected admin session can keep listing and copying files.", "No containment"),
            "reset_every_password": _dec("Reset Every Password in the Company", "poor", 8, "Broad reset, path still open", "A company-wide reset does not remove the tool already running on the desk PC.", "Source left online"),
        },
        "scene": _scene([
            _n("pc", "WORKSTATION-03", 8, 26, 12),
            _n("file", "FILE-SERVER", 46, 20, 24),
            _n("backup", "BACKUP-01", 46, 68, 8),
            _n("db", "Database", 78, 30, 14),
        ], ["pc", "file"], {
            "trace_logon": "file", "check_admin_group": "backup", "inspect_workstation": "pc", "check_database": "db",
        }),
    },
    "crypto_plaintext_secret": {
        "key": "crypto_plaintext_secret",
        "domain": "cryptography",
        "activity_type": "simulation",
        "difficulty": "intermediate",
        "environment": "Secure Communication Audit Console",
        "workspace_type": "crypto",
        "incident_code": "CQ-CR-002",
        "severity": "HIGH",
        "title": "Exposed plaintext secret",
        "objective": "Find a live API secret stored in plaintext and rotate it after removing the copy.",
        "briefing": {
            "employee": "Partner API",
            "department": "Engineering, Cobalt Ferry",
            "subject": "Secret visible in a shared note",
            "time": "03:18 PM",
            "summary": "A code review found a partner API secret written in a shared note. Decide what must happen to the secret and the note.",
        },
        "workspace": {
            "system_name": "Ferry Partner API",
            "claim": "The note is private to engineering",
            "channel": "Shared engineering note",
            "data_type": "Live API secret",
        },
        "required_evidence": ["read_exposure", "check_secret_use", "see_who_can_read"],
        "missing_evidence_penalty": -10,
        "investigations": {
            "read_exposure": _inv("Read the Exposure", 10, "Exposure", [
                {"label": "Note text", "value": "The full API secret is written out"},
                {"label": "Protection", "value": "No encryption on the note"},
            ], "A secret in plaintext is exposed to every reader of that note."),
            "check_secret_use": _inv("Check Where It Works", 10, "Secret Use", [
                {"label": "Status", "value": "Still accepted by the partner API"},
                {"label": "Last use", "value": "This morning’s invoice job"},
            ], "Rotating the note alone is not enough while the partner still accepts this secret."),
            "see_who_can_read": _inv("See Who Can Read It", 10, "Readers", [
                {"label": "Access", "value": "All 26 engineers and two guests"},
            ], "The note is wider than the people who run the invoice job."),
            "search_copies": _inv("Search for Copies", 8, "Copies", [
                {"label": "Other copies", "value": "One more in a ticket comment"},
            ], "A second plaintext copy exists."),
        },
        "decisions": {
            "rotate_and_purge": _dec("Revoke the Secret and Delete the Copies", "correct", 40, "Plaintext secret retired", "The partner key was rotated and both plaintext copies were removed.", "Secret rotated"),
            "hide_the_note": _dec("Restrict the Note Only", "poor", 8, "Live secret still valid", "Fewer people can open the note, but the old secret still works and the ticket copy remains.", "Incomplete cleanup"),
            "leave_it": _dec("Leave It for the Next Review", "unsafe", -30, "Plaintext secret stays live", "Anyone who already saw the note can call the partner API.", "Exposure accepted"),
            "email_secret_to_partner": _dec("Email the Secret to the Partner", "unsafe", -30, "Secret copied into mail", "Emailing the value creates another plaintext copy.", "Exposure widened"),
        },
        "scene": _scene([
            _n("note", "Shared note", 12, 22, 10),
            _n("ticket", "Ticket copy", 40, 64, 8),
            _n("api", "Partner API", 70, 24, 22),
            _n("job", "Invoice job", 72, 66, 12),
        ], ["note", "ticket"], {
            "read_exposure": "note", "check_secret_use": "api", "see_who_can_read": "note", "search_copies": "ticket",
        }),
    },
    "crypto_key_storage": {
        "key": "crypto_key_storage",
        "domain": "cryptography",
        "activity_type": "incident",
        "difficulty": "intermediate",
        "environment": "Secure Communication Audit Console",
        "workspace_type": "crypto",
        "incident_code": "CQ-CR-003",
        "severity": "HIGH",
        "title": "Insecure key storage",
        "objective": "Separate an encryption key from the files it protects.",
        "briefing": {
            "employee": "Records archive",
            "department": "Compliance, Paper Kite Clinic",
            "subject": "Archive key sits in the same folder",
            "time": "11:27 AM",
            "summary": "Patient-export files are encrypted, but staff found the key file beside them. Review the storage and correct it.",
        },
        "workspace": {
            "system_name": "Clinic records archive",
            "claim": "The exports are encrypted, so the folder is safe",
            "channel": "Department file share",
            "data_type": "Encrypted patient exports (fictional)",
        },
        "required_evidence": ["locate_key", "check_folder_acl", "identify_algorithm"],
        "missing_evidence_penalty": -10,
        "investigations": {
            "locate_key": _inv("Locate the Key", 10, "Key Location", [
                {"label": "Key file", "value": "archive.key in the same folder as the exports"},
                {"label": "Passphrase", "value": "Written in a README next to it"},
            ], "Anyone who can download the exports can also download the key and passphrase."),
            "check_folder_acl": _inv("Check Folder Access", 10, "Access", [
                {"label": "Read access", "value": "Entire compliance department"},
            ], "Encryption does not help when the whole department can read the key."),
            "identify_algorithm": _inv("Identify the Algorithm", 10, "Algorithm", [
                {"label": "Cipher", "value": "A current authenticated cipher"},
                {"label": "Problem", "value": "Key storage, not the cipher choice"},
            ], "The cipher is fine. The key handling is the weakness."),
            "check_backups": _inv("Check Backups", 8, "Backups", [
                {"label": "Nightly copy", "value": "Includes archive.key"},
            ], "The backup copied the same mistake."),
        },
        "decisions": {
            "move_key": _dec("Move the Key to a Vault and Rotate It", "correct", 40, "Key separated from data", "The key was rotated into the vault and removed from the share and the backup set.", "Storage corrected"),
            "zip_the_folder": _dec("Zip the Folder", "poor", 0, "Key still beside the data", "A zip file stores the key and the exports together.", "No real separation"),
            "approve": _dec("Approve the Folder", "unsafe", -30, "Key remains with the files", "The department can still open every export.", "Insecure storage accepted"),
            "stop_encrypting": _dec("Stop Encrypting", "unsafe", -30, "Protection removed", "Removing encryption leaves the exports readable with no key required.", "Weaker than before"),
        },
        "scene": _scene([
            _n("files", "Encrypted exports", 14, 24, 12),
            _n("key", "archive.key", 42, 28, 26),
            _n("share", "Department share", 70, 20, 10),
            _n("vault", "Key vault", 74, 66, 18),
        ], ["key"], {
            "locate_key": "key", "check_folder_acl": "share", "identify_algorithm": "files", "check_backups": "share",
        }),
    },
    "crypto_tls_problem": {
        "key": "crypto_tls_problem",
        "domain": "cryptography",
        "activity_type": "incident",
        "difficulty": "advanced",
        "environment": "Secure Communication Audit Console",
        "workspace_type": "crypto",
        "incident_code": "CQ-CR-004",
        "severity": "HIGH",
        "title": "Certificate and TLS problem",
        "objective": "Decide what a name mismatch and an expired certificate mean before telling users to click through.",
        "briefing": {
            "employee": "Patient portal",
            "department": "Paper Kite Clinic",
            "subject": "Browsers warn on the portal",
            "time": "08:50 AM",
            "summary": "Staff say the patient portal shows a certificate warning. Patients have been told to continue anyway. Investigate the certificate before the clinic opens the doors.",
        },
        "workspace": {
            "system_name": "portal.paperkite.example",
            "claim": "The warning is a browser glitch",
            "channel": "Public HTTPS portal",
            "data_type": "Appointment sign-in",
        },
        "required_evidence": ["read_certificate", "compare_name", "check_expiry"],
        "missing_evidence_penalty": -10,
        "investigations": {
            "read_certificate": _inv("Read the Certificate", 10, "Certificate", [
                {"label": "Subject", "value": "portal.paper-kite.example"},
                {"label": "Issuer", "value": "A public practice CA (simulated)"},
            ], "The certificate is for a hyphenated name, not the name patients type."),
            "compare_name": _inv("Compare the Name", 10, "Name Check", [
                {"label": "Site patients use", "value": "portal.paperkite.example"},
                {"label": "Certificate name", "value": "portal.paper-kite.example"},
            ], "The names differ. A warning here is a real mismatch, not a glitch."),
            "check_expiry": _inv("Check Expiry", 10, "Dates", [
                {"label": "Not after", "value": "Yesterday"},
                {"label": "Replacement", "value": "Ordered, not installed"},
            ], "The presented certificate is also expired."),
            "see_user_advice": _inv("See the Advice Staff Gave", 8, "User Advice", [
                {"label": "Front desk script", "value": "Click continue so the queue keeps moving"},
            ], "Patients are being trained to ignore a certificate warning."),
        },
        "decisions": {
            "install_and_stop_bypass": _dec("Install the Matching Certificate and Stop the Bypass", "correct", 40, "Portal identity restored", "The new certificate matches the real name, and staff stopped telling patients to click through.", "TLS corrected"),
            "tell_users_continue": _dec("Tell Users to Continue", "unsafe", -30, "Warning bypass remains the procedure", "Patients will accept the next warning too, including a fake portal.", "Unsafe user guidance"),
            "turn_off_https": _dec("Turn Off HTTPS", "unsafe", -30, "Sign-in sent in clear text", "Removing TLS avoids the warning by exposing the appointment sign-in.", "Protection removed"),
            "wait_for_vendor": _dec("Wait Without a Change", "poor", -5, "Expired mismatch stays up", "The doors open while the wrong, expired certificate is still presented.", "Known problem left in place"),
        },
        "scene": _scene([
            _n("patient", "Patient browser", 10, 24, 10),
            _n("portal", "Portal", 44, 22, 20),
            _n("cert", "Wrong certificate", 72, 28, 24),
            _n("desk", "Front desk", 70, 68, 8),
        ], ["cert"], {
            "read_certificate": "cert", "compare_name": "portal", "check_expiry": "cert", "see_user_advice": "desk",
        }),
    },
    "osint_domain_case": {
        "key": "osint_domain_case",
        "domain": "osint",
        "activity_type": "simulation",
        "difficulty": "intermediate",
        "environment": "Investigation Workspace",
        "workspace_type": "osint",
        "incident_code": "CQ-OS-002",
        "severity": "MEDIUM",
        "title": "Domain investigation",
        "objective": "Use public domain records to test a claim, and stop when those records do not support it.",
        "briefing": {
            "employee": "Trust desk",
            "department": "Harbor & Co.",
            "subject": "Is this new shop our supplier?",
            "time": "02:05 PM",
            "summary": "A buyer thinks shop.harbor-goods.example is the company’s real supplier site. Check public domain facts only.",
        },
        "workspace": {
            "case_name": "CASE-OSINT-502",
            "subject_handle": "shop.harbor-goods.example",
            "claim": "This domain is the official Harbor supplier store.",
            "rule": "Public registration and site facts only. Do not contact real people.",
        },
        "required_evidence": ["lookup_domain", "compare_official", "review_page"],
        "missing_evidence_penalty": -10,
        "investigations": {
            "lookup_domain": _inv("Look Up the Domain", 10, "Domain Record", [
                {"label": "Registered", "value": "4 days ago"},
                {"label": "Registrant", "value": "Privacy service, no company name"},
            ], "A four-day-old domain is a weak match for a long-running supplier."),
            "compare_official": _inv("Compare the Official Site", 10, "Official Site", [
                {"label": "Known supplier site", "value": "supply.harborco.example"},
                {"label": "Age", "value": "6 years"},
            ], "The company already publishes a different, older supplier hostname."),
            "review_page": _inv("Review the Public Page", 10, "Page Notes", [
                {"label": "Content", "value": "Stock photos and a copied about paragraph"},
                {"label": "Checkout", "value": "Asks for a company login"},
            ], "The page imitates the brand and asks for a login the real supplier does not use."),
            "check_certificates": _inv("Check the Certificate Name", 7, "Certificate", [
                {"label": "Name", "value": "shop.harbor-goods.example only"},
            ], "The certificate matches the new host, not the official supplier host."),
        },
        "decisions": {
            "report_not_official": _dec("Report: Not the Official Domain", "correct", 40, "Claim rejected with sources", "You documented that the new domain is not the known supplier site.", "Supported finding"),
            "confirm_official": _dec("Confirm It Is Official", "unsafe", -30, "False confirmation", "Calling the new shop official would send buyers to a login the company does not run.", "Unsupported conclusion"),
            "close_no_notes": _dec("Close Without Notes", "poor", -10, "No record of the comparison", "The next buyer will have to rediscover the official hostname.", "Poor case notes"),
            "demand_private_whois": _dec("Demand Private Registration Data", "unsafe", -20, "Out of scope", "This exercise uses public records only.", "Scope exceeded"),
        },
        "scene": _scene([
            _n("shop", "New shop domain", 12, 22, 12),
            _n("official", "Official supplier", 44, 26, 18),
            _n("page", "Copied page", 74, 22, 14),
            _n("buyer", "Buyer", 70, 66, 8),
        ], ["shop"], {
            "lookup_domain": "shop", "compare_official": "official", "review_page": "page", "check_certificates": "shop",
        }),
    },
    "osint_exposed_staff": {
        "key": "osint_exposed_staff",
        "domain": "osint",
        "activity_type": "incident",
        "difficulty": "intermediate",
        "environment": "Investigation Workspace",
        "workspace_type": "osint",
        "incident_code": "CQ-OS-003",
        "severity": "MEDIUM",
        "title": "Exposed employee information",
        "objective": "Judge a public staff list by what it actually reveals, then recommend removal of the sensitive fields.",
        "briefing": {
            "employee": "Public careers page",
            "department": "Lumen Ledger",
            "subject": "A spreadsheet of staff is linked from the blog",
            "time": "09:40 AM",
            "summary": "Someone found a public spreadsheet linked from an old blog post. Determine which fields are exposed before you write the finding.",
        },
        "workspace": {
            "case_name": "CASE-OSINT-518",
            "subject_handle": "blog.lumenledger.example/staff-export",
            "claim": "The file publishes private employee records.",
            "rule": "Review the public file only. Do not enrich it with outside personal data.",
        },
        "required_evidence": ["open_public_file", "classify_columns", "find_link_source"],
        "missing_evidence_penalty": -10,
        "investigations": {
            "open_public_file": _inv("Open the Public File", 10, "Public File", [
                {"label": "Rows", "value": "40 fictional staff names and job titles"},
                {"label": "Also included", "value": "Direct dials and badge numbers"},
            ], "Names and titles may be public on purpose. Direct dials and badge numbers were not meant for the blog."),
            "classify_columns": _inv("Classify the Columns", 10, "Column Review", [
                {"label": "Expected public", "value": "Name, role, office city"},
                {"label": "Not for publication", "value": "Direct dial, badge number"},
            ], "The sensitive part is specific columns, not the entire staff directory."),
            "find_link_source": _inv("Find the Link Source", 10, "Link Source", [
                {"label": "Posted from", "value": "A 2022 recruiting blog post"},
                {"label": "Still linked", "value": "Yes, no login required"},
            ], "An old recruiting post still exposes the file."),
            "check_freshness": _inv("Check Freshness", 7, "Freshness", [
                {"label": "File date", "value": "Updated last week"},
            ], "This is not a forgotten stale copy. It is still being replaced."),
        },
        "decisions": {
            "remove_sensitive_columns": _dec("Recommend Removing Dials and Badge Numbers", "correct", 40, "Exposure scoped correctly", "You asked the site owner to take down the direct dials and badge numbers while keeping the public directory fields.", "Precise recommendation"),
            "publish_more": _dec("Add Home Addresses to Help Verification", "unsafe", -30, "Exposure expanded", "Adding more personal fields would make the public file worse.", "Wrong direction"),
            "ignore": _dec("Ignore", "unsafe", -20, "Dials and badge numbers stay public", "The file remains linked from the blog.", "No takedown"),
            "declare_whole_file_secret": _dec("Declare Every Name Secret", "poor", 5, "Finding overstates the file", "Job titles on a careers page are not the same as badge numbers. The recommendation is too broad to act on cleanly.", "Imprecise finding"),
        },
        "scene": _scene([
            _n("blog", "Old blog post", 10, 20, 10),
            _n("file", "Staff spreadsheet", 42, 32, 20),
            _n("dials", "Direct dials", 72, 18, 16),
            _n("roles", "Public roles", 72, 66, 8),
        ], ["file", "dials"], {
            "open_public_file": "file", "classify_columns": "dials", "find_link_source": "blog", "check_freshness": "roles",
        }),
    },
    "osint_metadata_case": {
        "key": "osint_metadata_case",
        "domain": "osint",
        "activity_type": "incident",
        "difficulty": "advanced",
        "environment": "Investigation Workspace",
        "workspace_type": "osint",
        "incident_code": "CQ-OS-004",
        "severity": "MEDIUM",
        "title": "Metadata and infrastructure footprint",
        "objective": "Read file metadata and hosting clues without treating them as proof of who wrote a document.",
        "briefing": {
            "employee": "Incident mailbox",
            "department": "Cobalt Ferry trust team",
            "subject": "A public PDF claims to be an internal memo",
            "time": "05:12 PM",
            "summary": "A public PDF says it is an internal Cobalt Ferry memo. Use its metadata and hosting footprint to test that claim.",
        },
        "workspace": {
            "case_name": "CASE-OSINT-530",
            "subject_handle": "files.relay-docs.example/memo.pdf",
            "claim": "Metadata proves the CEO wrote this memo.",
            "rule": "Public file metadata and hosting only. Do not identify a real person.",
        },
        "required_evidence": ["read_metadata", "inspect_host", "compare_brand_assets"],
        "missing_evidence_penalty": -10,
        "investigations": {
            "read_metadata": _inv("Read Metadata", 10, "PDF Metadata", [
                {"label": "Author field", "value": "Admin"},
                {"label": "Created with", "value": "A consumer PDF tool"},
                {"label": "Company property", "value": "No internal template ID"},
            ], "The author field is a generic word. It does not identify the CEO."),
            "inspect_host": _inv("Inspect Hosting", 10, "Hosting", [
                {"label": "Host", "value": "files.relay-docs.example"},
                {"label": "Company sites", "value": "cobaltferry.example only"},
            ], "The file is hosted outside the company’s known sites."),
            "compare_brand_assets": _inv("Compare Brand Assets", 10, "Brand Comparison", [
                {"label": "Logo in PDF", "value": "Low-resolution copy"},
                {"label": "Footer address", "value": "Does not match the published office address"},
            ], "The document imitates the brand and gets public facts wrong."),
            "timeline": _inv("Check Dates", 8, "Dates", [
                {"label": "PDF created", "value": "Yesterday"},
                {"label": "Claimed memo date", "value": "Last year"},
            ], "The file was created long after the date printed on the memo."),
        },
        "decisions": {
            "report_unreliable": _dec("Report: Claim Is Not Supported", "correct", 40, "Metadata kept in proportion", "You reported that generic metadata and outside hosting do not prove who wrote the memo.", "Careful finding"),
            "name_the_ceo": _dec("Name the CEO as the Author", "unsafe", -30, "Person named from a generic field", "The author field says Admin. Naming the CEO overclaims the evidence.", "Unsafe attribution"),
            "delete_public_web": _dec("Take Down Unrelated Public Sites", "poor", -10, "Action misses the host", "The PDF is on relay-docs.example, not on the company’s own sites.", "Wrong infrastructure"),
            "close_no_notes": _dec("Close Without Notes", "poor", -10, "No record", "The next analyst cannot see why the CEO claim failed.", "Poor documentation"),
        },
        "scene": _scene([
            _n("pdf", "Public PDF", 12, 24, 14),
            _n("meta", "Author: Admin", 42, 20, 18),
            _n("host", "Outside host", 72, 28, 16),
            _n("brand", "Brand facts", 68, 68, 8),
        ], ["pdf", "host"], {
            "read_metadata": "meta", "inspect_host": "host", "compare_brand_assets": "brand", "timeline": "pdf",
        }),
    },
}
