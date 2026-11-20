"""
مرآة مولّد العقود (المرحلة الانتقالية)
=====================================
تسحب كل تبويبات ملف العقود من Google Sheets إلى المنصة:
  عروض الأسعار + بنود الخدمات · مراجعات العروض · سجل المدفوعات · ملاحق العقود · طلبات التغيير
وتربطها بالمناسبات برقم العقد / رقم التشغيل.

قاعدة: ما دام مولّد العقود هو المصدر (CONTRACTS_MASTER != 'hub') فالسجلات القادمة منه
للعرض فقط في المنصة، وأي تعديل يكون من المولّد.
"""
import json
import sqlite3
import time
import datetime

from sync_sheets import fetch_csv, to_number, clean_text

SHEET_ID = '1yd4YQwjV-kDkqqu4iwFmGAlQmwhGWOYrP-x2w5r4_kg'
GIDS = {
    'quotes': '1514937596',
    'revisions': '169843237',
    'payments': '1810607881',
    'addenda': '806981353',
    'changes': '1781537118',
}


def _date(v):
    """2026/10/08 18:00 أو 19/10/2026 → ISO"""
    s = clean_text(v)
    if not s:
        return None
    s = s.translate(str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789')).replace('-', '/')
    part, _, tm = s.partition(' ')
    bits = part.split('/')
    try:
        if len(bits[0]) == 4:
            y, m, d = int(bits[0]), int(bits[1]), int(bits[2])
        else:
            d, m, y = int(bits[0]), int(bits[1]), int(bits[2])
        out = f"{y:04d}-{m:02d}-{d:02d}"
        return out + (' ' + tm.strip() if tm.strip() else '')
    except Exception:
        return s


def map_event_type(t):
    t = clean_text(t)
    if 'ولادة' in t or 'مولود' in t:
        return 'newborn', ('home' if 'منزل' in t else 'hospital')
    if 'معرض' in t:
        return 'exhibition', 'other'
    return 'special', ('home' if 'منزل' in t else 'other')


def init_tables(conn):
    cols = {r[1] for r in conn.execute("PRAGMA table_info(quotes)")}
    for c, d in [('source', "TEXT DEFAULT 'system'"), ('gen_status', 'TEXT'), ('client_title', 'TEXT'),
                 ('client_email', 'TEXT'), ('revision', 'INTEGER'), ('confirmed_date', 'TEXT'),
                 ('gen_operation_order', 'TEXT'), ('gen_paid_flags', 'TEXT'), ('gen_received', 'REAL'),
                 ('gen_remaining', 'REAL'), ('final_payment', 'REAL'), ('gen_synced_at', 'TEXT')]:
        if c not in cols:
            conn.execute(f"ALTER TABLE quotes ADD COLUMN {c} {d}")
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS gen_quote_revisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, quote_code TEXT, revision INTEGER, revision_date TEXT,
        reason TEXT, client_name TEXT, contract_value REAL, additional REAL, discount REAL,
        total_with_vat REAL, deposit REAL, final_payment REAL, insurance REAL, data_json TEXT,
        UNIQUE(quote_code, revision));
    CREATE TABLE IF NOT EXISTS gen_payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT, row_key TEXT UNIQUE, recorded_at TEXT, quote_code TEXT,
        contract_code TEXT, client_name TEXT, payment_type TEXT, amount REAL, method TEXT,
        payment_date TEXT, reference TEXT, notes TEXT);
    CREATE TABLE IF NOT EXISTS gen_addenda (
        id INTEGER PRIMARY KEY AUTOINCREMENT, addendum_code TEXT UNIQUE, contract_code TEXT,
        operation_order TEXT, client_name TEXT, change_type TEXT, description TEXT,
        cost REAL, vat REAL, total REAL, issued_at TEXT, status TEXT, pay_method TEXT,
        paid_at TEXT, reference TEXT, notes TEXT);
    CREATE TABLE IF NOT EXISTS gen_change_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT, request_code TEXT UNIQUE, contract_code TEXT, quote_code TEXT,
        operation_order TEXT, client_name TEXT, request_type TEXT, summary TEXT, proposed_json TEXT,
        money_impact REAL, approval_method TEXT, evidence_json TEXT, payment_json TEXT, created_by TEXT,
        created_at TEXT, status TEXT, approved_by TEXT, approved_at TEXT, approver_note TEXT,
        result TEXT, diff_json TEXT);
    CREATE INDEX IF NOT EXISTS idx_gen_pay_contract ON gen_payments(contract_code);
    CREATE INDEX IF NOT EXISTS idx_gen_add_contract ON gen_addenda(contract_code);
    CREATE INDEX IF NOT EXISTS idx_gen_cr_contract ON gen_change_requests(contract_code);
    """)
    for t, extra in (('gen_quote_revisions', [('source', "TEXT DEFAULT 'generator'"), ('by_name', 'TEXT')]),
                     ('gen_payments', [('source', "TEXT DEFAULT 'generator'")]),
                     ('gen_addenda', [('source', "TEXT DEFAULT 'generator'"), ('event_id', 'INTEGER'), ('created_by', 'TEXT')]),
                     ('gen_change_requests', [('source', "TEXT DEFAULT 'generator'"), ('evidence_path', 'TEXT')])):
        have = {r[1] for r in conn.execute(f"PRAGMA table_info({t})")}
        for c, d in extra:
            if c not in have:
                conn.execute(f"ALTER TABLE {t} ADD COLUMN {c} {d}")
    for t in ('quotes', 'events'):
        have = {r[1] for r in conn.execute(f"PRAGMA table_info({t})")}
        if 'is_test' not in have:
            conn.execute(f"ALTER TABLE {t} ADD COLUMN is_test INTEGER DEFAULT 0")


def _table(rows):
    if not rows:
        return []
    head = [clean_text(h) for h in rows[0]]
    out = []
    for r in rows[1:]:
        if not any(clean_text(x) for x in r):
            continue
        r = list(r) + [''] * (len(head) - len(r))
        out.append(dict(zip(head, r)))
    return out


def sync_quotes(conn, rows):
    n = 0
    now = datetime.datetime.now().isoformat(timespec='seconds')
    for r in _table(rows):
        code = clean_text(r.get('رقم العرض'))
        if not code:
            continue
        etype, vkind = map_event_type(r.get('نوع المناسبة'))
        contract = clean_text(r.get('رقم العقد')) or None
        gst = clean_text(r.get('حالة المستند'))
        status = 'contracted' if contract else ('rejected' if 'ملغ' in gst or 'مرفوض' in gst else 'sent')
        op = clean_text(r.get('رقم أمر التشغيل')) or None
        ev = None
        if contract:
            ev = conn.execute("SELECT id FROM events WHERE contract_code=?", (contract,)).fetchone()
        if not ev and op:
            ev = conn.execute("SELECT id FROM events WHERE operation_order=?", (op,)).fetchone()
        flags = json.dumps({'deposit': clean_text(r.get('العربون مدفوع')), 'insurance': clean_text(r.get('التأمين مدفوع')),
                            'final': clean_text(r.get('الدفعة النهائية مدفوعة'))}, ensure_ascii=False)
        vals = dict(
            client_name=clean_text(r.get('اسم العميل')), client_phone=clean_text(r.get('رقم التواصل')) or None,
            client_id_number=clean_text(r.get('رقم الهوية')) or None, event_type=etype, venue_kind=vkind,
            venue_name=clean_text(r.get('الموقع')) or None, expected_date=_date(r.get('تاريخ المناسبة')),
            contract_value=to_number(r.get('قيمة العقد')), additional=to_number(r.get('مبالغ إضافية')),
            discount=to_number(r.get('الخصم')), vat_amount=to_number(r.get('الضريبة')),
            total_with_vat=to_number(r.get('الإجمالي بعد الضريبة')), insurance=to_number(r.get('التأمين')),
            deposit=to_number(r.get('العربون')), final_payment=to_number(r.get('الدفعة النهائية')),
            status=status, notes=clean_text(r.get('ملاحظات')) or None, event_id=ev[0] if ev else None,
            contract_code=contract, source='generator', gen_status=gst, client_title=clean_text(r.get('اللقب')) or None,
            client_email=clean_text(r.get('البريد')) or None, revision=int(to_number(r.get('رقم النسخة'))) or None,
            confirmed_date=_date(r.get('التاريخ المؤكد')), gen_operation_order=op, gen_paid_flags=flags,
            gen_received=to_number(r.get('المبلغ المستلم')), gen_remaining=to_number(r.get('المبلغ المتبقي')),
            gen_synced_at=now, created_at=_date(r.get('تاريخ العرض')) or now,
        )
        old = conn.execute("SELECT id, source FROM quotes WHERE quote_code=?", (code,)).fetchone()
        if old and old[1] not in (None, 'generator'):
            continue  # رقم محجوز لعرض أُنشئ في المنصة — لا نكتب فوقه
        if old:
            qid = old[0]
            conn.execute("UPDATE quotes SET " + ", ".join(f"{k}=?" for k in vals) + ", updated_at=CURRENT_TIMESTAMP WHERE id=?",
                         list(vals.values()) + [qid])
        else:
            cur = conn.execute("INSERT INTO quotes (quote_code, " + ", ".join(vals) + ") VALUES (?" + ",?" * len(vals) + ")",
                               [code] + list(vals.values()))
            qid = cur.lastrowid
        conn.execute("DELETE FROM quote_items WHERE quote_id=?", (qid,))
        try:
            items = json.loads(r.get('الخدمات') or '[]')
        except Exception:
            items = []
        for i, it in enumerate(items):
            name = clean_text(it.get('name'))
            if name:
                conn.execute("INSERT INTO quote_items (quote_id, name, qty, sort_order) VALUES (?,?,?,?)",
                             (qid, name, to_number(it.get('qty')) or None, i))
        if ev:
            conn.execute("UPDATE events SET quote_id=COALESCE(quote_id, ?) WHERE id=?", (qid, ev[0]))
        n += 1
    return n


def sync_revisions(conn, rows):
    n = 0
    for r in _table(rows):
        code = clean_text(r.get('رقم العرض'))
        rev = int(to_number(r.get('رقم النسخة')))
        if not code or not rev:
            continue
        conn.execute("""INSERT INTO gen_quote_revisions (quote_code, revision, revision_date, reason, client_name,
                          contract_value, additional, discount, total_with_vat, deposit, final_payment, insurance, data_json)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                        ON CONFLICT(quote_code, revision) DO UPDATE SET revision_date=excluded.revision_date,
                          reason=excluded.reason, client_name=excluded.client_name, contract_value=excluded.contract_value,
                          additional=excluded.additional, discount=excluded.discount, total_with_vat=excluded.total_with_vat,
                          deposit=excluded.deposit, final_payment=excluded.final_payment, insurance=excluded.insurance,
                          data_json=excluded.data_json""",
                     (code, rev, _date(r.get('تاريخ النسخة')), clean_text(r.get('سبب التعديل')),
                      clean_text(r.get('اسم العميل')), to_number(r.get('قيمة العقد')), to_number(r.get('مبالغ إضافية')),
                      to_number(r.get('الخصم')), to_number(r.get('الإجمالي بعد الضريبة')), to_number(r.get('العربون')),
                      to_number(r.get('الدفعة النهائية')), to_number(r.get('التأمين')), r.get('بيانات كاملة') or None))
        n += 1
    return n


def sync_payments(conn, rows):
    conn.execute("DELETE FROM gen_payments WHERE COALESCE(source,'generator')='generator'")  # سجل المولّد هو المرجع لدفعاته فقط
    n = 0
    for i, r in enumerate(_table(rows)):
        amt = to_number(r.get('المبلغ'))
        if not amt:
            continue
        key = f"{i}|{clean_text(r.get('تاريخ التسجيل'))}|{clean_text(r.get('رقم العرض'))}|{amt}"
        conn.execute("""INSERT OR REPLACE INTO gen_payments (row_key, recorded_at, quote_code, contract_code, client_name,
                          payment_type, amount, method, payment_date, reference, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                     (key, _date(r.get('تاريخ التسجيل')), clean_text(r.get('رقم العرض')) or None,
                      clean_text(r.get('رقم العقد')) or None, clean_text(r.get('اسم العميل')),
                      clean_text(r.get('نوع الدفعة')), amt, clean_text(r.get('طريقة السداد')),
                      _date(r.get('تاريخ السداد')), clean_text(r.get('رقم الحوالة/المرجع')) or None,
                      clean_text(r.get('ملاحظات')) or None))
        n += 1
    return n


def sync_addenda(conn, rows):
    n = 0
    for r in _table(rows):
        code = clean_text(r.get('رقم الملحق'))
        if not code:
            continue
        vals = (clean_text(r.get('رقم العقد')), clean_text(r.get('رقم أمر التشغيل')) or None, clean_text(r.get('اسم العميل')),
                clean_text(r.get('نوع التغيير')), (r.get('الوصف') or '').strip(), to_number(r.get('التكلفة قبل الضريبة')),
                to_number(r.get('الضريبة')), to_number(r.get('الإجمالي')), _date(r.get('تاريخ الإصدار')),
                clean_text(r.get('الحالة')), clean_text(r.get('طريقة السداد')) or None, _date(r.get('تاريخ السداد')),
                clean_text(r.get('المرجع')) or None, clean_text(r.get('ملاحظات')) or None)
        own = conn.execute("SELECT source FROM gen_addenda WHERE addendum_code=?", (code,)).fetchone()
        if own and own[0] == 'hub':
            continue
        conn.execute("""INSERT INTO gen_addenda (addendum_code, contract_code, operation_order, client_name, change_type,
                          description, cost, vat, total, issued_at, status, pay_method, paid_at, reference, notes)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        ON CONFLICT(addendum_code) DO UPDATE SET contract_code=excluded.contract_code,
                          operation_order=excluded.operation_order, client_name=excluded.client_name,
                          change_type=excluded.change_type, description=excluded.description, cost=excluded.cost,
                          vat=excluded.vat, total=excluded.total, issued_at=excluded.issued_at, status=excluded.status,
                          pay_method=excluded.pay_method, paid_at=excluded.paid_at, reference=excluded.reference,
                          notes=excluded.notes""", (code,) + vals)
        n += 1
    return n


def sync_changes(conn, rows):
    n = 0
    for r in _table(rows):
        code = clean_text(r.get('رقم الطلب'))
        if not code:
            continue
        vals = (clean_text(r.get('رقم العقد')) or None, clean_text(r.get('رقم العرض')) or None,
                clean_text(r.get('رقم أمر التشغيل')) or None, clean_text(r.get('اسم العميل')), clean_text(r.get('نوع الطلب')),
                clean_text(r.get('ملخص التغيير')), r.get('البيانات المقترحة') or None, to_number(r.get('الأثر المالي قبل الضريبة')),
                clean_text(r.get('طريقة موافقة العميل')), r.get('معرّف الإثبات') or None, r.get('بيانات السداد') or None,
                clean_text(r.get('أنشأه')), _date(r.get('تاريخ الإنشاء')), clean_text(r.get('الحالة')),
                clean_text(r.get('اعتمده')) or None, _date(r.get('تاريخ الاعتماد')), clean_text(r.get('ملاحظة المعتمد')) or None,
                clean_text(r.get('النتيجة')) or None, r.get('الفروقات') or None)
        own = conn.execute("SELECT source FROM gen_change_requests WHERE request_code=?", (code,)).fetchone()
        if own and own[0] == 'hub':
            continue
        cols = ('contract_code, quote_code, operation_order, client_name, request_type, summary, proposed_json, money_impact, '
                'approval_method, evidence_json, payment_json, created_by, created_at, status, approved_by, approved_at, '
                'approver_note, result, diff_json')
        upd = ", ".join(f"{c.strip()}=excluded.{c.strip()}" for c in cols.split(','))
        conn.execute(f"INSERT INTO gen_change_requests (request_code, {cols}) VALUES (?{',?' * len(vals)}) "
                     f"ON CONFLICT(request_code) DO UPDATE SET {upd}", (code,) + vals)
        n += 1
    return n


def run(db_path, log=print):
    t0 = time.time()
    conn = sqlite3.connect(str(db_path), timeout=30)
    res = {}
    try:
        init_tables(conn)
        res['quotes'] = sync_quotes(conn, fetch_csv(SHEET_ID, GIDS['quotes']))
        res['revisions'] = sync_revisions(conn, fetch_csv(SHEET_ID, GIDS['revisions']))
        res['payments'] = sync_payments(conn, fetch_csv(SHEET_ID, GIDS['payments']))
        res['addenda'] = sync_addenda(conn, fetch_csv(SHEET_ID, GIDS['addenda']))
        res['changes'] = sync_changes(conn, fetch_csv(SHEET_ID, GIDS['changes']))
        ms = int((time.time() - t0) * 1000)
        conn.execute("INSERT INTO sync_log (source, status, rows_imported, duration_ms) VALUES ('contract_generator','success',?,?)",
                     (sum(res.values()), ms))
        conn.commit()
        log(f"✓ مرآة مولّد العقود: {res}")
        return {'success': True, **res}
    except Exception as e:
        conn.rollback()
        try:
            conn.execute("INSERT INTO sync_log (source, status, error_message) VALUES ('contract_generator','error',?)", (str(e),))
            conn.commit()
        except Exception:
            pass
        log(f"⚠ مرآة مولّد العقود: {e}")
        return {'success': False, 'error': str(e)}
    finally:
        conn.close()
