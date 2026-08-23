import os
from datetime import datetime, date, timezone
from decimal import Decimal
from typing import List, Tuple
from sqlalchemy.orm import Session

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
    KeepTogether
)

from app.models.wallet import Wallet
from app.models.user import User
from app.models.ledger import LedgerPosting, PostingDirection
from app.config import settings

CURRENCY_SYMBOLS = {
    "USD": "$",
    "GBP": "£",
    "GHS": "GH₵",
}


class PDFStatementService:
    @staticmethod
    def _format_currency(amount: Decimal, currency: str) -> str:
        symbol = CURRENCY_SYMBOLS.get(currency.upper(), currency.upper() + " ")
        return f"{symbol}{amount:,.2f}"

    @classmethod
    def generate_statement_pdf(
        cls,
        db: Session,
        wallet_id: int,
        start_date: date,
        end_date: date,
        output_dir: str = settings.STORAGE_DIR
    ) -> Tuple[str, str, int]:
        """
        Generates a monthly/date-range bank statement PDF for a given wallet.
        Returns: (filepath, filename, file_size_bytes)
        """
        os.makedirs(output_dir, exist_ok=True)

        wallet = db.query(Wallet).filter(Wallet.id == wallet_id).first()
        if not wallet:
            raise ValueError(f"Wallet #{wallet_id} not found")

        user = db.query(User).filter(User.id == wallet.user_id).first()
        currency = wallet.currency.upper()

        # Convert date boundaries to datetime
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())

        # Retrieve prior postings to compute opening balance
        prior_postings = db.query(LedgerPosting).filter(
            LedgerPosting.wallet_id == wallet_id,
            LedgerPosting.created_at < start_dt
        ).order_by(LedgerPosting.created_at.asc()).all()

        opening_balance = Decimal("0.0000")
        for p in prior_postings:
            if p.direction == PostingDirection.DEBIT:
                opening_balance += p.amount
            else:
                opening_balance -= p.amount

        # Retrieve postings in range
        postings = db.query(LedgerPosting).filter(
            LedgerPosting.wallet_id == wallet_id,
            LedgerPosting.created_at >= start_dt,
            LedgerPosting.created_at <= end_dt
        ).order_by(LedgerPosting.created_at.asc()).all()

        total_inflows = Decimal("0.0000")
        total_outflows = Decimal("0.0000")

        running_balance = opening_balance
        table_rows = [
            ["Date & Time", "Reference / Description", "Type", "Amount", "Balance"]
        ]

        for p in postings:
            journal = p.journal_entry
            ref = journal.reference_id if journal else f"TX-{p.id}"
            desc = journal.description if journal else "Ledger Adjustment"
            tx_type = journal.entry_type.value if journal else "TRANSFER"

            if p.direction == PostingDirection.DEBIT:
                # Inflow to user wallet
                total_inflows += p.amount
                running_balance += p.amount
                amount_str = f"+{cls._format_currency(p.amount, currency)}"
            else:
                # Outflow from user wallet
                total_outflows += p.amount
                running_balance -= p.amount
                amount_str = f"-{cls._format_currency(p.amount, currency)}"

            date_str = p.created_at.strftime("%Y-%m-%d %H:%M")
            table_rows.append([
                date_str,
                f"{desc}\n(Ref: {ref})",
                tx_type,
                amount_str,
                cls._format_currency(running_balance, currency)
            ])

        closing_balance = running_balance

        # File creation
        filename = f"statement_{wallet.user_id}_{currency}_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.pdf"
        filepath = os.path.join(output_dir, filename)

        doc = SimpleDocTemplate(
            filepath,
            pagesize=letter,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36
        )

        styles = getSampleStyleSheet()
        primary_color = colors.HexColor("#1A365D")  # Deep Navy Blue
        accent_color = colors.HexColor("#2B6CB0")   # Slate Blue
        neutral_bg = colors.HexColor("#F7FAFC")     # Off-white

        header_title_style = ParagraphStyle(
            "HeaderTitle",
            parent=styles["Heading1"],
            fontSize=20,
            leading=24,
            textColor=primary_color,
            fontName="Helvetica-Bold"
        )
        
        sub_style = ParagraphStyle(
            "SubStyle",
            parent=styles["Normal"],
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#4A5568")
        )

        section_title_style = ParagraphStyle(
            "SectionTitle",
            parent=styles["Heading2"],
            fontSize=12,
            leading=16,
            textColor=primary_color,
            fontName="Helvetica-Bold",
            spaceAfter=6
        )

        elements = []

        # 1. Header Banner
        header_data = [
            [
                Paragraph("<b>ANTIGRAVITY FINTECH</b><br/><font size=8 color='#718096'>Global Multi-Currency Ledger Systems</font>", styles["Normal"]),
                Paragraph("<b>OFFICIAL ACCOUNT STATEMENT</b>", header_title_style)
            ]
        ]
        header_table = Table(header_data, colWidths=[270, 270])
        header_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ]))
        elements.append(header_table)
        elements.append(Spacer(1, 12))
        elements.append(HRFlowable(width="100%", thickness=1.5, color=primary_color, spaceAfter=15))

        # 2. Account & Period Information Box
        now_str = datetime.now(timezone.utc).strftime('%b %d, %Y %H:%M UTC')
        info_data = [
            [
                Paragraph(f"<b>Account Holder:</b> {user.full_name if user else 'Customer'}<br/>"
                          f"<b>Email:</b> {user.email if user else 'N/A'}<br/>"
                          f"<b>Wallet ID:</b> #{wallet.id} ({currency})", sub_style),
                Paragraph(f"<b>Statement Period:</b> {start_date.strftime('%b %d, %Y')} - {end_date.strftime('%b %d, %Y')}<br/>"
                          f"<b>Generated On:</b> {now_str}<br/>"
                          f"<b>Currency:</b> {currency} ({CURRENCY_SYMBOLS.get(currency, currency)})", sub_style)
            ]
        ]
        info_table = Table(info_data, colWidths=[270, 270])
        info_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), neutral_bg),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#E2E8F0")),
            ('PADDING', (0, 0), (-1, -1), 8),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        elements.append(info_table)
        elements.append(Spacer(1, 15))

        # 3. Financial Summary Card
        summary_data = [
            [
                Paragraph("<b>Opening Balance</b>", sub_style),
                Paragraph("<b>Total Inflows</b>", sub_style),
                Paragraph("<b>Total Outflows</b>", sub_style),
                Paragraph("<b>Closing Balance</b>", sub_style)
            ],
            [
                Paragraph(f"<b>{cls._format_currency(opening_balance, currency)}</b>", header_title_style),
                Paragraph(f"<font color='#38A169'><b>+{cls._format_currency(total_inflows, currency)}</b></font>", header_title_style),
                Paragraph(f"<font color='#E53E3E'><b>-{cls._format_currency(total_outflows, currency)}</b></font>", header_title_style),
                Paragraph(f"<b>{cls._format_currency(closing_balance, currency)}</b>", header_title_style),
            ]
        ]
        summary_table = Table(summary_data, colWidths=[135, 135, 135, 135])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#EDF2F7")),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#CBD5E0")),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(summary_table)
        elements.append(Spacer(1, 20))

        # 4. Detailed Transactions Table
        elements.append(Paragraph("Itemized Transaction Ledger", section_title_style))

        if len(table_rows) == 1:
            elements.append(Paragraph("<i>No transactions recorded in this period.</i>", sub_style))
        else:
            cell_style = ParagraphStyle(
                "CellStyle",
                parent=styles["Normal"],
                fontSize=8,
                leading=10,
                textColor=colors.HexColor("#2D3748")
            )
            formatted_table_rows = []
            # Header row
            formatted_table_rows.append([
                Paragraph(f"<b>{h}</b>", cell_style) for h in table_rows[0]
            ])
            # Data rows
            for row in table_rows[1:]:
                formatted_table_rows.append([
                    Paragraph(row[0], cell_style),
                    Paragraph(row[1].replace("\n", "<br/>"), cell_style),
                    Paragraph(row[2], cell_style),
                    Paragraph(row[3], cell_style),
                    Paragraph(row[4], cell_style)
                ])

            tx_table = Table(
                formatted_table_rows,
                colWidths=[85, 235, 75, 75, 70]
            )
            tx_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), accent_color),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7FAFC")]),
                ('PADDING', (0, 0), (-1, -1), 5),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ]))
            elements.append(tx_table)

        elements.append(Spacer(1, 25))

        # 5. Footer Notice
        footer_notice = Paragraph(
            "<font size=7 color='#A0AEC0'>This document is an electronically generated statement certified by Antigravity FinTech Ledger Engine. All transactions are cryptographically verified and backed by strict double-entry ledger balance invariants. Questions? Contact support@antigravity-fintech.io.</font>",
            sub_style
        )
        elements.append(KeepTogether([footer_notice]))

        # Build document
        doc.build(elements)

        file_size = os.path.getsize(filepath)
        return filepath, filename, file_size
