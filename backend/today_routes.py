"""
«أبيلا اليوم» داخل المنصة (/today) — لوحة الإدارة (أ. نوف ومنصور)
==================================================================
تُحسب من بيانات المنصة مباشرة: العقود + الدفعات + المصروفات الأربعة + إدارة العمليات + يوم التنفيذ + الجرد.
الأرقام بالصافي قبل الضريبة للإيراد والتكلفة (الإيراد = الإجمالي ÷ 1.15، التكلفة = صافي التكلفة).
"""
import json, datetime

VAT = 1.15


def _r(x):
    return round(float(x or 0), 2)


def _today():
    return (datetime.datetime.utcnow() + datetime.timedelta(hours=3)).strftime('%Y-%m-%d')


def _add(d, n):
    return (datetime.date.fromisoformat(d) + datetime.timedelta(days=n)).isoformat()


def compute(conn):
    today = _today()
    month = today[:7]
    # ── العقود (جدول العقود الأساسية + المنصة) ──
    paid_by_c = {}
    for r in conn.execute("SELECT contract_code, SUM(amount) FROM gen_payments WHERE COALESCE(contract_code,'')<>'' GROUP BY contract_code"):
        paid_by_c[r[0]] = r[1] or 0
    cons = []
    for r in conn.execute("""SELECT operation_order o, contract_code b, customer_name client, event_type type, venue, expected_date e, actual_date a,
                                   total_revenue rev, received, remaining, status FROM sheet_contracts
                            WHERE COALESCE(contract_code,'')<>'' AND COALESCE(operation_order,'') NOT IN ('', 'O1001')"""):
        d = dict(r)
        d['date'] = d['a'] or d['e']
        d['received'] = max(float(d['received'] or 0), float(paid_by_c.get(d['b'], 0)))
        d['rev'] = float(d['rev'] or 0)
        d['remaining'] = max(0.0, d['rev'] - d['received'])
        cons.append(d)
    by_o = {c['o']: c for c in cons}
    # ── المصروفات ──
    exp = [dict(r) for r in conn.execute("""SELECT k, operation_order o, sup_key, item, total, net, paid, remaining, invoice_date, entered_at, invoice_number,
                                                  attachment, person, source FROM exp_invoices WHERE status<>'deleted' AND COALESCE(is_test,0)=0""")]
    cost_o = {}
    for e in exp:
        c = cost_o.setdefault(e['o'] or '—', {'sup': 0, 'hos': 0, 'exe': 0, 'pur': 0})
        c[e['k']] += float(e['net'] or 0)

    def ev_month(c):
        return (c['date'] or '')[:7]
    # ── شهرياً (حسب شهر المناسبة) — آخر 6 أشهر + الشهرين القادمة ──
    months = sorted({ev_month(c) for c in cons if c['date']})
    lo = (datetime.date.fromisoformat(today[:7] + '-01') - datetime.timedelta(days=170)).isoformat()[:7]
    hi = (datetime.date.fromisoformat(today[:7] + '-01') + datetime.timedelta(days=62)).isoformat()[:7]
    monthly = []
    for m in [x for x in months if lo <= x <= hi]:
        cs = [c for c in cons if ev_month(c) == m]
        rev = sum(c['rev'] for c in cs) / VAT
        cost = {k: sum(cost_o.get(c['o'], {}).get(k, 0) for c in cs) for k in ('sup', 'hos', 'exe', 'pur')}
        tc = sum(cost.values())
        monthly.append({'m': m, 'n': len(cs), 'rev': _r(rev), **{k: _r(v) for k, v in cost.items()}, 'cost': _r(tc), 'profit': _r(rev - tc),
                        'received': _r(sum(c['received'] for c in cs)), 'remaining': _r(sum(c['remaining'] for c in cs))})
    # ── مؤشرات الشهر ──
    cm = [c for c in cons if ev_month(c) == month]
    exp_month = [e for e in exp if ((e['invoice_date'] or e['entered_at'] or '')[:7]) == month]
    pay_month = conn.execute("SELECT COALESCE(SUM(amount),0), COUNT(*) FROM gen_payments WHERE substr(COALESCE(payment_date, recorded_at),1,7)=?", (month,)).fetchone()
    new_contracts = conn.execute("""SELECT COUNT(*), COALESCE(SUM(total_with_vat),0) FROM quotes WHERE COALESCE(contract_code,'')<>'' AND COALESCE(is_test,0)=0
                                    AND substr(COALESCE(contracted_at, created_at),1,7)=?""", (month,)).fetchone()
    kpis = {'month': month, 'events': len(cm), 'eventsRevenue': _r(sum(c['rev'] for c in cm) / VAT),
            'collected': _r(pay_month[0]), 'payments': pay_month[1], 'expenses': _r(sum(float(e['net'] or 0) for e in exp_month)),
            'expensesN': len(exp_month), 'newContracts': new_contracts[0], 'newContractsValue': _r(new_contracts[1]),
            'receivable': _r(sum(c['remaining'] for c in cons if c['status'] != 'ملغي')),
            'supplierDues': _r(sum(float(e['remaining'] or 0) for e in exp if float(e['remaining'] or 0) > 0.009))}
    # ── القادمة (30 يوم) مع حالة العمليات ──
    ops = {r['O']: dict(r) for r in conn.execute("SELECT O, Q, C, E, cls, closed FROM opn_orders WHERE COALESCE(O,'')<>''")}
    exn = {r['code']: dict(r) for r in conn.execute("""SELECT p.code, COUNT(t.id) n, SUM(t.status='done') done FROM exn_projects p
                                                       LEFT JOIN exn_tasks t ON t.pid=p.id GROUP BY p.id""")}
    upcoming = []
    for c in sorted(cons, key=lambda c: c['date'] or '9'):
        if c['date'] and today <= c['date'] <= _add(today, 30) and 'ملغ' not in (c['status'] or ''):
            o = ops.get(c['o']) or {}
            x = exn.get(c['o'])
            upcoming.append({'o': c['o'], 'client': c['client'], 'type': c['type'], 'venue': c['venue'], 'date': c['date'],
                             'confirmed': bool(o.get('C')), 'rev': _r(c['rev']), 'remaining': _r(c['remaining']),
                             'exec': f"{x['done'] or 0}/{x['n']}" if x else ''})
    # ── مستحقات متأخرة على العملاء (المناسبة صارت وفيه متبقي) ──
    overdue = sorted([{'o': c['o'], 'client': c['client'], 'date': c['date'], 'remaining': _r(c['remaining']), 'rev': _r(c['rev'])}
                      for c in cons if c['date'] and c['date'] < today and c['remaining'] > 1 and 'ملغ' not in (c['status'] or '')],
                     key=lambda x: -x['remaining'])
    # ── ربحية كل مناسبة (المنتهية آخر 90 يوم) ──
    pnl = []
    for c in cons:
        if c['date'] and _add(today, -90) <= c['date'] <= today:
            co = cost_o.get(c['o'], {})
            tc = sum(co.values())
            rev = c['rev'] / VAT
            pnl.append({'o': c['o'], 'client': c['client'], 'date': c['date'], 'rev': _r(rev), 'cost': _r(tc), 'profit': _r(rev - tc),
                        'margin': round((rev - tc) / rev * 100, 1) if rev else None, **{k: _r(v) for k, v in co.items()},
                        'flags': ' · '.join(x for x in [('لا مصاريف ضيافة' if not co.get('hos') else ''), ('لا مصاريف إشراف' if not co.get('sup') else '')] if x)})
    pnl.sort(key=lambda x: x['date'], reverse=True)
    # ── الموردين ──
    sup_rows = {}
    for e in exp:
        s = sup_rows.setdefault(e['sup_key'] or e['item'] or '—', {'name': e['sup_key'] or e['item'] or '—', 'total': 0, 'month': 0, 'due': 0, 'n': 0})
        s['total'] += float(e['net'] or 0); s['n'] += 1; s['due'] += max(0, float(e['remaining'] or 0))
        if ((e['invoice_date'] or e['entered_at'] or '')[:7]) == month:
            s['month'] += float(e['net'] or 0)
    suppliers = sorted(({k: (_r(v) if isinstance(v, float) else v) for k, v in s.items()} for s in sup_rows.values()), key=lambda s: -s['total'])[:25]
    # ── العروض المفتوحة ──
    qs = [dict(r) for r in conn.execute("""SELECT quote_code, client_name, event_type, expected_date, total_with_vat, gen_status, status, created_at FROM quotes
                                          WHERE COALESCE(contract_code,'')='' AND status NOT IN ('rejected','cancelled','expired') AND COALESCE(is_test,0)=0
                                          ORDER BY created_at DESC LIMIT 30""")]
    # ── تنبيهات ──
    alerts = []
    red = conn.execute("SELECT COUNT(*) FROM opn_orders WHERE COALESCE(closed,'')<>'نعم'").fetchone()[0]
    miss = sum(1 for e in exp if e['source'] == 'sheet' and (not e['invoice_number'] or not e['attachment']) and (e['invoice_date'] or '') >= _add(today, -60))
    if miss:
        alerts.append(f'{miss} فاتورة مصروفات آخر 60 يوم بدون رقم فاتورة أو صورة')
    pend = conn.execute("SELECT COUNT(*) FROM exp_requests WHERE status='بانتظار الاعتماد'").fetchone()[0]
    if pend:
        alerts.append(f'{pend} طلب تعديل/حذف مصروفات بانتظار اعتماد منصور')
    unconf = [u for u in upcoming if not u['confirmed'] and u['date'] <= _add(today, 7)]
    if unconf:
        alerts.append(f"{len(unconf)} مناسبة خلال أسبوع بدون تأكيد موعد: " + '، '.join(u['o'] for u in unconf[:6]))
    if overdue:
        alerts.append(f"{len(overdue)} عقد انتهت مناسبته وعليه متبقي بإجمالي {sum(x['remaining'] for x in overdue):,.0f} ريال")
    try:
        dmg = conn.execute("SELECT counts_json FROM jrd_items WHERE section='asset' AND deleted=0").fetchall()
        rep = sum(json.loads(r[0] or '{}').get('يحتاج صيانة', 0) + json.loads(r[0] or '{}').get('تالف', 0) for r in dmg)
        if rep:
            alerts.append(f'{rep} قطعة في الجرد تحتاج صيانة أو تالفة')
    except Exception:
        pass
    pending_photos = conn.execute("SELECT COUNT(*) FROM exn_photos WHERE COALESCE(approval,'بانتظار')='بانتظار'").fetchone()[0]
    if pending_photos:
        alerts.append(f'{pending_photos} صورة من يوم التنفيذ بانتظار الاعتماد')
    return {'generated': datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M'), 'today': today, 'kpis': kpis, 'monthly': monthly,
            'upcoming': upcoming, 'overdue': overdue[:30], 'pnl': pnl, 'suppliers': suppliers, 'quotes': qs, 'alerts': alerts,
            'activeOrders': red}


def handle(h, conn, method, path, query, data, ctx, send_json):
    if path != '/api/today' or method != 'GET':
        return False
    if not (ctx['perms'].get('is_super') or ctx['user'].get('role') in ('owner', 'general_manager')):
        send_json({'error': 'اللوحة للإدارة'}, 403)
        return True
    base = compute(conn)
    import insights
    try:
        base['insights'] = insights.build(conn, base)
    except Exception as e:
        base['insights'] = [{'level': 'info', 'area': 'النظام', 'title': 'تعذّر التحليل', 'detail': str(e)[:200], 'link': '', 'score': 0}]
    q = query.get('ai') if isinstance(query, dict) else None
    force = bool(q and (q[0] if isinstance(q, list) else q) == 'refresh')
    try:
        base['ai'] = insights.ai_brief(conn, base, base['insights'], force=force)
    except Exception as e:
        base['ai'] = {'enabled': True, 'error': str(e)[:200]}
    send_json(base)
    return True
