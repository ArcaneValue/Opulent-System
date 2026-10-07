from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether

ROOT = Path(r"C:\opulent condo system")
OUT = ROOT / "output" / "pdf" / "opulent_pricing_review.pdf"
OUT.parent.mkdir(parents=True, exist_ok=True)

NAVY = colors.HexColor("#14213b")
GOLD = colors.HexColor("#b98b36")
INK = colors.HexColor("#1e293b")
MUTED = colors.HexColor("#526174")
PALE = colors.HexColor("#f5f7fa")
LINE = colors.HexColor("#d8e0e9")

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="TitleX", fontName="Helvetica-Bold", fontSize=23, leading=27, textColor=NAVY, spaceAfter=11))
styles.add(ParagraphStyle(name="Deck", fontName="Helvetica", fontSize=10.5, leading=15, textColor=MUTED, spaceAfter=18))
styles.add(ParagraphStyle(name="H1X", fontName="Helvetica-Bold", fontSize=14, leading=18, textColor=NAVY, spaceBefore=14, spaceAfter=8))
styles.add(ParagraphStyle(name="H2X", fontName="Helvetica-Bold", fontSize=10.5, leading=14, textColor=NAVY, spaceBefore=10, spaceAfter=5))
styles.add(ParagraphStyle(name="BodyX", fontName="Helvetica", fontSize=9.2, leading=13.5, textColor=INK, spaceAfter=7))
styles.add(ParagraphStyle(name="SmallX", fontName="Helvetica", fontSize=7.8, leading=11, textColor=MUTED, spaceAfter=5))
styles.add(ParagraphStyle(name="CallX", fontName="Helvetica-Bold", fontSize=11, leading=15, textColor=NAVY))

def p(t, sty="BodyX"):
    return Paragraph(t, styles[sty])

def bullet(t):
    return p("&#8226; " + t)

def table(rows, widths, header=True):
    data = [[p(str(c), "SmallX" if i == 0 else "BodyX") for c in row] for i, row in enumerate(rows)]
    t = Table(data, colWidths=widths, hAlign="LEFT", repeatRows=1 if header else 0)
    cmds = [
        ("VALIGN", (0,0),(-1,-1),"TOP"),
        ("LEFTPADDING",(0,0),(-1,-1),8), ("RIGHTPADDING",(0,0),(-1,-1),8),
        ("TOPPADDING",(0,0),(-1,-1),6), ("BOTTOMPADDING",(0,0),(-1,-1),5),
        ("LINEBELOW",(0,-1),(-1,-1),0.5,LINE),
    ]
    if header:
        cmds += [("BACKGROUND",(0,0),(-1,0),PALE),("LINEBELOW",(0,0),(-1,0),0.7,LINE)]
    for i in range(1,len(rows)):
        if i % 2 == 0:
            cmds.append(("BACKGROUND",(0,i),(-1,i),colors.HexColor("#fafbfd")))
    t.setStyle(TableStyle(cmds))
    return t

doc = SimpleDocTemplate(str(OUT), pagesize=(595.28,841.89), rightMargin=47, leftMargin=47, topMargin=55, bottomMargin=53,
                        title="Opulent System - Pricing and Commercial Review", author="Codex")

story=[]
story += [p("OPULENT SYSTEM", "SmallX"), p("Pricing and commercial review", "TitleX"),
          p("A working guide for pricing the original build, quoting another organization, and separating ongoing operating costs. Prepared 6 October 2026. Figures are recommendations, not an appraisal or a new invoice.", "Deck")]

call = Table([[p("Recommended original-build quote", "SmallX"), p("USD 800-1,500", "CallX")],
              [p("Practical example", "SmallX"), p("USD 1,200", "CallX")]], colWidths=[245,245])
call.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),PALE),("BOX",(0,0),(-1,-1),0.6,LINE),
                           ("LEFTPADDING",(0,0),(-1,-1),12),("TOPPADDING",(0,0),(-1,-1),8),
                           ("BOTTOMPADDING",(0,0),(-1,-1),8)]))
story += [call, Spacer(1,14),p("Executive assessment", "H1X"),
          p("The agreed USD 100 was very low for the scope of a custom billing and reminder system. A first-client or pilot discount can be a deliberate business choice, but it should be named as such. Do not retroactively replace an agreed invoice without mutual agreement; quote additional work separately."),
          p("What was reviewed", "H1X"),
          p("The repository contains staff roles and sign-in; properties, units and contacts; recurring charges; payment allocation, credits and reversals; manual and scheduled reminders; SMS integration; statement and receipt links; histories, reports, audit records; a responsive installable web interface; and PostgreSQL/Railway deployment files. This is more than a single reminder form."),
          p("Limits that affect what can be promised", "H1X"),
          bullet("The documentation calls the product a single-organization pilot. Some operating policies and production hardening remain important before a broad commercial rollout."),
          bullet("SMS provider acceptance is not proof of handset delivery. Operational monitoring and reconciliation should be part of a production agreement."),
          bullet("The latest GitHub verification run for the receipt update showed a failure as of this review. Resolve it and complete acceptance testing before calling that update fully verified."),
          p("Pricing assumptions", "H1X"),
          p("All development prices below are judgment-based scope estimates, not published market rates. UGX examples use a rounded planning rate of UGX 4,000 per USD; use the contract's actual currency-conversion rule for billing. No verified record of hours worked or signed intellectual-property terms was supplied."),
          PageBreak()]

story += [p("1. Original Opulent build", "TitleX"),
          p("Illustrative one-time quote if the same scope were priced before work began.","Deck"),
          table([
              ["Work package","Example price"],
              ["Requirements and billing rules","USD 100"],
              ["Units, contacts, charges, payments, balances","USD 350"],
              ["Reminder scheduling and SMS integration","USD 150"],
              ["Statements and receipts","USD 200"],
              ["Staff interface and responsive layout","USD 150"],
              ["Deployment and testing","USD 200"],
              ["Handover and basic training","USD 50"],
              ["TOTAL","USD 1,200"],
          ],[372,118]),
          Spacer(1,9),
          p("A sensible initial quoting range would have been USD 800-1,500 (approximately UGX 3.2-6.0 million at the planning rate). The lower end assumes tight scope and a pilot-level handover. The higher end allows more validation, training and deployment work. If actual hours, scope or production obligations were much greater, the quote could be higher."),
          p("2. Another company using the existing product", "H1X"),
          p("Reusing working code reduces development effort. Each organization's data, rules, staff training and testing still require paid work."),
          table([
              ["Work package","Example price"],
              ["Configuration and branding","USD 100"],
              ["Preparing/importing company records","USD 200"],
              ["Workflow adjustments","USD 150"],
              ["Acceptance testing and staff training","USD 250"],
              ["TOTAL","USD 700"],
          ],[372,118]),
          Spacer(1,8),
          p("Suggested setup range: USD 500-1,200 (roughly UGX 2.0-4.8 million at the planning rate) for a small organization with limited customization. Quote significant new features separately. Building a comparable system from scratch for a different customer could be USD 1,500-3,000 or more, subject to scope and delivery commitments."),
          p("Before reusing the code commercially, confirm whether the Opulent agreement grants the customer exclusive ownership or restricts resale. A reusable product license and a custom work-for-hire project should be priced differently."),
          PageBreak()]

story += [p("3. Operating costs and invoice", "TitleX"),
          p("Recurring costs should be visible and separate from the one-time build fee.","Deck"),
          table([
              ["Cost","Working treatment"],
              ["Railway hosting/database","Pass through actual bill; Hobby minimum USD 5/month or Pro minimum USD 20/month, with usage affecting the final bill. The plan payment includes equal usage credit; do not add it twice."],
              ["SMS credits","Pass through actual provider charges. EgoSMS lists UGX 35 per SMS in its first volume tier; message length/segments and actual terms matter."],
              ["Support and maintenance","Propose USD 30-100/month only with a written limit on work and response time; this is a suggested commercial rate, not a provider charge."],
              ["New features/data migration","Estimate and approve separately before work."],
          ],[125,365]),
          Spacer(1,8),
          p("Illustration: 20 contacts receiving three one-segment messages in a month means 60 messages x UGX 35 = UGX 2,100 in SMS charges. Statements, receipts, repeats or multi-segment messages increase that total. This example excludes hosting and your labor."),
          p("Current Opulent invoice", "H1X"),
          p("The stated invoice was USD 70 for the build plus USD 30 for professional costs, totaling USD 100. You clarified that UGX 150,000 was a partial payment, not full settlement. At the rounded planning rate, USD 100 is about UGX 400,000 and the illustrative remainder is UGX 250,000. Calculate and request the actual balance under your agreed exchange-rate and payment terms."),
          p("Recommended next commercial steps", "H1X"),
          bullet("Document what the USD 100 already covers and ask for the remaining agreed payment without reframing the old price."),
          bullet("Write a new scope and price for future changes, support and onboarding other organizations."),
          bullet("Specify who owns the code, who holds the Railway/SMS accounts, what uptime/support you promise, and what happens when service bills are unpaid."),
          bullet("Complete verification and a real-user acceptance checklist before presenting the pilot as a production-ready product."),
          p("Sources and review basis", "H1X"),
          p("Local project: README.md, IMPLEMENTATION_NOTES.md and server.py in C:\\opulent condo system, reviewed 6 October 2026. Railway pricing: https://docs.railway.com/pricing/plans . EgoSMS pricing: https://www.egosms.co/pricing.php . GitHub verification run: https://github.com/ArcaneValue/Opulent-System/actions/runs/37467087341 . Provider rates and project status may change; recheck before issuing a new quote.","SmallX")]

def footer(canvas, document):
    canvas.saveState()
    w,h=document.pagesize
    canvas.setStrokeColor(LINE); canvas.setLineWidth(0.5); canvas.line(47,39,w-47,39)
    canvas.setFont("Helvetica",7.5); canvas.setFillColor(MUTED)
    canvas.drawString(47,26,"OPULENT SYSTEM  /  PRICING REVIEW")
    canvas.drawRightString(w-47,26,f"{document.page}")
    canvas.restoreState()

doc.build(story,onFirstPage=footer,onLaterPages=footer)
print(OUT)
