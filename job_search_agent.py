#!/usr/bin/env python3
"""
Job Search Agent - Daily 1:30 PM PST
Searches for Sr. Director of Engineering roles in retail tech.
Sends digest email via Gmail SMTP (App Password).
"""

import os
import sys
import time
import ssl
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

import anthropic

# ── CONFIG ──────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY  = os.environ.get("ANTHROPIC_API_KEY", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
GMAIL_SENDER       = "vermasangeeta@gmail.com"
TARGET_EMAIL       = "vermasangeeta@gmail.com"
ROLE               = "Senior Director of Engineering"
LOG_FILE           = os.path.expanduser("~/roughpad/jobBot/logs/job_agent.log")

SEARCH_QUERIES = [
    f'"{ROLE}" retail technology jobs 2026',
    f'"Sr Director of Engineering" retail ecommerce omnichannel',
    f'"{ROLE}" Levi\'s OR ALO OR Gap OR Target OR Walmart careers',
    f'"{ROLE}" store commerce POS technology jobs',
    f'"{ROLE}" retail omnichannel engineering hiring 2026',
    f'"Senior Director Engineering" retail fashion technology site:linkedin.com',
    f'"{ROLE}" site:indeed.com retail technology',
    f'"VP Engineering" OR "Sr Director Engineering" retail store systems jobs',
]

FILTER_SYSTEM = f"""You are a job search assistant for retail technology leadership roles.

Given web search results, extract job postings matching "{ROLE}" in retail/commerce technology.

INCLUDE only roles where:
- Title is: Senior Director of Engineering, Sr. Director of Engineering, VP Engineering,
  or Director of Engineering (senior level)
- Industry: Retail, ecommerce, store commerce, omnichannel, POS, fashion/apparel, consumer goods
- Relevant tech: Engineering leadership, POS/store systems, omnichannel, payments/EMV

For EACH match output exactly this format:
COMPANY: [name]
TITLE: [exact job title]
LOCATION: [city / remote / hybrid]
FIT_SCORE: [1-10 based on retail store commerce engineering fit]
HIGHLIGHTS: [2-3 key responsibilities, comma-separated]
URL: [direct link or "Search on [Company] careers page"]
---

If no matches, output: NO_MATCHES"""

# ── LOGGING ──────────────────────────────────────────────────────────────────
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

def log(msg):
    ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

# ── SEARCH ────────────────────────────────────────────────────────────────────
def search_and_filter(client: anthropic.Anthropic, query: str) -> str:
    """Run one web-search query through Claude and filter results, with retry on rate limit."""
    for attempt in range(4):
        try:
            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1500,
                system=FILTER_SYSTEM,
                tools=[{"type": "web_search_20260209", "name": "web_search"}],
                messages=[{
                    "role": "user",
                    "content": (
                        f'Search for jobs using this query and extract matches:\n"{query}"\n\n'
                        f"Today is {datetime.now().strftime('%B %d, %Y')}. "
                        f"Focus on {ROLE} roles in retail/ecommerce companies."
                    ),
                }],
            )
            return "\n".join(b.text for b in response.content if b.type == "text")
        except anthropic.RateLimitError:
            wait = 60 * (attempt + 1)   # 60s, 120s, 180s, 240s
            log(f"  → Rate limited — waiting {wait}s before retry {attempt + 1}/3...")
            time.sleep(wait)
    raise RuntimeError("Exceeded retries due to rate limiting")


def consolidate(client: anthropic.Anthropic, raw_blocks: list) -> str:
    """Deduplicate, rank, and summarise across all search batches."""
    combined = "\n\n===\n\n".join(raw_blocks)
    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=2000,
        messages=[{
            "role": "user",
            "content": (
                f"Here are job search results for '{ROLE}' in retail technology:\n\n"
                f"{combined}\n\n"
                "Please:\n"
                "1. DEDUPLICATE any repeated companies/roles\n"
                "2. RANK the top 10 by fit_score descending\n"
                "3. Keep the same structured format "
                "(COMPANY / TITLE / LOCATION / FIT_SCORE / HIGHLIGHTS / URL / ---)\n"
                "4. End with a 2-sentence MARKET_SUMMARY of current hiring trends\n"
                "If fewer than 10 found, list all."
            ),
        }],
    )
    return "\n".join(b.text for b in response.content if b.type == "text")

# ── EMAIL ─────────────────────────────────────────────────────────────────────
def send_via_smtp(subject: str, body: str) -> bool:
    """Send email via Gmail SMTP using App Password."""
    if not GMAIL_APP_PASSWORD:
        log("⚠️  GMAIL_APP_PASSWORD not set — skipping SMTP, saving locally only")
        return False
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_SENDER
    msg["To"]      = TARGET_EMAIL
    msg.attach(MIMEText(body, "plain"))
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(GMAIL_SENDER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_SENDER, TARGET_EMAIL, msg.as_string())
    return True

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    log("=" * 60)
    log("Job Search Agent starting")
    log(f"Role: {ROLE}")
    log(f"Recipient: {TARGET_EMAIL}")
    log(f"Queries: {len(SEARCH_QUERIES)}")

    if not ANTHROPIC_API_KEY:
        log("ERROR: ANTHROPIC_API_KEY is not set")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # ── 1. Search all queries ─────────────────────────────────────────────────
    raw_results = []
    for i, query in enumerate(SEARCH_QUERIES, 1):
        log(f"[{i}/{len(SEARCH_QUERIES)}] Searching: {query[:70]}...")
        try:
            result = search_and_filter(client, query)
            if result and "NO_MATCHES" not in result:
                raw_results.append(result)
                count = result.count("COMPANY:")
                log(f"  → {count} match(es) found")
            else:
                log("  → No matches in this batch")
        except Exception as e:
            log(f"  → ERROR: {e}")
        time.sleep(30)

    if not raw_results:
        log("No results found across all queries — sending empty digest")
        raw_results = ["No matching jobs found today. Will retry tomorrow."]

    # ── 2. Consolidate & rank ─────────────────────────────────────────────────
    log("Consolidating and ranking results...")
    try:
        digest_body = consolidate(client, raw_results)
    except Exception as e:
        log(f"Consolidation error: {e}")
        digest_body = "\n\n".join(raw_results)

    # ── 3. Build email ────────────────────────────────────────────────────────
    today      = datetime.now().strftime("%A, %B %d, %Y")
    subject    = f"🎯 Daily Job Digest: {ROLE} in Retail Tech — {today}"
    email_body = f"""Hi Sangeeta,

Here is your daily job search digest for {ROLE} in retail technology.
Generated: {today} at 1:30 PM PST

{'=' * 55}

{digest_body}

{'=' * 55}

This digest was generated automatically by your Job Search Agent.
Sources searched: LinkedIn, Indeed, Glassdoor, and major retailer career pages.
Queries run: {len(SEARCH_QUERIES)} | Results processed: {len(raw_results)} batches
"""

    # ── 4. Send email ─────────────────────────────────────────────────────────
    log("Sending email via Gmail SMTP...")
    try:
        if send_via_smtp(subject, email_body):
            log(f"✅ Email sent to {TARGET_EMAIL}")
    except Exception as e:
        log(f"❌ Gmail SMTP error: {e}")

    # Always save a local backup
    fallback = os.path.expanduser(
        f"~/roughpad/jobBot/logs/digest_{datetime.now().strftime('%Y%m%d')}.txt"
    )
    with open(fallback, "w") as f:
        f.write(f"Subject: {subject}\n\n{email_body}")
    log(f"Digest saved locally: {fallback}")

    log("Job Search Agent complete")
    log("=" * 60)


if __name__ == "__main__":
    main()
