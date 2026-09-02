"""Report generation service for CSV, Excel-compatible and PDF printable reports."""
import csv
import io
from datetime import datetime
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

from app.models.user import User
from app.models.team import Team
from app.models.tournament import Tournament, TournamentRegistration
from app.models.match import Match, MatchResult
from app.models.payment import Payment
from app.models.prize import Prize
from app.models.dispute import Dispute


# ─────────────────────────────────────────────
# CSV / Excel Generators
# ─────────────────────────────────────────────

def generate_users_csv():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Full Name", "Username", "Email", "Phone", "Role", "Active", "Verified", "Created At", "Last Login"])
    
    users = User.query.order_by(User.id.asc()).all()
    for u in users:
        writer.writerow([
            u.id, u.full_name, u.username, u.email, u.phone or "",
            u.role_name, "Yes" if u.is_active_account else "No",
            "Yes" if u.is_email_verified else "No",
            u.created_at.strftime("%Y-%m-%d %H:%M") if u.created_at else "",
            u.last_login_at.strftime("%Y-%m-%d %H:%M") if u.last_login_at else "Never"
        ])
    return output.getvalue()


def generate_teams_csv():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Team Name", "Tag", "Captain", "Total Members", "Active", "Created At"])
    
    teams = Team.query.order_by(Team.id.asc()).all()
    for t in teams:
        writer.writerow([
            t.id, t.name, t.tag or "", t.captain.username if t.captain else "",
            t.members.count(), "Yes" if t.is_active else "No",
            t.created_at.strftime("%Y-%m-%d %H:%M") if t.created_at else ""
        ])
    return output.getvalue()


def generate_tournaments_csv():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Name", "Type", "Mode", "Map", "Status", "Max Teams", "Registered", "Entry Fee", "Prize Pool", "Start Time", "Deadline"])
    
    tournaments = Tournament.query.order_by(Tournament.start_time.desc()).all()
    for t in tournaments:
        writer.writerow([
            t.id, t.name, t.tournament_type, t.game_mode or "", t.map_name or "",
            t.status, t.max_teams, t.registered_team_count, str(t.entry_fee),
            str(t.prize_pool), t.start_time.strftime("%Y-%m-%d %H:%M"),
            t.registration_deadline.strftime("%Y-%m-%d %H:%M")
        ])
    return output.getvalue()


def generate_registrations_csv(tournament_id=None):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Registration Code", "Tournament", "Team Name", "Captain / Registered By", "Status", "Created At"])
    
    query = TournamentRegistration.query
    if tournament_id:
        query = query.filter_by(tournament_id=tournament_id)
    regs = query.order_by(TournamentRegistration.created_at.desc()).all()
    
    for r in regs:
        writer.writerow([
            r.registration_code, r.tournament.name, r.team.name,
            r.team.captain.username if r.team and r.team.captain else "",
            r.status, r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else ""
        ])
    return output.getvalue()


def generate_payments_csv():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Registration Code", "Tournament", "Team", "Amount", "Method", "Transaction ID", "Status", "Created At", "Rejection Reason"])
    
    payments = Payment.query.order_by(Payment.created_at.desc()).all()
    for p in payments:
        reg = p.registration
        writer.writerow([
            p.id, reg.registration_code if reg else "",
            reg.tournament.name if reg and reg.tournament else "",
            reg.team.name if reg and reg.team else "",
            str(p.amount), p.payment_method or "Manual",
            p.transaction_id or "", p.status,
            p.created_at.strftime("%Y-%m-%d %H:%M") if p.created_at else "",
            p.rejection_reason or ""
        ])
    return output.getvalue()


def generate_results_csv(tournament_id=None):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Result ID", "Match ID", "Tournament", "Round", "Team Name", "Placement", "Kills", "Placement Points", "Kill Points", "Total Points", "Status"])
    
    query = MatchResult.query.join(Match)
    if tournament_id:
        query = query.filter(Match.tournament_id == tournament_id)
    results = query.order_by(Match.scheduled_date.desc(), MatchResult.placement.asc()).all()
    
    for res in results:
        writer.writerow([
            res.id, res.match_id, res.match.tournament.name if res.match and res.match.tournament else "",
            res.match.round_number if res.match else 1,
            res.team.name if res.team else "",
            res.placement, res.kills, res.placement_points,
            res.kill_points, res.total_points, res.status
        ])
    return output.getvalue()


def generate_prizes_csv():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Prize ID", "Tournament", "Team Name", "Rank", "Amount", "Status", "Reference ID", "Payment Date"])
    
    prizes = Prize.query.order_by(Prize.created_at.desc()).all()
    for pr in prizes:
        writer.writerow([
            pr.id, pr.tournament.name if pr.tournament else "",
            pr.team.name if pr.team else "", pr.rank, str(pr.amount),
            pr.status, pr.reference_id or "",
            pr.payment_date.strftime("%Y-%m-%d %H:%M") if pr.payment_date else ""
        ])
    return output.getvalue()


def generate_disputes_csv():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Dispute ID", "Match ID", "Tournament", "Team Name", "Reason", "Status", "Created At", "Resolution Note"])
    
    disputes = Dispute.query.order_by(Dispute.created_at.desc()).all()
    for d in disputes:
        writer.writerow([
            d.id, d.match_id,
            d.match.tournament.name if d.match and d.match.tournament else "",
            d.team.name if d.team else "", d.reason, d.status,
            d.created_at.strftime("%Y-%m-%d %H:%M") if d.created_at else "",
            d.resolution_note or ""
        ])
    return output.getvalue()


# ─────────────────────────────────────────────
# PDF Generators (ReportLab)
# ─────────────────────────────────────────────

def _build_pdf(title, headers, data, is_landscape=False):
    buffer = io.BytesIO()
    pagesize = landscape(letter) if is_landscape else letter
    doc = SimpleDocTemplate(
        buffer,
        pagesize=pagesize,
        rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30
    )
    elements = []
    styles = getSampleStyleSheet()

    # Title
    title_style = ParagraphStyle(
        'TitleStyle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#ff3860'),
        fontName='Helvetica-Bold',
        spaceAfter=6,
    )
    elements.append(Paragraph(f"FF CUSTOM ARENA — {title}", title_style))

    # Meta
    meta_style = ParagraphStyle(
        'MetaStyle',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor('#666666'),
        spaceAfter=15,
    )
    elements.append(Paragraph(f"Generated on {datetime.utcnow().strftime('%d %B %Y, %I:%M %p UTC')} | Confidential Official Platform Report", meta_style))

    # Table
    table_data = [headers]
    for row in data:
        table_data.append([str(c) if c is not None else "" for c in row])

    t = Table(table_data, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#161922')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#ffffff')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ('TOPPADDING', (0, 0), (-1, 0), 6),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e0e0e0')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#ffffff'), colors.HexColor('#f9f9f9')]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(t)
    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()


def generate_users_pdf():
    users = User.query.order_by(User.id.asc()).all()
    headers = ["ID", "Full Name", "Username", "Email", "Phone", "Role", "Active", "Joined"]
    data = [
        [u.id, u.full_name, f"@{u.username}", u.email, u.phone or "—", u.role_name.replace('_', ' ').title(), "Yes" if u.is_active_account else "No", u.created_at.strftime("%d/%m/%Y") if u.created_at else ""]
        for u in users
    ]
    return _build_pdf("Users & Players Directory", headers, data, is_landscape=True)


def generate_teams_pdf():
    teams = Team.query.order_by(Team.id.asc()).all()
    headers = ["ID", "Team Name", "Tag", "Captain", "Members", "Active", "Created"]
    data = [
        [t.id, t.name, t.tag or "—", f"@{t.captain.username}" if t.captain else "—", t.members.count(), "Yes" if t.is_active else "No", t.created_at.strftime("%d/%m/%Y") if t.created_at else ""]
        for t in teams
    ]
    return _build_pdf("Teams & Rosters Report", headers, data)


def generate_tournaments_pdf():
    tournaments = Tournament.query.order_by(Tournament.start_time.desc()).all()
    headers = ["ID", "Name", "Mode", "Map", "Status", "Slots", "Fee (₹)", "Prize (₹)", "Start Time"]
    data = [
        [t.id, t.name[:25], t.game_mode or "BR", t.map_name or "Bermuda", t.status.replace('_', ' ').title(), f"{t.registered_team_count}/{t.max_teams}", str(t.entry_fee), str(t.prize_pool), t.start_time.strftime("%d/%m/%y %H:%M")]
        for t in tournaments
    ]
    return _build_pdf("Tournaments Master Report", headers, data, is_landscape=True)


def generate_registrations_pdf(tournament_id=None):
    query = TournamentRegistration.query
    if tournament_id:
        query = query.filter_by(tournament_id=tournament_id)
    regs = query.order_by(TournamentRegistration.created_at.desc()).all()
    headers = ["Reg Code", "Tournament", "Team Name", "Captain", "Status", "Date"]
    data = [
        [r.registration_code, r.tournament.name[:25], r.team.name, f"@{r.team.captain.username}" if r.team and r.team.captain else "—", r.status.title(), r.created_at.strftime("%d/%m/%y %H:%M") if r.created_at else ""]
        for r in regs
    ]
    return _build_pdf("Registrations & Slots Report", headers, data)


def generate_payments_pdf():
    payments = Payment.query.order_by(Payment.created_at.desc()).all()
    headers = ["ID", "Reg Code", "Tournament", "Team", "Amount (₹)", "Method", "Txn ID", "Status", "Date"]
    data = [
        [p.id, p.registration.registration_code if p.registration else "—", p.registration.tournament.name[:20] if p.registration and p.registration.tournament else "—", p.registration.team.name if p.registration and p.registration.team else "—", str(p.amount), p.payment_method or "UPI", p.transaction_id or "—", p.status.title(), p.created_at.strftime("%d/%m/%y") if p.created_at else ""]
        for p in payments
    ]
    return _build_pdf("Financial & Payments Ledger", headers, data, is_landscape=True)


def generate_results_pdf(tournament_id=None):
    query = MatchResult.query.join(Match)
    if tournament_id:
        query = query.filter(Match.tournament_id == tournament_id)
    results = query.order_by(Match.scheduled_date.desc(), MatchResult.placement.asc()).all()
    headers = ["ID", "Tournament", "Round", "Match", "Team", "Place", "Kills", "Place Pts", "Kill Pts", "Total Pts", "Status"]
    data = [
        [r.id, r.match.tournament.name[:20] if r.match and r.match.tournament else "—", r.match.round_number if r.match else 1, f"#{r.match.match_number}" if r.match else "—", r.team.name if r.team else "—", f"#{r.placement}", r.kills, r.placement_points, r.kill_points, r.total_points, r.status.title()]
        for r in results
    ]
    return _build_pdf("Match Results & Scores Report", headers, data, is_landscape=True)


def generate_prizes_pdf():
    prizes = Prize.query.order_by(Prize.created_at.desc()).all()
    headers = ["ID", "Tournament", "Team Name", "Rank", "Amount (₹)", "Status", "Ref ID", "Paid Date"]
    data = [
        [pr.id, pr.tournament.name[:25] if pr.tournament else "—", pr.team.name if pr.team else "—", f"#{pr.rank}", str(pr.amount), pr.status.title(), pr.reference_id or "—", pr.payment_date.strftime("%d/%m/%y") if pr.payment_date else "—"]
        for pr in prizes
    ]
    return _build_pdf("Prize Distributions Report", headers, data)


def generate_disputes_pdf():
    disputes = Dispute.query.order_by(Dispute.created_at.desc()).all()
    headers = ["ID", "Tournament", "Match", "Team", "Reason", "Status", "Resolution Note", "Date"]
    data = [
        [d.id, d.match.tournament.name[:20] if d.match and d.match.tournament else "—", f"#{d.match.match_number}" if d.match else "—", d.team.name if d.team else "—", d.reason[:30], d.status.replace('_', ' ').title(), d.resolution_note or "—", d.created_at.strftime("%d/%m/%y") if d.created_at else ""]
        for d in disputes
    ]
    return _build_pdf("Disputes Moderation Log", headers, data, is_landscape=True)
