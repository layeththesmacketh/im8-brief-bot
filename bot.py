import os
import re
import json
from datetime import date
import anthropic
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

# ── Environment ──────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ANTHROPIC_API_KEY  = os.environ["ANTHROPIC_API_KEY"]

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ── System prompt for Claude ──────────────────────────────────────────────────
SYSTEM_PROMPT = """You are an IM8 video production assistant. When given a creative brief, extract and map the information to fill out a row in the IM8 Video Editing Process Google Sheet.

NAMING CONVENTION:
YYMMDD_FORMAT_ADTYPE_ICP_PROBLEM_CREATIVENUMBER_AGENCY_BATCHNAME_CREATORTYPE_CREATORNAME_HOOK_WTAD_LDP*

CODE TABLES:

FORMAT:
VID=Video, IMG=Image, CRS=Carousel, FLXVID=Flexible Video, IE=Instant Experience

AD TYPES:
TALKH=Talking Head, PODCT=Podcast, TREND=Trend, VLOG=Routine Vlog, PANEL=Event Panel,
EVENT=Event Recap, VSL=VSL, MUSIC=Music Short, ANIMT=Animations, CALLC=Calling Customers,
BTS=Factory/Pop Up/Store/Event BTS, INTER=Interviews, WOTXT=Wall of Text,
RVIEW=Real Customer Reviews, UNBOX=Unboxing, LIST=Listicle, GRNSRN=Green Screen,
VOBRL=Voiceover Broll, AINRTR=AI Narrator

ICP CODES:
SIMPSK=Simplification Seekers, AGATH=Aging Athletes, DIETOP=Diet Optimizer,
MEDRL=Medication Relief, BIOHK=Biohackers, HCSS=Health Condition Solution Seekers,
VTFS=Vitality Focused Seniors, GENL=Generic Longevity, GENE=Generic Essentials,
GENBS=Generic Beckham Stack, GEN=Generic No SKU, MENO=Menopause, COLL=Collagen,
GLP=GLP-1 Users, PCOS=PCOS, ADHD=ADHD, INSL=Insulin Resistance

PROBLEM CODES:
BLOAT, MULTISUPP, LOWENGY, FATIGUE, RECOVERY, PERFORM (Performance/Fitness),
IMMUNITY, GUTHEALTH, PERFORMANCE, ALLINONE, BRAND, LONGEVITY, AGING, SKIN, SLEEP,
ENERGY, HYDRATION, JOINTHEALTH, EDUCATIONAL, MULTIUSP, HEALTHBENEFITS, ABSORPTION,
BRAIN, GAPS, WEIGHTLOSS, METABOLICHEALTH, CELLULARHEALTH, INGREDIENTS, VITALITY,
9BODYSYSTEMS, COLLAGEN, COST

CREATOR TYPES:
NA, AFF=Affiliate, KOL=Key Opinion Leader, AMB=Ambassador, CUST=Customer, UGC=UGC,
ATH=Athlete, SAB=Scientific Advisory, DOC=Doctor, FND=Founder, AVA=AI Avatar

AGENCY: INT=Internal

WTAD: WTAD=Whitelisted Creator Ad, PTAD=Partnership Ad, NA

LDP CODES:
HOMEPAGE, PDP, PDPPRO, V2UPGRADELDP, V2FLAVOURSLDP, GETPDP, DB, PDPLONGEVITY,
PDPTBS, PDP3OD, PDP3ODLONGEVITY, GETQUIZ, GETQUIZV2, DIETLDP, TRANSFORMATIONLDP,
GETFITNESSLDP, GETRECOVERYHRLDP, GETRECOVERYIGRTLDP, GETRECOVERYACTLDP,
GETRECOVERYCOMPLDP, GETRECOVERYPROLDP, GETENERGYLP, SENIORSLP, MENOPAUSELDP,
WHYIM8LDP, NORSLOP

RULES:
- CREATORNAME: strip spaces and punctuation, ALL CAPS (e.g. David Beckham → DAVIDBECKHAM)
- HOOK: summarise the first 3-5 seconds in ALL CAPS no spaces (e.g. THREETHINGSICOACHO)
- BATCHNAME: derive from project/event name in ALL CAPS no spaces (e.g. Desert Smash → DESERTSMASH)
- CREATIVENUMBER: default C1A1 unless variations are specified
- WTAD: default NA unless specified
- PIC: always "Nick"
- EDITOR: always "TBD"
- CURRENT_STATUS: always "Ready To Start"
- TYPE: default "100% Net New" unless it's clearly a variation of a winning ad
- EDITING_STYLE: default "TikTok Organic" unless brief specifies documentary/VSL/etc
- Note: PERFORM problem code needs confirmation with NOA before use

Return ONLY a valid JSON object — no markdown, no explanation, just the JSON:

{
  "name": "full naming string",
  "concept_reference": "N/A or link",
  "execution": "Internal Editing Only",
  "script_concept_link": "N/A or link",
  "concept_name_description": "short human-readable description",
  "raw_footage_link": "URL or TBD",
  "comments": "key edit notes: length, style, cameras, hook, reference link if any",
  "type": "100% Net New",
  "winner_iteration_ref": "None",
  "editing_style": "TikTok Organic",
  "pic": "Nick",
  "editor": "TBD",
  "current_status": "Ready To Start",
  "frame_io_link": "TBD",
  "num_videos": "1",
  "landing_page": "full URL or TBD",
  "yymmdd": "YYMMDD",
  "format_code": "VID",
  "ad_type": "code",
  "icp": "code",
  "problem": "code",
  "creative_number": "C1A1",
  "agency": "INT",
  "batch_name": "code",
  "creator_type": "code",
  "creator_name": "FIRSTLAST",
  "hook_message": "HOOKCODE",
  "wtad": "NA",
  "ldp": "code",
  "flags": "any warnings — e.g. PERFORM needs NOA confirmation",
  "reasoning": "1-2 sentence explanation of key mapping decisions"
}"""


# ── In-memory state (user_id → pending data) ─────────────────────────────────
pending: dict[int, dict] = {}


# ── Helpers ───────────────────────────────────────────────────────────────────

def parse_brief(brief_text: str) -> dict:
    today = date.today().strftime("%y%m%d")
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=SYSTEM_PROMPT + f"\n\nToday's date (for YYMMDD): {today}",
        messages=[{"role": "user", "content": f"Parse this brief:\n\n{brief_text}"}],
    )
    raw = message.content[0].text.strip()
    # Strip markdown code fences if Claude adds them
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def build_preview(d: dict) -> str:
    flags = d.get("flags", "")
    flag_line = f"\n⚨️ *Flags:* _{flags}_" if flags else ""

    return (
        f"📋 *PARSED BRIEF — REVIEW BEFORE COMMITTING*\n\n"
        f"📌 *Name:*\n`{d.get('name', 'TBD')}`\n\n"
        f"🎬 *Ad Type:* `{d.get('ad_type')}` │ *ICP:* `{d.get('icp')}` │ *Problem:* `{d.get('problem')}`\n"
        f"📦 *Batch:* `{d.get('batch_name')}` │ *Agency:* `{d.get('agency')}` │ *Creative #:* `{d.get('creative_number')}`\n"
        f"👤 *Creator:* `{d.get('creator_name')}` ({d.get('creator_type')})\n"
        f"🪝 *Hook:* `{d.get('hook_message')}`\n"
        f"🔗 *LDP:* `{d.get('ldp')}`\n\n"
        f"📝 *Description:* {d.get('concept_name_description')}\n"
        f"🎥 *Raw Footage:* {d.get('raw_footage_link', 'TBD')}\n"
        f"💬 *Comments:* {d.get('comments', '')}\n\n"
        f"🎨 *Type:* {d.get('type')} │ *Style:* {d.get('editing_style')}\n"
        f"🙋 *PIC:* {d.get('pic')} │ *Status:* {d.get('current_status')}"
        f"{flag_line}\n\n"
        f"💡 _{d.get('reasoning', '')}_"
    )


def build_tab_row(d: dict) -> str:
    """
    Builds a tab-separated string matching the column order in April Ad Pipeline 2026.
    Columns A–AM. Blank strings hold the place for auto-filled / locked columns.
    """
    cols = [
        d.get("name", ""),                      # A  Name
        d.get("concept_reference", ""),          # B  Concept Reference
        d.get("execution", "Internal Editing Only"),  # C  Execution
        d.get("script_concept_link", "N/A"),     # D  Script/Concept Link
        d.get("concept_name_description", ""),   # E  Concept Name / Description
        "",                                      # F  (Raw Footage Master – link header)
        "",                                      # G  (blank)
        "",                                      # H  (blank)
        d.get("raw_footage_link", ""),           # I  Raw Footage Link
        d.get("comments", ""),                   # J  Comments
        d.get("type", "100% Net New"),           # K  Type
        d.get("winner_iteration_ref", "None"),   # L  Winner Iteration Ref
        d.get("editing_style", "TikTok Organic"),# M  Editing Style
        d.get("pic", "Nick"),                    # N  PIC
        d.get("editor", "TBD"),                  # O  Editor
        "",                                      # P  Krave Capacity (auto)
        "",                                      # Q  IM8 Capacity (auto)
        d.get("current_status", "Ready To Start"),# R  Current Status
        d.get("frame_io_link", ""),              # S  Frame IO Link
        d.get("num_videos", "1"),                # T  # Of Videos
        d.get("landing_page", ""),               # U  Landing Page
        "",                                      # V  (blank)
        "",                                      # W  Uploaded? (checkbox – leave blank)
        "",                                      # X  Week Complete Reported? (John only)
        "",                                      # Y  Handover Link
        "",                                      # Z  (blank)
        d.get("yymmdd", ""),                     # AA YYMMDD
        d.get("format_code", "VID"),             # AB Format
        d.get("ad_type", ""),                    # AC Ad Type
        d.get("icp", ""),                        # AD ICP
        d.get("problem", ""),                    # AE Problem (Concept)
        d.get("creative_number", "C1A1"),        # AF Creative Number
        d.get("agency", "INT"),                  # AG Agency
        d.get("batch_name", ""),                 # AH Batch Name
        d.get("creator_type", ""),               # AI Creator Type
        d.get("creator_name", ""),               # AJ Creator Name
        d.get("hook_message", ""),               # AK Hook Message
        d.get("wtad", "NA"),                     # AL WTAD
        d.get("ldp", ""),                        # AM LDP
    ]
    return "\t".join(str(c) for c in cols)


# ── Handlers ──────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 *IM8 Brief Parser Bot*\n\n"
        "Paste any creative brief and I'll map it to the IM8 Video Editing Sheet.\n\n"
        "You'll get a preview to review — then approve it to get the paste-ready row for Google Sheets.\n\n"
        "_Commands:_\n"
        "/start — show this message\n"
        "/cancel — discard current brief",
        parse_mode="Markdown",
    )


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    pending.pop(update.effective_user.id, None)
    await update.message.reply_text("❌ Cancelled. Paste a new brief whenever you're ready.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    text = update.message.text.strip()

    await update.message.reply_text("⏳ Parsing brief with Claude…")

    try:
        data = parse_brief(text)
    except json.JSONDecodeError as e:
        await update.message.reply_text(
            f"❌ Couldn't parse Claude's response as JSON.\nError: {e}\n\nPlease try again."
        )
        return
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}\n\nPlease try again.")
        return

    pending[user_id] = data
    preview = build_preview(data)

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve — give me the row", callback_data="approve"),
            InlineKeyboardButton("❌ Discard", callback_data="discard"),
        ]
    ])

    await update.message.reply_text(preview, parse_mode="Markdown", reply_markup=keyboard)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "discard":
        pending.pop(user_id, None)
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("❌ Discarded. Paste a new brief whenever you're ready.")
        return

    if query.data == "approve":
        data = pending.pop(user_id, None)
        if not data:
            await query.message.reply_text("⚠️ No pending brief found. Please paste the brief again.")
            return

        tab_row = build_tab_row(data)
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(
            "✅ *Paste-ready row*\n\n"
            "Copy everything between the lines, then paste into the first empty cell in column A of the April Ad Pipeline tab.\n"
            "Each value will auto-fill across the columns.\n\n"
            "───────────────────────\n"
            f"`{tab_row}`\n"
            "───────────────────────\n\n"
            "⚨️ _Remember to check any flagged fields (e.g. PERFORM needs NOA confirmation) before saving._",
            parse_mode="Markdown",
        )


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot is running…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
