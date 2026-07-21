import uuid
from datetime import datetime
from lxml import etree
from odoo.exceptions import UserError #type: ignore

# =====================================================
# UTILITIES
# =====================================================

def safe_text(value, fallback=""):
    if value in (None, False, ""):
        return str(fallback)
    return str(value)

UAE_FTA_TAX_CODES = {
    0.0: "Z",
    5.0: "S"
}

# =====================================================
# MAIN ENTRY POINT
# =====================================================

def build_xml_payload(move) -> str:
    env = move.env
    invoice = _get_invoice_data(move)
    partner = _get_partner_data(move)
    company = _get_company_data(move)
    lines = _get_line_data(move)
    journal = _get_journal_data(move)
    currency_code, exchange_rate = _get_currency_data(move, env)
    doc_meta = detect_document_type(invoice, journal)
    tax_totals = build_tax_totals(lines, env)

    ctx = {
        "invoice": invoice,
        "partner": partner,
        "company": company,
        "lines": lines,
        "tax_totals": tax_totals,
        "env": env,
        "totals": {
            "line_net": abs(float(move.amount_untaxed)),
            "tax": abs(float(move.amount_tax)),
            "total": abs(float(move.amount_total)),
        },
        "issue_date": str(move.invoice_date) if move.invoice_date
                      else datetime.utcnow().date().isoformat(),
        "due_date": str(move.invoice_date_due) if move.invoice_date_due
                    else str(move.invoice_date),
        "exchange_rate": exchange_rate,
        "currency_code": currency_code,
        "is_multi_currency": currency_code != "AED",
    }

    root = build_sbdh_root(ctx, doc_meta)
    build_document(root, ctx, doc_meta)

    xml_payload = etree.tostring(
        root, pretty_print=True,
        xml_declaration=True, encoding="UTF-8"
    )
    return xml_payload.decode("utf-8")

# =====================================================
# DATA FETCHERS
# =====================================================

def _get_invoice_data(move):
    return {
        "name": move.name,
        "move_type": move.move_type,
        "invoice_date": str(move.invoice_date) if move.invoice_date else None,
        "invoice_date_due": str(move.invoice_date_due) if move.invoice_date_due else None,
        "amount_untaxed": float(move.amount_untaxed),
        "amount_tax": float(move.amount_tax),
        "amount_total": float(move.amount_total),
        "currency_id": [move.currency_id.id, move.currency_id.name] if move.currency_id else None,
        "reversed_entry_id": [move.reversed_entry_id.id, move.reversed_entry_id.name]
                              if move.reversed_entry_id else False,
        "ref": move.ref or "",
    }

def _get_partner_data(move):
    p = move.partner_id
    return {
        "name": p.name, "vat": p.vat or "",
        "street": p.street or "", "city": p.city or "",
        "zip": p.zip or "", "phone": p.phone or "",
        "email": p.email or "",
        "country_code": p.country_id.code if p.country_id else "",
        "state_code": p.state_id.code if p.state_id else "",
    }

def _get_company_data(move):
    c = move.company_id
    return {
        "name": c.name, "vat": c.vat or "",
        "street": c.street or "", "city": c.city or "",
        "zip": c.zip or "", "phone": c.phone or "",
        "email": c.email or "",
        "country_code": c.country_id.code if c.country_id else "",
        "state_code": c.state_id.code if c.state_id else "",
    }

def _get_line_data(move):
    lines = []
    for line in move.invoice_line_ids:
        lines.append({
            "name": line.name,
            "quantity": float(line.quantity),
            "price_unit": float(line.price_unit),
            "price_subtotal": float(line.price_subtotal),
            "price_total": float(line.price_total),
            "tax_ids": line.tax_ids.ids,
        })
    return lines

def _get_journal_data(move):
    return {
        "is_self_billing": move.journal_id.is_self_billing
        if hasattr(move.journal_id, 'is_self_billing') else False,
    }

def _get_currency_data(move, env):
    currency_code = move.currency_id.name if move.currency_id else "AED"
    exchange_rate = 1.0
    if currency_code != "AED":
        source_rates = env['res.currency.rate'].search(
            [('currency_id', '=', move.currency_id.id)],
            order='name desc', limit=1
        )
        aed_currency = env['res.currency'].search([('name', '=', 'AED')], limit=1)
        aed_rates = env['res.currency.rate'].search(
            [('currency_id', '=', aed_currency.id)],
            order='name desc', limit=1
        )
        if source_rates and aed_rates:
            exchange_rate = aed_rates[0].rate / source_rates[0].rate
    return currency_code, exchange_rate

# =====================================================
# TAX DETAILS
# =====================================================

def get_tax_details(tax_ids, env):
    if not tax_ids:
        return {"rate": 0.0, "code": "Z"}
    if isinstance(tax_ids[0], list):
        tax_id_list = tax_ids[0][2]
    else:
        tax_id_list = tax_ids
    taxes = env['account.tax'].browse(tax_id_list)
    rate = round(abs(float(taxes[0].amount)), 1) if taxes else 0.0
    return {"rate": rate, "code": UAE_FTA_TAX_CODES.get(rate, "Z")}

def build_tax_totals(lines, env):
    totals = {}
    for line in lines:
        tax = get_tax_details(line.get("tax_ids"), env)
        net = abs(float(line["price_subtotal"]))
        tax_amt = abs(float(line["price_total"]) - net)
        if tax["code"] not in totals:
            totals[tax["code"]] = {"base": 0.0, "tax": 0.0, "rate": tax["rate"]}
        totals[tax["code"]]["base"] += net
        totals[tax["code"]]["tax"] += tax_amt
    for k in totals:
        totals[k]["base"] = round(totals[k]["base"], 2)
        totals[k]["tax"] = round(totals[k]["tax"], 2)
    return totals

# =====================================================
# DOCUMENT TYPE DETECTION
# =====================================================

def detect_document_type(invoice, journal):
    is_self = journal.get("is_self_billing")
    move_type = invoice.get("move_type")
    if is_self and move_type == "in_refund":
        return {"doc_type": "CreditNote", "ubl_root": "CreditNote", "type_code": "261"}
    if move_type == "out_refund":
        return {"doc_type": "CreditNote", "ubl_root": "CreditNote", "type_code": "381"}
    if is_self:
        return {"doc_type": "Invoice", "ubl_root": "Invoice", "type_code": "389"}
    return {"doc_type": "Invoice", "ubl_root": "Invoice", "type_code": "380"}

# =====================================================
# XML BUILDERS
# =====================================================

def add_business_scope(sbdh, doc_meta):
    bs = etree.SubElement(sbdh, "BusinessScope")
    profile_type = "selfbilling" if doc_meta["type_code"] in ["389", "261"] else "billing"

    scope = etree.SubElement(bs, "Scope")
    etree.SubElement(scope, "Type").text = "DOCUMENTID"
    etree.SubElement(scope, "InstanceIdentifier").text = (
        f"urn:oasis:names:specification:ubl:schema:xsd:"
        f"{doc_meta['ubl_root']}-2::{doc_meta['doc_type']}##"
        f"urn:peppol:pint:{profile_type}-1@ae-1::2.1"
    )
    etree.SubElement(scope, "Identifier").text = "peppol-doctype-wildcard"

    scope = etree.SubElement(bs, "Scope")
    etree.SubElement(scope, "Type").text = "PROCESSID"
    etree.SubElement(scope, "InstanceIdentifier").text = f"urn:peppol:bis:{profile_type}"
    etree.SubElement(scope, "Identifier").text = "cenbii-procid-ubl"

    scope = etree.SubElement(bs, "Scope")
    etree.SubElement(scope, "Type").text = "COUNTRY_C1"
    etree.SubElement(scope, "InstanceIdentifier").text = "AE"

    scope = etree.SubElement(bs, "Scope")
    etree.SubElement(scope, "Type").text = "MLS_TO"
    etree.SubElement(scope, "InstanceIdentifier").text = "0242:000539"
    etree.SubElement(scope, "Identifier").text = "iso6523-actorid-upis"

    scope = etree.SubElement(bs, "Scope")
    etree.SubElement(scope, "Type").text = "MLS_TYPE"
    etree.SubElement(scope, "InstanceIdentifier").text = "ALWAYS_SEND"


def build_sbdh_root(ctx, doc_meta):
    root = etree.Element(
        "StandardBusinessDocument",
        nsmap={None: "http://www.unece.org/cefact/namespaces/StandardBusinessDocumentHeader"}
    )
    sbdh = etree.SubElement(root, "StandardBusinessDocumentHeader")
    etree.SubElement(sbdh, "HeaderVersion").text = "1.0"

    sender_vat = ctx['company'].get('vat')
    receiver_vat = ctx['partner'].get('vat')

    sender = etree.SubElement(sbdh, "Sender")
    etree.SubElement(sender, "Identifier",
                     Authority="iso6523-actorid-upis").text = f"0235:{safe_text(sender_vat)}"

    receiver = etree.SubElement(sbdh, "Receiver")
    etree.SubElement(receiver, "Identifier",
                     Authority="iso6523-actorid-upis").text = f"0235:{safe_text(receiver_vat)}"

    doc = etree.SubElement(sbdh, "DocumentIdentification")
    etree.SubElement(doc, "Standard").text = (
        f"urn:oasis:names:specification:ubl:schema:xsd:{doc_meta['ubl_root']}-2"
    )
    etree.SubElement(doc, "TypeVersion").text = "2.1"
    etree.SubElement(doc, "InstanceIdentifier").text = ctx["invoice"]["name"]
    etree.SubElement(doc, "Type").text = doc_meta["doc_type"]
    etree.SubElement(doc, "CreationDateAndTime").text = datetime.utcnow().isoformat()

    add_business_scope(sbdh, doc_meta)
    return root


def build_party(parent, data, NS):
    party = etree.SubElement(parent, f"{{{NS['cac']}}}Party")
    vat = safe_text(data.get("vat"))
    etree.SubElement(party, f"{{{NS['cbc']}}}EndpointID", schemeID="0235").text = vat

    pname = etree.SubElement(party, f"{{{NS['cac']}}}PartyName")
    etree.SubElement(pname, f"{{{NS['cbc']}}}Name").text = safe_text(data.get("name"))

    address = etree.SubElement(party, f"{{{NS['cac']}}}PostalAddress")
    etree.SubElement(address, f"{{{NS['cbc']}}}StreetName").text = safe_text(data.get("street"))
    etree.SubElement(address, f"{{{NS['cbc']}}}CityName").text = safe_text(data.get("city"))
    etree.SubElement(address, f"{{{NS['cbc']}}}PostalZone").text = safe_text(data.get("zip"))

    country_code = data.get("country_code")
    state_code = data.get("state_code")
    if state_code:
        if country_code == "AE":
            valid_emirates = ["DXB", "AUH", "SHJ", "UAQ", "FUJ", "AJM", "RAK"]
            if state_code not in valid_emirates:
                state_code = "DXB"
        etree.SubElement(address, f"{{{NS['cbc']}}}CountrySubentity").text = safe_text(state_code)

    country = etree.SubElement(address, f"{{{NS['cac']}}}Country")
    etree.SubElement(country, f"{{{NS['cbc']}}}IdentificationCode").text = safe_text(country_code)

    tax_scheme = etree.SubElement(party, f"{{{NS['cac']}}}PartyTaxScheme")
    etree.SubElement(tax_scheme, f"{{{NS['cbc']}}}CompanyID").text = vat
    ts = etree.SubElement(tax_scheme, f"{{{NS['cac']}}}TaxScheme")
    etree.SubElement(ts, f"{{{NS['cbc']}}}ID").text = "VAT"

    legal = etree.SubElement(party, f"{{{NS['cac']}}}PartyLegalEntity")
    etree.SubElement(legal, f"{{{NS['cbc']}}}RegistrationName").text = safe_text(data.get("name"))
    etree.SubElement(legal, f"{{{NS['cbc']}}}CompanyID",
                     schemeAgencyID="TL",
                     schemeAgencyName="Trade License issuing Authority").text = vat

    contact = etree.SubElement(party, f"{{{NS['cac']}}}Contact")
    etree.SubElement(contact, f"{{{NS['cbc']}}}Telephone").text = safe_text(data.get("phone"))
    etree.SubElement(contact, f"{{{NS['cbc']}}}ElectronicMail").text = safe_text(data.get("email"))


def add_document_lines(parent, ctx, doc_meta, NS):
    env = ctx["env"]
    for idx, line in enumerate(ctx["lines"], start=1):
        is_credit = doc_meta["type_code"] in ["381", "261"]
        line_tag = "CreditNoteLine" if is_credit else "InvoiceLine"
        qty_tag = "CreditedQuantity" if is_credit else "InvoicedQuantity"

        ln = etree.SubElement(parent, f"{{{NS['cac']}}}{line_tag}")
        etree.SubElement(ln, f"{{{NS['cbc']}}}ID").text = str(idx)
        etree.SubElement(ln, f"{{{NS['cbc']}}}Note").text = "0"

        # qty = abs(float(line.get("quantity", 1)))
        qty = abs(float(line.get("quantity", 0)) or 0)
        etree.SubElement(ln, f"{{{NS['cbc']}}}{qty_tag}", unitCode="EA").text = f"{qty:.1f}"

        rate = ctx.get("exchange_rate", 1)
        # line_net = abs(float(line.get("price_subtotal", 0)))
        # raw_total = abs(float(line.get("price_total", 0)))
        # line_tax = raw_total - line_net
        unit_price = abs(float(line.get("price_unit", 0)))
        line_net = round(qty * unit_price, 2)
        # line_tax = round(abs(float(line.get("price_total", 0))) - line_net, 2)
        tax_info = get_tax_details(line.get("tax_ids", []), env)
        line_tax = round(line_net * (tax_info["rate"] / 100), 2)

        etree.SubElement(ln, f"{{{NS['cbc']}}}LineExtensionAmount",
                         currencyID=ctx["currency_code"]).text = f"{line_net:.2f}"

        line_tax_total = etree.SubElement(ln, f"{{{NS['cac']}}}TaxTotal")
        etree.SubElement(line_tax_total, f"{{{NS['cbc']}}}TaxAmount",
                         currencyID="AED").text = f"{line_tax * rate:.2f}"

        item = etree.SubElement(ln, f"{{{NS['cac']}}}Item")
        etree.SubElement(item, f"{{{NS['cbc']}}}Description").text = safe_text(line.get("name"))
        etree.SubElement(item, f"{{{NS['cbc']}}}Name").text = safe_text(line.get("name"))

        tax_info = get_tax_details(line.get("tax_ids", []), env)
        item_tax = etree.SubElement(item, f"{{{NS['cac']}}}ClassifiedTaxCategory")
        etree.SubElement(item_tax, f"{{{NS['cbc']}}}ID").text = tax_info["code"]
        etree.SubElement(item_tax, f"{{{NS['cbc']}}}Percent").text = f"{tax_info['rate']:.1f}"
        item_tax_scheme = etree.SubElement(item_tax, f"{{{NS['cac']}}}TaxScheme")
        etree.SubElement(item_tax_scheme, f"{{{NS['cbc']}}}ID").text = "VAT"

        price = etree.SubElement(ln, f"{{{NS['cac']}}}Price")
        # net_unit_price = round(line_net / qty if qty > 0 else 0, 2)
        net_unit_price = unit_price
        # etree.SubElement(price, f"{{{NS['cbc']}}}PriceAmount",
        #                  currencyID=ctx["currency_code"]).text = f"{net_unit_price:.2f}"
        # etree.SubElement(price, f"{{{NS['cbc']}}}BaseQuantity",
        #                  unitCode="EA").text = f"{qty:.1f}"
        # etree.SubElement(price, f"{{{NS['cbc']}}}PriceAmount",
        #                 currencyID=ctx["currency_code"]).text = f"{line_net:.2f}"
        # ✅ to this
        etree.SubElement(price, f"{{{NS['cbc']}}}PriceAmount",
                currencyID=ctx["currency_code"]).text = f"{unit_price:.2f}"

        etree.SubElement(price, f"{{{NS['cbc']}}}BaseQuantity",
                        unitCode="EA").text = "1.0"

        allowance = etree.SubElement(price, f"{{{NS['cac']}}}AllowanceCharge")
        etree.SubElement(allowance, f"{{{NS['cbc']}}}ChargeIndicator").text = "false"
        etree.SubElement(allowance, f"{{{NS['cbc']}}}Amount",
                         currencyID=ctx["currency_code"]).text = "0.00"
        # etree.SubElement(allowance, f"{{{NS['cbc']}}}BaseAmount",
        #                  currencyID=ctx["currency_code"]).text = f"{line_net:.2f}"
        etree.SubElement(allowance, f"{{{NS['cbc']}}}BaseAmount",
                 currencyID=ctx["currency_code"]).text = f"{unit_price:.2f}"

        item_price_ext = etree.SubElement(ln, f"{{{NS['cac']}}}ItemPriceExtension")
        etree.SubElement(item_price_ext, f"{{{NS['cbc']}}}Amount",
                         currencyID=ctx["currency_code"]).text = f"{line_net:.2f}"
        line_price_tax_total = etree.SubElement(item_price_ext, f"{{{NS['cac']}}}TaxTotal")
        # etree.SubElement(line_price_tax_total, f"{{{NS['cbc']}}}TaxAmount",
        #                  currencyID=ctx["currency_code"]).text = f"{line_tax:.2f}"
        etree.SubElement(line_price_tax_total, f"{{{NS['cbc']}}}TaxAmount",
                 currencyID="AED").text = f"{line_tax:.2f}"


def add_tax_total(parent, ctx, NS):
    tax_total = etree.SubElement(parent, f"{{{NS['cac']}}}TaxTotal")
    etree.SubElement(tax_total, f"{{{NS['cbc']}}}TaxAmount",
                     currencyID=ctx["currency_code"]).text = f"{ctx['totals']['tax']:.2f}"

    for code, t in ctx["tax_totals"].items():
        sub = etree.SubElement(tax_total, f"{{{NS['cac']}}}TaxSubtotal")
        etree.SubElement(sub, f"{{{NS['cbc']}}}TaxableAmount",
                         currencyID=ctx["currency_code"]).text = f"{t['base']:.2f}"
        etree.SubElement(sub, f"{{{NS['cbc']}}}TaxAmount",
                         currencyID=ctx["currency_code"]).text = f"{t['tax']:.2f}"
        cat = etree.SubElement(sub, f"{{{NS['cac']}}}TaxCategory")
        etree.SubElement(cat, f"{{{NS['cbc']}}}ID").text = code
        etree.SubElement(cat, f"{{{NS['cbc']}}}Percent").text = f"{t['rate']:.1f}"
        scheme = etree.SubElement(cat, f"{{{NS['cac']}}}TaxScheme")
        etree.SubElement(scheme, f"{{{NS['cbc']}}}ID").text = "VAT"

    if ctx["currency_code"] != "AED":
        tax_total_aed = etree.SubElement(parent, f"{{{NS['cac']}}}TaxTotal")
        aed_tax = ctx['totals']['tax'] * ctx['exchange_rate']
        etree.SubElement(tax_total_aed, f"{{{NS['cbc']}}}TaxAmount",
                         currencyID="AED").text = f"{aed_tax:.2f}"


def add_monetary_total(parent, ctx, NS, credit=False):
    mt = etree.SubElement(parent, f"{{{NS['cac']}}}LegalMonetaryTotal")
    etree.SubElement(mt, f"{{{NS['cbc']}}}LineExtensionAmount",
                     currencyID=ctx["currency_code"]).text = f"{ctx['totals']['line_net']:.2f}"
    etree.SubElement(mt, f"{{{NS['cbc']}}}TaxExclusiveAmount",
                     currencyID=ctx["currency_code"]).text = f"{ctx['totals']['line_net']:.2f}"
    etree.SubElement(mt, f"{{{NS['cbc']}}}TaxInclusiveAmount",
                     currencyID=ctx["currency_code"]).text = f"{ctx['totals']['total']:.2f}"
    if credit:
        etree.SubElement(mt, f"{{{NS['cbc']}}}PrepaidAmount",
                         currencyID=ctx["currency_code"]).text = "0.00"
        etree.SubElement(mt, f"{{{NS['cbc']}}}PayableRoundingAmount",
                         currencyID=ctx["currency_code"]).text = "0.00"
    etree.SubElement(mt, f"{{{NS['cbc']}}}PayableAmount",
                     currencyID=ctx["currency_code"]).text = f"{ctx['totals']['total']:.2f}"


def build_document(root, ctx, doc_meta):
    NS = {
        None: f"urn:oasis:names:specification:ubl:schema:xsd:{doc_meta['ubl_root']}-2",
        "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
        "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    }
    doc = etree.SubElement(root, doc_meta["doc_type"], nsmap=NS)
    profile_type = "selfbilling" if doc_meta["type_code"] in ["389", "261"] else "billing"

    etree.SubElement(doc, f"{{{NS['cbc']}}}CustomizationID").text = f"urn:peppol:pint:{profile_type}-1@ae-1"
    etree.SubElement(doc, f"{{{NS['cbc']}}}ProfileID").text = f"urn:peppol:bis:{profile_type}"
    etree.SubElement(doc, f"{{{NS['cbc']}}}ProfileExecutionID").text = "00000000"
    etree.SubElement(doc, f"{{{NS['cbc']}}}ID").text = ctx["invoice"]["name"]
    etree.SubElement(doc, f"{{{NS['cbc']}}}UUID").text = str(uuid.uuid4())
    etree.SubElement(doc, f"{{{NS['cbc']}}}IssueDate").text = ctx["issue_date"]

    if doc_meta["type_code"] in ["380", "389"]:
        etree.SubElement(doc, f"{{{NS['cbc']}}}DueDate").text = ctx["due_date"]

    if doc_meta["type_code"] in ["380", "389"]:
        etree.SubElement(doc, f"{{{NS['cbc']}}}InvoiceTypeCode").text = doc_meta["type_code"]
    else:
        etree.SubElement(doc, f"{{{NS['cbc']}}}CreditNoteTypeCode").text = doc_meta["type_code"]

    etree.SubElement(doc, f"{{{NS['cbc']}}}DocumentCurrencyCode").text = ctx["currency_code"]

    # --- Step 1: TaxCurrencyCode only (AdditionalDocumentReference moved further down) ---
    if ctx["currency_code"] != "AED":
        etree.SubElement(doc, f"{{{NS['cbc']}}}TaxCurrencyCode").text = "AED"

    # --- Step 2: Credit note specific blocks, DiscrepancyResponse BEFORE BillingReference ---
    if doc_meta["type_code"] in ["381", "261"]:

        disc = etree.SubElement(doc, f"{{{NS['cac']}}}DiscrepancyResponse")
        etree.SubElement(disc, f"{{{NS['cbc']}}}ResponseCode").text = (
            "DL8.61.1.E" if doc_meta["type_code"] == "261" else "DL8.61.1.A"
        )
        etree.SubElement(disc, f"{{{NS['cbc']}}}Description").text = safe_text(
            ctx["invoice"].get("ref") or "Credit Note"
        )

        billing_ref = etree.SubElement(doc, f"{{{NS['cac']}}}BillingReference")
        inv_ref = etree.SubElement(billing_ref, f"{{{NS['cac']}}}InvoiceDocumentReference")
        original_move = ctx["invoice"].get("reversed_entry_id")
        if original_move:
            env = ctx["env"]
            original_invoice = env['account.move'].browse(original_move[0])
            original_date = str(original_invoice.invoice_date) \
                            if original_invoice.invoice_date else ctx["issue_date"]
            etree.SubElement(inv_ref, f"{{{NS['cbc']}}}ID").text = safe_text(original_move[1])
            etree.SubElement(inv_ref, f"{{{NS['cbc']}}}IssueDate").text = original_date
        else:
            etree.SubElement(inv_ref, f"{{{NS['cbc']}}}ID").text = "UNKNOWN"
            etree.SubElement(inv_ref, f"{{{NS['cbc']}}}IssueDate").text = ctx["issue_date"]

    # --- Step 3: AdditionalDocumentReference now goes here, after Billing/Discrepancy ---
    if ctx["currency_code"] != "AED":
        aed_total = ctx["totals"]["total"] * ctx["exchange_rate"]
        ref = etree.SubElement(doc, f"{{{NS['cac']}}}AdditionalDocumentReference")
        etree.SubElement(ref, f"{{{NS['cbc']}}}ID").text = "AED"
        etree.SubElement(ref, f"{{{NS['cbc']}}}DocumentTypeCode").text = "aedtotal-incl-vat"
        etree.SubElement(ref, f"{{{NS['cbc']}}}DocumentDescription").text = f"AED {aed_total:.2f}"

    sup = etree.SubElement(doc, f"{{{NS['cac']}}}AccountingSupplierParty")
    build_party(sup, ctx["company"], NS)
    cust = etree.SubElement(doc, f"{{{NS['cac']}}}AccountingCustomerParty")
    build_party(cust, ctx["partner"], NS)

    if doc_meta["type_code"] in ["380", "389"]:
        payment_means = etree.SubElement(doc, f"{{{NS['cac']}}}PaymentMeans")
        etree.SubElement(payment_means, f"{{{NS['cbc']}}}PaymentMeansCode",
                         name="Credit transfer").text = "30"
        etree.SubElement(payment_means, f"{{{NS['cbc']}}}PaymentID").text = \
            f"PAY-{ctx['invoice']['name']}"
        payee_account = etree.SubElement(payment_means, f"{{{NS['cac']}}}PayeeFinancialAccount")
        etree.SubElement(payee_account, f"{{{NS['cbc']}}}ID").text = \
            safe_text(ctx["company"].get("vat"))
        etree.SubElement(payee_account, f"{{{NS['cbc']}}}Name").text = \
            safe_text(ctx["company"].get("name"))
        financial_inst = etree.SubElement(payee_account,
                                          f"{{{NS['cac']}}}FinancialInstitutionBranch")
        etree.SubElement(financial_inst, f"{{{NS['cbc']}}}ID").text = "UAE01"
        payment_terms = etree.SubElement(doc, f"{{{NS['cac']}}}PaymentTerms")
        etree.SubElement(payment_terms, f"{{{NS['cbc']}}}Note").text = "30 Days Payment"

    # --- TaxExchangeRate stays here, unchanged — this position was already correct ---
    if ctx["currency_code"] != "AED":
        exchange = etree.SubElement(doc, f"{{{NS['cac']}}}TaxExchangeRate")
        etree.SubElement(exchange, f"{{{NS['cbc']}}}SourceCurrencyCode").text = ctx["currency_code"]
        etree.SubElement(exchange, f"{{{NS['cbc']}}}TargetCurrencyCode").text = "AED"
        etree.SubElement(exchange, f"{{{NS['cbc']}}}CalculationRate").text = \
            f"{ctx['exchange_rate']:.6f}"

    add_tax_total(doc, ctx, NS)
    add_monetary_total(doc, ctx, NS, credit=doc_meta["type_code"] in ["381", "261"])
    add_document_lines(doc, ctx, doc_meta, NS)
    return doc