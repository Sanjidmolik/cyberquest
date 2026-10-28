"""
Rule-based career recommendation, skill-gap analysis and learning roadmap.
No external APIs. All logic is deterministic from the user's submitted inputs.
"""

# Required skills per career role (skill slug → minimum level 1-5)
ROLES = {
    "Penetration Tester": {
        "description": "Simulate real-world attacks to find weaknesses before adversaries do.",
        "skills_required": {
            "networking": 3, "linux": 3, "web_security": 3,
            "python": 2, "cryptography": 2,
        },
        "certifications": ["CEH", "OSCP", "CompTIA PenTest+"],
        "avg_salary": "£40 000–£65 000",
    },
    "SOC Analyst": {
        "description": "Monitor, detect and respond to security incidents in real time.",
        "skills_required": {
            "networking": 2, "siem": 2, "incident_response": 2,
            "log_analysis": 2, "threat_intel": 1,
        },
        "certifications": ["CompTIA Security+", "SC-200", "Blue Team Labs"],
        "avg_salary": "£28 000–£48 000",
    },
    "Digital Forensics Investigator": {
        "description": "Recover and analyse digital evidence for incidents and legal proceedings.",
        "skills_required": {
            "forensics": 3, "windows": 2, "linux": 2,
            "log_analysis": 2, "evidence_handling": 2,
        },
        "certifications": ["EnCE", "GCFE", "CHFI"],
        "avg_salary": "£32 000–£55 000",
    },
    "Security Engineer": {
        "description": "Design and build secure systems, infrastructure and pipelines.",
        "skills_required": {
            "networking": 3, "cloud": 2, "scripting": 3,
            "iam": 2, "devops": 2,
        },
        "certifications": ["AWS Security", "CISSP", "CCSP"],
        "avg_salary": "£45 000–£75 000",
    },
    "Cryptography Specialist": {
        "description": "Implement and audit cryptographic protocols and key management systems.",
        "skills_required": {
            "mathematics": 4, "cryptography": 4,
            "python": 3, "protocols": 3,
        },
        "certifications": ["IACR courses", "Applied Cryptography (Coursera)"],
        "avg_salary": "£50 000–£80 000",
    },
    "OSINT Analyst": {
        "description": "Gather and verify open-source intelligence for investigations and threat research.",
        "skills_required": {
            "research": 3, "data_analysis": 2,
            "social_engineering_awareness": 2, "reporting": 2,
        },
        "certifications": ["OSINT Framework training", "GEOINT certification"],
        "avg_salary": "£30 000–£50 000",
    },
    "Malware Analyst": {
        "description": "Reverse-engineer malicious software to understand and counter threats.",
        "skills_required": {
            "assembly": 3, "python": 3, "linux": 3,
            "reverse_engineering": 3, "forensics": 2,
        },
        "certifications": ["GREM", "GCIH", "Malware Unicorn courses"],
        "avg_salary": "£40 000–£68 000",
    },
    "Cybersecurity Consultant": {
        "description": "Advise organisations on risk, compliance and security strategy.",
        "skills_required": {
            "risk_management": 3, "communication": 3,
            "networking": 2, "compliance": 3,
        },
        "certifications": ["CISM", "CRISC", "ISO 27001 Lead Auditor"],
        "avg_salary": "£45 000–£80 000",
    },
}

# Learner-friendly skill names
SKILL_LABELS = {
    "networking": "Networking",
    "linux": "Linux",
    "web_security": "Web Security",
    "python": "Python / Scripting",
    "cryptography": "Cryptography",
    "siem": "SIEM / Log Platforms",
    "incident_response": "Incident Response",
    "log_analysis": "Log Analysis",
    "threat_intel": "Threat Intelligence",
    "forensics": "Digital Forensics",
    "windows": "Windows Administration",
    "evidence_handling": "Evidence Handling",
    "cloud": "Cloud Security",
    "scripting": "Scripting / Automation",
    "iam": "Identity & Access Management",
    "devops": "DevSecOps",
    "mathematics": "Mathematics",
    "protocols": "Cryptographic Protocols",
    "research": "Research Methods",
    "data_analysis": "Data Analysis",
    "social_engineering_awareness": "Social Engineering Awareness",
    "reporting": "Technical Reporting",
    "assembly": "Assembly Language",
    "reverse_engineering": "Reverse Engineering",
    "risk_management": "Risk Management",
    "communication": "Business Communication",
    "compliance": "Regulatory Compliance",
    "steganography": "Steganography",
    "osint": "OSINT Techniques",
    "phishing_detection": "Phishing Detection",
    "password_security": "Password Security",
}

# Keywords that bias scoring toward a role
_INTEREST_ROLE_MAP = [
    (["pentest", "hack", "exploit", "red team", "bug bounty", "offensive"], "Penetration Tester"),
    (["soc", "monitor", "alert", "incident", "blue team", "defend", "detection"], "SOC Analyst"),
    (["forensic", "evidence", "investigation", "legal", "malware"], "Digital Forensics Investigator"),
    (["engineering", "cloud", "infrastructure", "devops", "devsecops", "build"], "Security Engineer"),
    (["crypto", "cipher", "key", "protocol", "mathematical", "maths"], "Cryptography Specialist"),
    (["osint", "intelligence", "research", "open source", "investigat"], "OSINT Analyst"),
    (["reverse", "assembly", "malware", "binary", "disassemble"], "Malware Analyst"),
    (["consult", "risk", "compliance", "audit", "governance", "grc", "iso"], "Cybersecurity Consultant"),
]

_SUBJECT_ROLE_MAP = [
    (["computer science", "software", "programming", "computing"], ["Penetration Tester", "Security Engineer", "Malware Analyst"]),
    (["network", "telecoms", "communications"], ["SOC Analyst", "Security Engineer", "Penetration Tester"]),
    (["mathematics", "maths", "statistics"], ["Cryptography Specialist", "Malware Analyst"]),
    (["law", "legal", "criminology"], ["Digital Forensics Investigator", "Cybersecurity Consultant"]),
    (["business", "management", "finance", "accounting"], ["Cybersecurity Consultant", "SOC Analyst"]),
    (["information technology", "it", "information systems"], ["SOC Analyst", "Security Engineer"]),
    (["data science", "machine learning", "ai", "artificial intelligence"], ["SOC Analyst", "Security Engineer"]),
    (["psychology", "social science", "communication"], ["Cybersecurity Consultant", "OSINT Analyst"]),
]


def _normalise_skill_slug(raw: str) -> str:
    return raw.strip().lower().replace(" ", "_").replace("-", "_")


def _skill_level_int(level_str: str) -> int:
    """Convert text level to 1-5 integer."""
    mapping = {
        "beginner": 1, "novice": 1,
        "basic": 2, "elementary": 2,
        "intermediate": 3,
        "advanced": 4, "proficient": 4,
        "expert": 5, "professional": 5,
    }
    return mapping.get((level_str or "").strip().lower(), 2)


def recommend_career(subject: str, skills: list, interests: str, experience: str, study_hours: int) -> dict:
    """
    Return {career_role, skill_gaps, learning_roadmap}.

    skills: list of {"skill": str, "level": str} dicts from the form.
    """
    subject_lower = (subject or "").lower()
    interests_lower = (interests or "").lower()
    experience_lower = (experience or "").lower()

    # Build a score dict for each role
    scores = {role: 0 for role in ROLES}

    # 1. Subject bias
    for keywords, roles in _SUBJECT_ROLE_MAP:
        if any(kw in subject_lower for kw in keywords):
            for role in roles:
                scores[role] += 2

    # 2. Interest / experience bias
    combined_text = interests_lower + " " + experience_lower
    for keywords, role in _INTEREST_ROLE_MAP:
        if any(kw in combined_text for kw in keywords):
            scores[role] += 3

    # 3. Skill match — award 1 point per skill that matches a role's requirements
    user_skills = {}
    for item in (skills or []):
        slug = _normalise_skill_slug(item.get("skill", ""))
        if slug:
            user_skills[slug] = _skill_level_int(item.get("level", "beginner"))

    for role, meta in ROLES.items():
        for skill_slug, min_level in meta["skills_required"].items():
            user_level = user_skills.get(skill_slug, 0)
            if user_level >= min_level:
                scores[role] += 1
            elif user_level > 0:
                scores[role] += 0.5  # partial credit

    # 4. Study hours — favour roles with shorter learning curves for busy learners
    if study_hours <= 5:
        scores["SOC Analyst"] += 1
        scores["Cybersecurity Consultant"] += 1

    # Pick the highest-scoring role
    best_role = max(scores, key=lambda r: scores[r])
    role_meta = ROLES[best_role]

    # Build skill gap analysis
    skill_gaps = []
    for skill_slug, min_level in role_meta["skills_required"].items():
        user_level = user_skills.get(skill_slug, 0)
        if user_level < min_level:
            skill_gaps.append({
                "skill": SKILL_LABELS.get(skill_slug, skill_slug.replace("_", " ").title()),
                "current": user_level,
                "needed": min_level,
                "gap": min_level - user_level,
            })

    # Sort gaps largest first
    skill_gaps.sort(key=lambda g: g["gap"], reverse=True)

    # Build learning roadmap
    roadmap = _build_roadmap(best_role, skill_gaps, study_hours)

    return {
        "career_role": best_role,
        "description": role_meta["description"],
        "certifications": role_meta["certifications"],
        "avg_salary": role_meta["avg_salary"],
        "skill_gaps": skill_gaps,
        "learning_roadmap": roadmap,
    }


_RESOURCE_MAP = {
    "Networking": "Complete the CyberQuest Network Defense module and study the CompTIA Network+ syllabus.",
    "Linux": "Work through OverTheWire: Bandit and the Linux Foundation's Introduction to Linux (free).",
    "Web Security": "Complete PortSwigger Web Security Academy (free) — start with SQL injection and XSS.",
    "Python / Scripting": "Work through Automate the Boring Stuff with Python (free online) then build a small security script.",
    "Cryptography": "Complete CyberQuest Cryptography practice, then try the Cryptopals challenges.",
    "SIEM / Log Platforms": "Set up a free Splunk trial; practice with the BOTS dataset on TryHackMe.",
    "Incident Response": "Study the NIST SP 800-61 guide; practice with Blue Team Labs Online.",
    "Log Analysis": "Practice Splunk/ELK queries on the public Boss of the SOC (BOTS) data set.",
    "Threat Intelligence": "Read the MITRE ATT&CK framework and complete the related TryHackMe room.",
    "Digital Forensics": "Try Autopsy on a practice image from Digital Corpora; read the SANS FOR508 syllabus.",
    "Windows Administration": "Study the Windows Server Administration Fundamentals (MTA 98-365) guide.",
    "Evidence Handling": "Read ACPO Good Practice Guide for Digital Evidence; practice chain-of-custody documentation.",
    "Cloud Security": "Complete the AWS Security Fundamentals course (free); explore the Cloud Security Alliance resources.",
    "Scripting / Automation": "Learn Bash scripting; practice with TryHackMe scripting rooms.",
    "Identity & Access Management": "Study the Microsoft Identity and Access course on Learn; practice with Azure AD free tier.",
    "DevSecOps": "Complete the DevSecOps pathway on TryHackMe; read the OWASP DevSecOps Guideline.",
    "Mathematics": "Study discrete mathematics with MIT OpenCourseWare 6.042J; practice number theory.",
    "Cryptographic Protocols": "Read 'Serious Cryptography' by Jean-Philippe Aumasson (open syllabus); try the Cryptopals challenges.",
    "Research Methods": "Practice structured note-taking with Obsidian; work through a Bellingcat open-source investigation.",
    "Data Analysis": "Learn pandas and matplotlib (free Python tutorials); practice on a public SIEM dataset.",
    "Social Engineering Awareness": "Read 'The Art of Intrusion' by Kevin Mitnick; complete phishing simulation training.",
    "Technical Reporting": "Study the SANS reading room report templates; write up a practice CTF finding as a report.",
    "Assembly Language": "Work through 'Programming from the Ground Up' (free PDF); try Malware Unicorn workshops.",
    "Reverse Engineering": "Use Ghidra on a crackme from crackmes.one; follow the OpenSecurityTraining2 Arch1001 course.",
    "Risk Management": "Study ISO 31000 and NIST RMF; practice risk assessments on sample scenarios.",
    "Business Communication": "Complete a technical writing course (Coursera / edX); practice summarising findings for non-technical audiences.",
    "Regulatory Compliance": "Read GDPR Article 32 and the ICO guidance; study the ISO 27001 control objectives.",
    "Steganography": "Complete CyberQuest Steganography Hunt game; read 'Hiding in Plain Sight' by Eric Cole.",
    "OSINT Techniques": "Work through the OSINT Framework; practice with TraceLabs OSINT challenges.",
    "Phishing Detection": "Play CyberQuest Phishing Simulator; complete the Proofpoint Security Awareness training.",
    "Password Security": "Play CyberQuest Password Cracker; read NIST SP 800-63B for modern guidance.",
}


def _build_roadmap(role: str, gaps: list, study_hours: int) -> list:
    steps = []

    # Phase 1: Close the biggest skill gap first
    for gap in gaps[:3]:
        skill_name = gap["skill"]
        resource = _RESOURCE_MAP.get(skill_name, f"Search for '{skill_name} fundamentals' on TryHackMe or Coursera.")
        weeks = max(2, gap["gap"] * (3 if study_hours <= 5 else 2))
        steps.append({
            "phase": f"Close gap: {skill_name}",
            "action": resource,
            "weeks": weeks,
        })

    # Phase 2: Certification path
    role_meta = ROLES[role]
    if role_meta["certifications"]:
        first_cert = role_meta["certifications"][0]
        steps.append({
            "phase": f"Target certification: {first_cert}",
            "action": f"Work through the official {first_cert} study guide and practice exams. "
                      f"Aim for {'12' if study_hours <= 5 else '8'} weeks of focused preparation.",
            "weeks": 12 if study_hours <= 5 else 8,
        })

    # Phase 3: Practical project
    project_map = {
        "Penetration Tester": "Complete a full-scope CTF (e.g. Hack The Box starting point) and write a pentest report.",
        "SOC Analyst": "Build a home lab with Splunk or Elastic SIEM; ingest logs from a test VM and write 3 detection rules.",
        "Digital Forensics Investigator": "Analyse a practice disk image from Digital Corpora and produce a findings report.",
        "Security Engineer": "Deploy a hardened Linux server on a free cloud tier; document all controls applied.",
        "Cryptography Specialist": "Implement a simple RSA or AES demo in Python from scratch (no libraries); document each step.",
        "OSINT Analyst": "Conduct a fictional-target OSINT investigation on a TraceLabs challenge and write an intelligence report.",
        "Malware Analyst": "Analyse a benign crackme binary in Ghidra; document its functionality and produce a one-page report.",
        "Cybersecurity Consultant": "Write a risk assessment for a fictional SMB; map findings to ISO 27001 controls.",
    }
    steps.append({
        "phase": "Practical project",
        "action": project_map.get(role, "Complete a capture-the-flag challenge and write up your findings."),
        "weeks": 4,
    })

    # Phase 4: Job readiness
    steps.append({
        "phase": "Job readiness",
        "action": (
            "Build a portfolio: a GitHub repo with your code/reports, a LinkedIn headline, "
            "and a one-page CV tailored to the role. Practice answering scenario questions aloud."
        ),
        "weeks": 3,
    })

    return steps
