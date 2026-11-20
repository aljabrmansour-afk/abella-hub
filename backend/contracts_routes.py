"""
العقود في المنصة — الملاحق وطلبات التغيير (بنفس قواعد مولّد العقود)
=====================================================================
- أي تعديل على عقد قائم أو ملحق يمر بطلب تغيير: موافقة العميل (توقيع / واتساب / سداد) ← اعتماد المحاسب ← يُطبَّق تلقائياً.
- الملحق: رقم = رقم العقد + -A1, -A2 … ، قبل الضريبة + 15% ، يُضاف لقيمة المناسبة، وسداده يُسجّل كدفعة.
- الجداول نفسها اللي فيها مرآة المولّد (gen_addenda / gen_change_requests) مع source='hub'.
"""
import json, re, os, base64, uuid, datetime
from pathlib import Path
import access_control as ac
import crm_routes as crm

APPROVE_ROLES = ('finance', 'owner', 'general_manager', 'admin')
APPROVAL_METHODS = ('توقيع العميل', 'موافقة واتساب', 'سداد')


def _now():
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M')


def _uname(conn, uid):
    r = conn.execute("SELECT full_name FROM users WHERE id=?", (uid,)).fetchone()
    return (r[0] or '').split(' — ')[0] if r else ''


def _can_approve(ctx):
    p = ctx['perms']
    return bool(p.get('is_super')) or ctx['user']['role'] in APPROVE_ROLES


def _contract(conn, qid):
    q = crm._row(conn, "SELECT * FROM quotes WHERE id=?", (qid,))
    if not q:
        raise ValueError('العرض غير موجود')
    if q.get('source') == 'generator':
        raise ValueError(crm.GEN_LOCK_MSG)
    if q['status'] != 'contracted' or not q.get('event_id'):
        raise ValueError('هذا الإجراء للعقود فقط (حوّل العرض لعقد أولاً)')
    return q


def _save_evidence(data_url, code):
    if not data_url:
        return None
    m = re.match(r'^data:([^;]+);base64,(.+)$', data_url, re.S)
    if not m:
        return None
    ext = {'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp', 'application/pdf': '.pdf'}.get(m[1], '.bin')
    base = Path(os.environ['DATA_DIR']) / 'uploads' if os.environ.get('DATA_DIR') else Path(__file__).resolve().parent / 'uploads'
    d = base / 'contracts'
    d.mkdir(parents=True, exist_ok=True)
    name = f"{code}-{uuid.uuid4().hex[:8]}{ext}"
    (d / name).write_bytes(base64.b64decode(m[2]))
    return '/uploads/contracts/' + name


def _vat(conn):
    return crm._num(ac.get_settings(conn).get('vat_rate'), 0.15)


def _items(conn, qid):
    return [{'name': r['name'], 'qty': r['qty']} for r in crm._rows(conn, "SELECT name, qty FROM quote_items WHERE quote_id=? ORDER BY sort_order, id", (qid,))]


CONTRACT_FIELDS = {  # الحقول اللي يقدر طلب التغيير يعدّلها
    'client_name': 'اسم العميل', 'client_title': 'اللقب', 'client_phone': 'الجوال', 'client_id_number': 'الهوية',
    'client_email': 'البريد', 'venue_name': 'الموقع', 'expected_date': 'تاريخ المناسبة', 'event_time': 'الوقت',
    'guests_count': 'عدد الضيوف', 'notes': 'ملاحظات',
}
MONEY_FIELDS = {'contract_value': 'قيمة العقد', 'additional': 'مبالغ إضافية', 'discount': 'الخصم'}


def _diff_contract(conn, q, proposed):
    diff = []
    for k, lbl in CONTRACT_FIELDS.items():
        if k in proposed and str(proposed.get(k) or '') != str(q.get(k) or ''):
            diff.append({'k': 'field', 'f': k, 'label': lbl, 'from': q.get(k) or '', 'to': proposed.get(k) or ''})
    for k, lbl in MONEY_FIELDS.items():
        if k in proposed and abs(crm._num(proposed.get(k)) - crm._num(q.get(k))) > 0.004:
            diff.append({'k': 'money', 'f': k, 'label': lbl, 'from': crm._num(q.get(k)), 'to': crm._num(proposed.get(k))})
    if 'items' in proposed:
        old = _items(conn, q['id'])
        on = {i['name']: i for i in old}
        nn = {(i.get('name') or '').strip(): i for i in proposed['items'] if (i.get('name') or '').strip()}
        for n, i in nn.items():
            if n not in on:
                diff.append({'k': 'svc+', 'name': n, 'qty': i.get('qty') or ''})
            elif crm._num(i.get('qty')) != crm._num(on[n]['qty']):
                diff.append({'k': 'svcQty', 'name': n, 'from': on[n]['qty'], 'to': i.get('qty')})
        for n in on:
            if n not in nn:
                diff.append({'k': 'svc-', 'name': n})
    return diff


def _summary(diff):
    parts = []
    add = sum(1 for d in diff if d['k'] == 'svc+'); rem = sum(1 for d in diff if d['k'] == 'svc-')
    if rem: parts.append(f'حذف {rem} بند')
    if add: parts.append(f'إضافة {add} بند')
    if any(d['k'] == 'svcQty' for d in diff): parts.append('تعديل أعداد')
    parts += [d['label'] for d in diff if d['k'] in ('field', 'money')]
    return ' · '.join(parts) or 'بدون تغيير'


def _money_impact(q, proposed):
    def base(x):
        return crm._num(x.get('contract_value')) + crm._num(x.get('additional')) - crm._num(x.get('discount'))
    return round(base({**q, **{k: v for k, v in proposed.items() if k in MONEY_FIELDS}}) - base(q), 2)


def _apply_contract_change(conn, q, proposed, uid, cr_code):
    merged = {**q, **{k: v for k, v in proposed.items() if k in CONTRACT_FIELDS or k in MONEY_FIELDS}}
    t = crm.compute_totals(conn, merged)
    conn.execute("""UPDATE quotes SET client_name=?, client_title=?, client_phone=?, client_id_number=?, client_email=?,
                      venue_name=?, expected_date=?, event_time=?, guests_count=?, notes=?, contract_value=?, additional=?,
                      discount=?, vat_rate=?, vat_amount=?, total_with_vat=?, insurance=?, deposit=?, updated_at=CURRENT_TIMESTAMP
                    WHERE id=?""",
                 (merged.get('client_name'), merged.get('client_title'), merged.get('client_phone'), merged.get('client_id_number'),
                  merged.get('client_email'), merged.get('venue_name'), merged.get('expected_date') or None, merged.get('event_time'),
                  int(crm._num(merged.get('guests_count'))) or None, merged.get('notes'), crm._num(merged.get('contract_value')),
                  crm._num(merged.get('additional')), crm._num(merged.get('discount')), t['vat_rate'], t['vat_amount'],
                  t['total_with_vat'], t['insurance'], t['deposit'], q['id']))
    if 'items' in proposed:
        crm._save_items(conn, q['id'], proposed['items'])
    # المناسبة تتبع العقد (القيمة = العقد + الملاحق)
    add_total = conn.execute("SELECT COALESCE(SUM(total),0) FROM gen_addenda WHERE source='hub' AND event_id=?", (q['event_id'],)).fetchone()[0]
    conn.execute("""UPDATE events SET total_price=?, event_date=COALESCE(?, event_date), venue_name=?, guests_count=?,
                      insurance_amount=?, discount=? WHERE id=?""",
                 (round(t['total_with_vat'] + add_total, 2), merged.get('expected_date') or None, merged.get('venue_name'),
                  int(crm._num(merged.get('guests_count'))) or None, t['insurance'], crm._num(merged.get('discount')), q['event_id']))
    crm._recalc_paid(conn, q['event_id'])
    return crm._snapshot_revision(conn, q['id'], uid, f'بموجب {cr_code}')


def handle(h, conn, method, path, query, data, ctx, send_json):
    uid = ctx['user']['id'] if ctx else None
    try:
        # ───── الملاحق ─────
        m = re.match(r'^/api/contracts/(\d+)/addenda$', path)
        if m and method == 'POST':
            if not (ctx['perms'].get('is_super') or ac.can(ctx['perms'], 'quotes', 'edit')):
                raise PermissionError('ما عندك صلاحية إصدار ملحق')
            q = _contract(conn, int(m.group(1)))
            cost = crm._num(data.get('cost'))
            desc = (data.get('description') or '').strip()
            if not desc:
                raise ValueError('اكتب وصف الملحق')
            ctype = data.get('change_type') or 'إضافة'
            n = conn.execute("SELECT COUNT(*) FROM gen_addenda WHERE contract_code=?", (q['contract_code'],)).fetchone()[0] + 1
            code = f"{q['contract_code']}-A{n}"
            vat = round(cost * _vat(conn), 2)
            total = round(cost + vat, 2) * (-1 if ctype == 'خصم' else 1)
            ev = crm._row(conn, "SELECT operation_order FROM events WHERE id=?", (q['event_id'],)) or {}
            conn.execute("""INSERT INTO gen_addenda (addendum_code, contract_code, operation_order, client_name, change_type, description,
                              cost, vat, total, issued_at, status, notes, source, event_id, created_by)
                            VALUES (?,?,?,?,?,?,?,?,?,?, 'غير مدفوع', ?, 'hub', ?, ?)""",
                         (code, q['contract_code'], ev.get('operation_order'), q['client_name'], ctype, desc,
                          cost if ctype != 'خصم' else -cost, vat if ctype != 'خصم' else -vat, total, _now()[:10],
                          data.get('notes'), q['event_id'], _uname(conn, uid)))
            conn.execute("UPDATE events SET total_price=COALESCE(total_price,0)+? WHERE id=?", (total, q['event_id']))
            crm._recalc_paid(conn, q['event_id'])
            ac.audit(conn, uid, 'ADDENDUM', 'quote', q['id'], new={'code': code, 'total': total})
            conn.commit()
            send_json({'success': True, 'addendum_code': code, 'total': total})
            return True

        m = re.match(r'^/api/addenda/([\w-]+)/pay$', path)
        if m and method == 'POST':
            if not (ctx['perms'].get('is_super') or ac.can(ctx['perms'], 'payments', 'create')):
                raise PermissionError('تسجيل السداد للمالية')
            a = crm._row(conn, "SELECT * FROM gen_addenda WHERE addendum_code=? AND source='hub'", (m.group(1),))
            if not a:
                raise ValueError('الملحق غير موجود')
            if a['status'] == 'مدفوع':
                raise ValueError('الملحق مدفوع من قبل')
            if a['total'] > 0:
                conn.execute("""INSERT INTO event_payments (event_id, amount, payment_method, payment_type, reference, payment_date,
                                  received_by, notes) VALUES (?,?,?,?,?,?,?,?)""",
                             (a['event_id'], a['total'], data.get('payment_method') or 'bank_transfer', 'addendum',
                              data.get('reference'), data.get('payment_date') or crm._today(), uid, 'سداد الملحق ' + a['addendum_code']))
            conn.execute("UPDATE gen_addenda SET status='مدفوع', pay_method=?, paid_at=?, reference=? WHERE addendum_code=?",
                         (data.get('payment_method') or 'تحويل', data.get('payment_date') or crm._today(), data.get('reference'), a['addendum_code']))
            crm._recalc_paid(conn, a['event_id'])
            ac.audit(conn, uid, 'ADDENDUM_PAID', 'event', a['event_id'], new={'code': a['addendum_code']})
            conn.commit()
            send_json({'success': True})
            return True

        # ───── طلبات التغيير ─────
        m = re.match(r'^/api/contracts/(\d+)/changes$', path)
        if m and method == 'POST':
            if not (ctx['perms'].get('is_super') or ac.can(ctx['perms'], 'quotes', 'edit')):
                raise PermissionError('ما عندك صلاحية طلب تغيير')
            q = _contract(conn, int(m.group(1)))
            kind = data.get('request_type') or 'تعديل العقد'
            method_ok = data.get('approval_method')
            if method_ok not in APPROVAL_METHODS:
                raise ValueError('حدد طريقة موافقة العميل (توقيع / واتساب / سداد)')
            if method_ok != 'سداد' and not data.get('evidence'):
                raise ValueError('أرفق إثبات موافقة العميل (صورة التوقيع أو الواتساب)')
            n = conn.execute("SELECT COUNT(*) FROM gen_change_requests WHERE contract_code=?", (q['contract_code'],)).fetchone()[0] + 1
            code = f"CR-{q['contract_code']}-{n}"
            if kind == 'تعديل ملحق':
                a = crm._row(conn, "SELECT * FROM gen_addenda WHERE addendum_code=? AND source='hub'", (data.get('addendum_code'),))
                if not a:
                    raise ValueError('اختر الملحق')
                if a['status'] == 'مدفوع':
                    raise ValueError('الملحق مدفوع — التعديل بملحق جديد')
                prop = {'addNo': a['addendum_code'], 'desc': (data.get('description') or a['description']).strip(),
                        'amount': crm._num(data.get('cost'), a['cost']), 'changeType': data.get('change_type') or a['change_type']}
                diff = []
                if prop['desc'] != (a['description'] or ''):
                    diff.append({'k': 'field', 'label': f"وصف الملحق ({a['addendum_code']})", 'from': a['description'], 'to': prop['desc']})
                if abs(prop['amount'] - a['cost']) > 0.004:
                    diff.append({'k': 'money', 'label': f"تكلفة الملحق قبل الضريبة ({a['addendum_code']})", 'from': a['cost'], 'to': prop['amount']})
                impact = round(prop['amount'] - a['cost'], 2)
                summary = ' · '.join(d['label'] for d in diff) or 'بدون تغيير'
            else:
                prop = {k: v for k, v in (data.get('proposed') or {}).items() if k in CONTRACT_FIELDS or k in MONEY_FIELDS or k == 'items'}
                diff = _diff_contract(conn, q, prop)
                impact = _money_impact(q, prop)
                summary = _summary(diff)
                prop['_baseRevision'] = q.get('revision')
            if not diff:
                raise ValueError('ما فيه تغيير عن الحالي')
            ev_path = _save_evidence(data.get('evidence'), code)
            conn.execute("""INSERT INTO gen_change_requests (request_code, contract_code, quote_code, operation_order, client_name,
                              request_type, summary, proposed_json, money_impact, approval_method, evidence_json, payment_json,
                              created_by, created_at, status, diff_json, source, evidence_path)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'بانتظار الاعتماد', ?, 'hub', ?)""",
                         (code, q['contract_code'], q['quote_code'],
                          (crm._row(conn, "SELECT operation_order FROM events WHERE id=?", (q['event_id'],)) or {}).get('operation_order'),
                          q['client_name'], kind, summary, json.dumps(prop, ensure_ascii=False), impact, method_ok,
                          json.dumps({'path': ev_path} if ev_path else {}, ensure_ascii=False),
                          json.dumps(data.get('payment') or {}, ensure_ascii=False), _uname(conn, uid), _now(),
                          json.dumps(diff, ensure_ascii=False, default=str), ev_path))
            ac.audit(conn, uid, 'CHANGE_REQUEST', 'quote', q['id'], new={'code': code, 'summary': summary})
            conn.commit()
            send_json({'success': True, 'request_code': code, 'summary': summary, 'money_impact': impact})
            return True

        m = re.match(r'^/api/changes/([\w-]+)/decide$', path)
        if m and method == 'POST':
            if not _can_approve(ctx):
                raise PermissionError('اعتماد طلبات التغيير للمحاسب/المالية')
            cr = crm._row(conn, "SELECT * FROM gen_change_requests WHERE request_code=? AND source='hub'", (m.group(1),))
            if not cr:
                raise ValueError('الطلب غير موجود')
            if cr['status'] != 'بانتظار الاعتماد':
                raise ValueError('الطلب ' + cr['status'])
            note = data.get('note') or ''
            if data.get('decision') != 'approve':
                conn.execute("UPDATE gen_change_requests SET status='مرفوض', approved_by=?, approved_at=?, approver_note=? WHERE request_code=?",
                             (_uname(conn, uid), _now(), note, cr['request_code']))
                conn.commit()
                send_json({'success': True, 'status': 'مرفوض'})
                return True
            q = crm._row(conn, "SELECT * FROM quotes WHERE quote_code=?", (cr['quote_code'],))
            prop = json.loads(cr['proposed_json'] or '{}')
            if cr['request_type'] == 'تعديل ملحق':
                a = crm._row(conn, "SELECT * FROM gen_addenda WHERE addendum_code=?", (prop['addNo'],))
                if a['status'] == 'مدفوع':
                    raise ValueError('الملحق انسدد بعد الطلب — ما يُطبّق')
                vat = round(prop['amount'] * _vat(conn), 2)
                total = round(prop['amount'] + vat, 2)
                conn.execute("UPDATE gen_addenda SET description=?, cost=?, vat=?, total=?, change_type=?, notes=COALESCE(notes,'')||? WHERE addendum_code=?",
                             (prop['desc'], prop['amount'], vat, total, prop['changeType'],
                              f" | عُدّل {_now()[:10]} بموجب {cr['request_code']}", a['addendum_code']))
                conn.execute("UPDATE events SET total_price=COALESCE(total_price,0)+? WHERE id=?", (total - (a['total'] or 0), a['event_id']))
                crm._recalc_paid(conn, a['event_id'])
                result = a['addendum_code']
            else:
                if (prop.get('_baseRevision') or 0) != (q.get('revision') or 0):
                    raise ValueError('العقد تعدّل بعد تقديم الطلب — اطلب من صاحب الطلب يعيده على النسخة الحالية')
                rev = _apply_contract_change(conn, q, prop, uid, cr['request_code'])
                result = f'نسخة {rev}'
            conn.execute("UPDATE gen_change_requests SET status='معتمد', approved_by=?, approved_at=?, approver_note=?, result=? WHERE request_code=?",
                         (_uname(conn, uid), _now(), note, result, cr['request_code']))
            ac.audit(conn, uid, 'CHANGE_APPROVED', 'quote', q['id'], new={'code': cr['request_code'], 'result': result})
            conn.commit()
            send_json({'success': True, 'status': 'معتمد', 'result': result})
            return True

        if path == '/api/changes' and method == 'GET':
            st = (query.get('status') or [''])[0] if isinstance(query.get('status'), list) else query.get('status')
            sql = "SELECT * FROM gen_change_requests WHERE source='hub'"
            p = []
            if st:
                sql += " AND status=?"; p.append(st)
            send_json(crm._rows(conn, sql + " ORDER BY created_at DESC LIMIT 300", p))
            return True

        if path == '/api/contracts/test-data' and method == 'DELETE':
            if not ctx['perms'].get('is_super'):
                raise PermissionError('للإدارة فقط')
            evs = [r[0] for r in conn.execute("SELECT id FROM events WHERE is_test=1")]
            for e in evs:
                conn.execute("DELETE FROM event_payments WHERE event_id=?", (e,))
                conn.execute("DELETE FROM event_confirmations WHERE event_id=?", (e,))
            conn.execute("DELETE FROM gen_addenda WHERE source='hub' AND contract_code LIKE 'T%'")
            conn.execute("DELETE FROM gen_change_requests WHERE source='hub' AND contract_code LIKE 'T%'")
            conn.execute("DELETE FROM gen_quote_revisions WHERE quote_code LIKE 'TQ%'")
            conn.execute("DELETE FROM quote_items WHERE quote_id IN (SELECT id FROM quotes WHERE is_test=1)")
            conn.execute("DELETE FROM quotes WHERE is_test=1")
            conn.execute("DELETE FROM events WHERE is_test=1")
            conn.commit()
            send_json({'success': True, 'events': len(evs)})
            return True
    except PermissionError as e:
        send_json({'error': str(e)}, 403)
        return True
    except ValueError as e:
        send_json({'error': str(e)}, 400)
        return True
    return False


def extend_quote(conn, q):
    """إضافات تفاصيل العقد (للعقود المنشأة في المنصة)"""
    if q.get('source') == 'generator':
        return q
    qc, cc = q.get('quote_code'), q.get('contract_code') or '-'
    if q.get('event_id'):
        r = conn.execute("SELECT total_price, paid_amount FROM events WHERE id=?", (q['event_id'],)).fetchone()
        if r:
            q['event_total'], q['paid_amount'] = r[0], r[1]
    q['revisions'] = crm._rows(conn, "SELECT revision, revision_date, reason, total_with_vat, by_name FROM gen_quote_revisions WHERE quote_code=? ORDER BY revision", (qc,))
    q['addenda'] = crm._rows(conn, "SELECT * FROM gen_addenda WHERE contract_code=? AND source='hub' ORDER BY id", (cc,))
    q['changes'] = crm._rows(conn, """SELECT request_code, request_type, summary, money_impact, approval_method, evidence_path, created_by,
                                         created_at, status, approved_by, approved_at, approver_note, result, diff_json
                                      FROM gen_change_requests WHERE contract_code=? AND source='hub' ORDER BY created_at""", (cc,))
    return q
