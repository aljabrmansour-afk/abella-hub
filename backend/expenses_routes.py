"""
المصروفات في المنصة (/expenses) — الإشراف · الضيافة · التنفيذ (التشغيلية) · المشتريات
=====================================================================================
نفس قواعد تطبيقَي «المصروفات» و«مصروفات المصنع»:
  - الإجمالي يُدخل شامل/غير شامل الضريبة → الضريبة المستردة = الإجمالي × 15/115 إذا «شامل»
  - آجل = المدفوع صفر (أو جزء) والباقي مستحق للمورد؛ غيره = مدفوع كامل
  - المورد: الضيافة = البند نفسه؛ غيرها = المورد أو البيان أو البند
  - السداد: لفواتير محددة، أو مبلغ للمورد يتوزع على أقدم الفواتير
  - الموظف ما يحذف ولا يعدّل مباشرة: يرفع طلب (السبب إلزامي) ← اعتماد منصور ← يُطبّق؛ والسجل خاص بمنصور
أثناء التشغيل المتوازي: فواتير الجداول تُستورد كل 15 دقيقة (للعرض)، والتسجيل من التطبيقات القديمة
(الإدارة تقدر تجرّب بفواتير تجريبية). التحويل: exp_master = 'hub'.
"""
import json, re, os, base64, uuid, datetime
from pathlib import Path
import access_control as ac
from sync_sheets import fetch_csv, to_number, clean_text, to_date

VAT = 0.15
METHODS = ['كاش', 'تحويل', 'بطاقة 1', 'آجل']
TYPES = {
    'sup': {'label': 'الإشراف', 'id': '110xUWBb4FdnYwIOg47RiFyqoyKKEW7bX40PlIKWGs90', 'item': 'البند',
            'cols': {'inv': 10, 'inv_date': 11, 'desc': 12, 'qty': 13}, 'supplier': 21, 'att': 22, 'by': 23},
    'hos': {'label': 'الضيافة', 'id': '1s9n9Y7PVArzLOrKlDQChMPd-anfApTaqmunj8EptsIY', 'item': 'المورد',
            'cols': {'inv': 10, 'inv_date': 11, 'desc': 12, 'qty': 13}, 'supplier': None, 'att': 21, 'by': 22},
    'exe': {'label': 'التنفيذ (التشغيلية)', 'id': '1jMWAK4sdkwwXJGArZQ3D8E3POM_82Nxzct5jrrRR-T4', 'item': 'البند',
            'cols': {'qty': 10, 'desc': 11, 'inv': 12, 'inv_date': 13}, 'supplier': 21, 'att': 22, 'by': 23},
    'pur': {'label': 'المشتريات', 'id': '1xvG_sfIddU7Poo5J54yVb4FjSckDX1pCrrE7Rd3Dd9g', 'item': 'البند',
            'cols': {'inv': 10, 'inv_date': 11, 'desc': 12, 'qty': 13}, 'supplier': 21, 'att': 22, 'by': 23},
}
# الأعمدة المشتركة (0-based): A رقم التشغيل … I المسؤول، J البند/المورد، O الإجمالي، P الضريبة، Q الصافي، R الطريقة، S المدفوع، T المتبقي، U ملاحظات
CO = dict(o=0, person=8, item=9, total=14, vat=15, net=16, method=17, paid=18, rem=19, notes=20)


def r2(x):
    return round(float(x or 0) + 1e-9, 2)


def _now():
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M')


def _rows(conn, sql, p=()):
    return [dict(r) for r in conn.execute(sql, p).fetchall()]


def _setting(conn, k, d=None):
    r = conn.execute("SELECT value FROM settings WHERE key=?", (k,)).fetchone()
    return r[0] if r and r[0] is not None else d


def init_tables(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS exp_invoices (
        id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT DEFAULT 'hub', sheet_row INTEGER, k TEXT NOT NULL,
        operation_order TEXT, client TEXT, person TEXT, item TEXT, supplier TEXT, sup_key TEXT, invoice_number TEXT,
        invoice_date TEXT, description TEXT, quantity TEXT, total REAL, vat REAL, net REAL, method TEXT, paid REAL,
        remaining REAL, notes TEXT, attachment TEXT, entered_by TEXT, entered_at TEXT, status TEXT DEFAULT 'active',
        is_test INTEGER DEFAULT 0, edited TEXT);
    CREATE INDEX IF NOT EXISTS idx_expinv_k ON exp_invoices(k, source);
    CREATE INDEX IF NOT EXISTS idx_expinv_o ON exp_invoices(operation_order);
    CREATE TABLE IF NOT EXISTS exp_payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT, pay_id TEXT, k TEXT, invoice_id INTEGER, supplier TEXT, operation_order TEXT,
        amount REAL, method TEXT, bank TEXT, reference TEXT, notes TEXT, attachment TEXT, pay_date TEXT, by_name TEXT,
        created_at TEXT, is_test INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS exp_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT, invoice_id INTEGER, kind TEXT, reason TEXT, proposed_json TEXT, snapshot_json TEXT,
        requested_by TEXT, requested_at TEXT, status TEXT DEFAULT 'بانتظار الاعتماد', decided_by TEXT, decided_at TEXT, note TEXT);
    """)
    if not _setting(conn, 'exp_master'):
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('exp_master', 'generator')")
    if not _setting(conn, 'exp_approvers'):
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('exp_approvers', '[\"mansour\"]')")


def sup_key(k, item, desc, supplier):
    return clean_text(item) if k == 'hos' else (clean_text(supplier) or clean_text(desc) or clean_text(item))


# ───────────────────────── استيراد الجداول ─────────────────────────
def import_sheets(conn, log=print):
    clients = {r[0]: r[1] for r in conn.execute("SELECT operation_order, customer_name FROM sheet_contracts WHERE operation_order<>''")}
    total = 0
    for k, T in TYPES.items():
        rows = fetch_csv(T['id'], '0')
        conn.execute("DELETE FROM exp_invoices WHERE k=? AND source='sheet'", (k,))
        n = 0
        for i, row in enumerate(rows):
            if not row or not re.match(r'^O\d+', clean_text(row[0]) or ''):
                continue
            g = lambda j: row[j] if j is not None and j < len(row) else ''
            tot = to_number(g(CO['total']))
            if not tot and not clean_text(g(CO['item'])):
                continue
            item, desc, sup = clean_text(g(CO['item'])), clean_text(g(T['cols']['desc'])), clean_text(g(T['supplier']))
            paid, rem = to_number(g(CO['paid'])), clean_text(g(CO['rem']))
            conn.execute("""INSERT INTO exp_invoices (source, sheet_row, k, operation_order, client, person, item, supplier, sup_key,
                              invoice_number, invoice_date, description, quantity, total, vat, net, method, paid, remaining, notes,
                              attachment, entered_by) VALUES ('sheet',?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                         (i + 1, k, clean_text(row[0]), clients.get(clean_text(row[0])) or clean_text(g(2)), clean_text(g(CO['person'])),
                          item, sup or (item if k == 'hos' else ''), sup_key(k, item, desc, sup), clean_text(g(T['cols']['inv'])),
                          to_date(g(T['cols']['inv_date'])), desc, clean_text(g(T['cols']['qty'])), tot, to_number(g(CO['vat'])),
                          to_number(g(CO['net'])), clean_text(g(CO['method'])), paid,
                          to_number(rem) if rem != '' else r2(tot - paid), clean_text(g(CO['notes'])),
                          clean_text(g(T['att'])), clean_text(g(T['by']))))
            n += 1
        total += n
    conn.execute("INSERT INTO sync_log (source, status, rows_imported) VALUES ('expenses_native','success',?)", (total,))
    conn.commit()
    log(f'✓ المصروفات: {total} فاتورة من الجداول الأربعة')
    return total


# ───────────────────────── صلاحيات ─────────────────────────
def is_hub_master(conn):
    return _setting(conn, 'exp_master') == 'hub'


def _me(ctx):
    u = ctx['user']
    return (u.get('full_name') or u['username']).split(' — ')[0]


def _is_approver(conn, ctx):
    try:
        return ctx['user']['username'] in json.loads(_setting(conn, 'exp_approvers') or '[]')
    except Exception:
        return False


def _can_enter(conn, ctx, k):
    p = ctx['perms']
    if p.get('is_super'):
        return True
    return ac.can(p, 'expenses', 'create') or ac.can(p, 'finance', 'create') or bool(ctx['user'].get('can_record_expenses'))


def _write_ok(conn, ctx, k=None):
    """يرجع is_test أو يرفع خطأ"""
    if is_hub_master(conn):
        if k and not _can_enter(conn, ctx, k):
            raise PermissionError('ما عندك صلاحية تسجيل مصروفات ' + TYPES[k]['label'])
        return 0
    if ctx['perms'].get('is_super'):
        return 1
    raise PermissionError('التسجيل حالياً من تطبيق المصروفات القديم (التشغيل المتوازي) — المنصة تعرض الفواتير')


def _save_file(data_url, prefix):
    if not data_url:
        return ''
    m = re.match(r'^data:([^;]+);base64,(.+)$', data_url, re.S)
    if not m:
        return ''
    ext = {'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp', 'application/pdf': '.pdf'}.get(m[1], '.bin')
    base = Path(os.environ['DATA_DIR']) / 'uploads' if os.environ.get('DATA_DIR') else Path(__file__).resolve().parent / 'uploads'
    d = base / 'expenses'
    d.mkdir(parents=True, exist_ok=True)
    name = f"{prefix}-{uuid.uuid4().hex[:10]}{ext}"
    (d / name).write_bytes(base64.b64decode(m[2]))
    return '/uploads/expenses/' + name


def _calc(k, p):
    total = r2(to_number(p.get('total')))
    if not total > 0:
        raise ValueError('أدخل المبلغ الإجمالي')
    if not clean_text(p.get('item')):
        raise ValueError('اختر المورد' if k == 'hos' else 'اختر البند')
    vat = r2(total * VAT / (1 + VAT)) if p.get('vatInc') else 0
    method = clean_text(p.get('method')) or 'كاش'
    if method == 'آجل':
        paid = r2(to_number(p.get('paid') or 0))
    else:
        paid = total if p.get('paid') in ('', None) else r2(to_number(p.get('paid')))
    paid = max(0, min(paid, total))
    return total, vat, r2(total - vat), method, paid, r2(total - paid)


def _ops(conn):
    rows = _rows(conn, """SELECT operation_order AS o, customer_name AS client, event_type AS type, venue, expected_date AS d1, status
                          FROM sheet_contracts WHERE operation_order LIKE 'O%' ORDER BY operation_order DESC""")
    rows += _rows(conn, """SELECT e.operation_order AS o, c.full_name AS client, e.event_type AS type, e.venue_name AS venue, e.event_date AS d1,
                             e.status AS status FROM events e LEFT JOIN customers c ON c.id=e.customer_id
                           WHERE e.sync_source='system' AND e.operation_order<>'' ORDER BY e.id DESC""")
    seen, out = set(), []
    for r in rows:
        if r['o'] and r['o'] not in seen:
            seen.add(r['o']); out.append(r)
    return out


def handle(h, conn, method, path, query, data, ctx, send_json):
    if not path.startswith('/api/exp/'):
        return False
    q1 = lambda k: (query.get(k) or [''])[0] if isinstance(query.get(k), list) else (query.get(k) or '')
    try:
        if path == '/api/exp/boot' and method == 'GET':
            people = [r[0] for r in conn.execute("SELECT person FROM exp_invoices WHERE person<>'' GROUP BY person ORDER BY COUNT(*) DESC LIMIT 40")]
            items = {k: [r[0] for r in conn.execute("SELECT item FROM exp_invoices WHERE k=? AND item<>'' GROUP BY item ORDER BY COUNT(*) DESC LIMIT 200", (k,))] for k in TYPES}
            sups = [r[0] for r in conn.execute("SELECT supplier FROM exp_invoices WHERE supplier<>'' GROUP BY supplier ORDER BY COUNT(*) DESC LIMIT 200")]
            send_json({'types': {k: {'label': v['label'], 'item': v['item'], 'canEnter': _can_enter(conn, ctx, k)} for k, v in TYPES.items()},
                       'methods': METHODS, 'ops': _ops(conn), 'people': ['أ. نوف', 'أبو زياد'] + [p for p in people if p not in ('أ. نوف', 'أبو زياد')],
                       'items': items, 'suppliers': sups, 'hubMaster': is_hub_master(conn), 'isSuper': bool(ctx['perms'].get('is_super')),
                       'isApprover': _is_approver(conn, ctx), 'me': _me(ctx),
                       'pending': conn.execute("SELECT COUNT(*) FROM exp_requests WHERE status='بانتظار الاعتماد'").fetchone()[0]})
            return True

        if path == '/api/exp/list' and method == 'GET':
            sql, p = "SELECT * FROM exp_invoices WHERE status<>'deleted'", []
            for f, col in (('k', 'k'), ('o', 'operation_order'), ('supplier', 'sup_key')):
                if q1(f):
                    sql += f" AND {col}=?"; p.append(q1(f))
            if q1('q'):
                sql += " AND (client LIKE ? OR item LIKE ? OR supplier LIKE ? OR invoice_number LIKE ? OR description LIKE ? OR operation_order LIKE ?)"
                p += ['%' + q1('q') + '%'] * 6
            if q1('missing'):
                sql += " AND (COALESCE(invoice_number,'')='' OR COALESCE(attachment,'')='' OR COALESCE(person,'')='')"
            sql += " ORDER BY COALESCE(invoice_date, entered_at) DESC, id DESC LIMIT " + str(min(int(q1('limit') or 400), 3000))
            rows = _rows(conn, sql, p)
            pend = {r[0] for r in conn.execute("SELECT invoice_id FROM exp_requests WHERE status='بانتظار الاعتماد'")}
            for r in rows:
                r['pending'] = r['id'] in pend
            send_json(rows)
            return True

        if path == '/api/exp/add' and method == 'POST':
            k = data.get('k')
            if k not in TYPES:
                raise ValueError('اختر نوع المصروف')
            is_test = _write_ok(conn, ctx, k)
            o = clean_text(data.get('o'))
            if not o:
                raise ValueError('اختر رقم التشغيل')
            if not any(x['o'] == o for x in _ops(conn)):
                raise ValueError('رقم التشغيل غير موجود')
            if not clean_text(data.get('person')):
                raise ValueError('حدد المسؤول (اللي اشترى)')
            total, vat, net, mth, paid, rem = _calc(k, data)
            op = next((x for x in _ops(conn) if x['o'] == o), {})
            att = _save_file(data.get('file'), o)
            item, sup = clean_text(data.get('item')), clean_text(data.get('supplier'))
            cur = conn.execute("""INSERT INTO exp_invoices (source, k, operation_order, client, person, item, supplier, sup_key, invoice_number,
                                    invoice_date, description, quantity, total, vat, net, method, paid, remaining, notes, attachment,
                                    entered_by, entered_at, is_test) VALUES ('hub',?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                               (k, o, op.get('client'), clean_text(data.get('person')), item, sup or (item if k == 'hos' else ''),
                                sup_key(k, item, data.get('desc'), sup), clean_text(data.get('inv')), data.get('invDate') or None,
                                clean_text(data.get('desc')), clean_text(data.get('qty')), total, vat, net, mth, paid, rem,
                                clean_text(data.get('notes')), att, _me(ctx), _now(), is_test))
            conn.commit()
            send_json({'success': True, 'id': cur.lastrowid, 'test': bool(is_test)})
            return True

        if path == '/api/exp/dues' and method == 'GET':
            rows = _rows(conn, """SELECT k, sup_key AS supplier, COUNT(*) AS n, ROUND(SUM(remaining),2) AS due, MIN(COALESCE(invoice_date,entered_at)) AS oldest,
                                     SUM(CASE WHEN source='hub' THEN 1 ELSE 0 END) AS hub_n
                                  FROM exp_invoices WHERE status<>'deleted' AND remaining>0.009 GROUP BY k, sup_key ORDER BY due DESC""")
            send_json(rows)
            return True

        if path == '/api/exp/pay' and method == 'POST':
            k = data.get('k')
            is_test = _write_ok(conn, ctx, k)
            if not (ctx['perms'].get('is_super') or ac.can(ctx['perms'], 'finance', 'create') or ac.can(ctx['perms'], 'payments', 'create') or ac.can(ctx['perms'], 'expenses', 'edit')):
                raise PermissionError('السداد للمالية')
            src = "AND source='hub'" + ("" if is_test else " AND is_test=0")
            if data.get('mode') == 'supplier':
                left = r2(to_number(data.get('amount')))
                if not left > 0:
                    raise ValueError('أدخل مبلغ السداد')
                open_ = _rows(conn, f"""SELECT * FROM exp_invoices WHERE k=? AND sup_key=? AND remaining>0.009 AND status<>'deleted' {src}
                                        ORDER BY COALESCE(invoice_date,'9999'), id""", (k, data.get('supplier')))
                due = r2(sum(x['remaining'] for x in open_))
                if left > due + 0.009:
                    raise ValueError(f'المبلغ أكبر من المستحق للمورد في المنصة ({due})')
                allocs = []
                for x in open_:
                    if left <= 0.009:
                        break
                    a = r2(min(left, x['remaining'])); allocs.append((x, a)); left = r2(left - a)
            else:
                allocs = []
                for it in data.get('rows') or []:
                    x = conn.execute(f"SELECT * FROM exp_invoices WHERE id=? {src}", (it.get('id'),)).fetchone()
                    if not x:
                        raise ValueError('فاتورة غير صالحة (فواتير الجداول تُسدّد من التطبيق القديم حتى التحويل)')
                    x = dict(x); a = r2(min(to_number(it.get('amt')), x['remaining']))
                    if a > 0:
                        allocs.append((x, a))
            if not allocs:
                raise ValueError('لا توجد مبالغ للسداد')
            att = _save_file(data.get('file'), 'سند')
            pay_id = 'P' + datetime.datetime.now().strftime('%y%m%d%H%M%S')
            for x, a in allocs:
                newp = r2(x['paid'] + a); rem = r2(x['total'] - newp)
                mth = x['method'] if rem > 0.009 else (data.get('method') if data.get('method') in METHODS and data.get('method') != 'آجل' else 'تحويل')
                conn.execute("UPDATE exp_invoices SET paid=?, remaining=?, method=? WHERE id=?", (newp, rem, mth, x['id']))
                conn.execute("""INSERT INTO exp_payments (pay_id, k, invoice_id, supplier, operation_order, amount, method, bank, reference, notes,
                                  attachment, pay_date, by_name, created_at, is_test) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                             (pay_id, x['k'], x['id'], x['sup_key'], x['operation_order'], a, data.get('method'), data.get('bank'),
                              data.get('ref'), data.get('notes'), att, data.get('date') or _now()[:10], _me(ctx), _now(), x['is_test']))
            conn.commit()
            send_json({'success': True, 'pay_id': pay_id, 'count': len(allocs), 'amount': r2(sum(a for _, a in allocs))})
            return True

        if path == '/api/exp/payments' and method == 'GET':
            send_json(_rows(conn, "SELECT * FROM exp_payments ORDER BY id DESC LIMIT 400"))
            return True

        # ───── طلبات التعديل والحذف (اعتماد منصور) ─────
        if path == '/api/exp/request' and method == 'POST':
            x = conn.execute("SELECT * FROM exp_invoices WHERE id=?", (data.get('id'),)).fetchone()
            if not x:
                raise ValueError('الفاتورة غير موجودة')
            x = dict(x)
            if x['source'] != 'hub':
                raise ValueError('فواتير الجداول تُعدّل من التطبيق القديم حتى التحويل')
            if not clean_text(data.get('reason')):
                raise ValueError('اكتب السبب')
            if conn.execute("SELECT 1 FROM exp_requests WHERE invoice_id=? AND status='بانتظار الاعتماد'", (x['id'],)).fetchone():
                raise ValueError('عليها طلب بانتظار الاعتماد')
            kind = 'حذف' if data.get('kind') == 'delete' else 'تعديل'
            if kind == 'حذف' and conn.execute("SELECT 1 FROM exp_payments WHERE invoice_id=?", (x['id'],)).fetchone():
                raise ValueError('عليها دفعات مسجلة — لا تُحذف')
            conn.execute("""INSERT INTO exp_requests (invoice_id, kind, reason, proposed_json, snapshot_json, requested_by, requested_at)
                            VALUES (?,?,?,?,?,?,?)""",
                         (x['id'], kind, clean_text(data.get('reason')), json.dumps(data.get('proposed') or {}, ensure_ascii=False),
                          json.dumps(x, ensure_ascii=False, default=str), _me(ctx), _now()))
            conn.commit()
            send_json({'success': True})
            return True

        if path == '/api/exp/requests' and method == 'GET':
            if not _is_approver(conn, ctx):
                raise PermissionError('الاعتمادات لمنصور فقط')
            st = q1('status') or 'بانتظار الاعتماد'
            sql = "SELECT r.*, i.k, i.operation_order, i.item, i.total, i.invoice_number FROM exp_requests r LEFT JOIN exp_invoices i ON i.id=r.invoice_id"
            rows = _rows(conn, sql + (" WHERE r.status=?" if st != 'all' else '') + " ORDER BY r.id DESC LIMIT 300", (st,) if st != 'all' else ())
            send_json(rows)
            return True

        m = re.match(r'^/api/exp/requests/(\d+)/decide$', path)
        if m and method == 'POST':
            if not _is_approver(conn, ctx):
                raise PermissionError('الاعتماد لمنصور فقط')
            r = conn.execute("SELECT * FROM exp_requests WHERE id=?", (int(m.group(1)),)).fetchone()
            if not r or r['status'] != 'بانتظار الاعتماد':
                raise ValueError('الطلب غير متاح')
            r = dict(r)
            x = dict(conn.execute("SELECT * FROM exp_invoices WHERE id=?", (r['invoice_id'],)).fetchone())
            snap = json.loads(r['snapshot_json'] or '{}')
            if data.get('decision') == 'approve':
                if any(abs(float(x.get(f) or 0) - float(snap.get(f) or 0)) > 0.009 for f in ('total', 'paid')):
                    raise ValueError('الفاتورة تغيّرت بعد الطلب — ارفض واطلب طلباً جديداً')
                if r['kind'] == 'حذف':
                    conn.execute("UPDATE exp_invoices SET status='deleted', edited=? WHERE id=?", (f"حُذفت بطلب {r['requested_by']} · {_now()}", x['id']))
                else:
                    pr = json.loads(r['proposed_json'] or '{}')
                    merged = {'item': x['item'], 'total': x['total'], 'vatInc': x['vat'] > 0, 'method': x['method'], **pr}
                    if merged.get('method') == 'آجل' and 'paid' not in pr:
                        merged['paid'] = x['paid']
                    total, vat, net, mth, paid, rem = _calc(x['k'], merged)
                    item, sup = clean_text(merged.get('item')), clean_text(pr.get('supplier', x['supplier']))
                    conn.execute("""UPDATE exp_invoices SET operation_order=?, person=?, item=?, supplier=?, sup_key=?, invoice_number=?, invoice_date=?,
                                      description=?, quantity=?, total=?, vat=?, net=?, method=?, paid=?, remaining=?, notes=?, edited=? WHERE id=?""",
                                 (pr.get('o', x['operation_order']), pr.get('person', x['person']), item, sup, sup_key(x['k'], item, pr.get('desc', x['description']), sup),
                                  pr.get('inv', x['invoice_number']), pr.get('invDate', x['invoice_date']), pr.get('desc', x['description']),
                                  pr.get('qty', x['quantity']), total, vat, net, mth, paid, rem, pr.get('notes', x['notes']),
                                  f"عُدّل بطلب {r['requested_by']} · {_now()}", x['id']))
                status = 'معتمد'
            else:
                status = 'مرفوض'
            conn.execute("UPDATE exp_requests SET status=?, decided_by=?, decided_at=?, note=? WHERE id=?",
                         (status, _me(ctx), _now(), data.get('note'), r['id']))
            conn.commit()
            send_json({'success': True, 'status': status})
            return True

        if path == '/api/exp/master' and method == 'POST':
            if not ctx['perms'].get('is_super'):
                raise PermissionError('للإدارة فقط')
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('exp_master', ?)", ('hub' if data.get('master') == 'hub' else 'generator',))
            conn.commit()
            send_json({'success': True})
            return True

        if path == '/api/exp/test-data' and method == 'POST':
            if not ctx['perms'].get('is_super'):
                raise PermissionError('للإدارة فقط')
            conn.execute("DELETE FROM exp_payments WHERE is_test=1")
            conn.execute("DELETE FROM exp_requests WHERE invoice_id IN (SELECT id FROM exp_invoices WHERE is_test=1)")
            n = conn.execute("DELETE FROM exp_invoices WHERE is_test=1").rowcount
            conn.commit()
            send_json({'success': True, 'deleted': n})
            return True
    except PermissionError as e:
        send_json({'error': str(e)}, 403)
        return True
    except ValueError as e:
        send_json({'error': str(e)}, 400)
        return True
    except Exception as e:
        import traceback; traceback.print_exc()
        send_json({'error': 'خطأ في الخادم: ' + str(e)}, 500)
        return True
    return False
