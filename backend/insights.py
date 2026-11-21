"""
الزبدة — تحليل ذكي مستمر لبيانات أبيلا (لمنصور وأ. نوف)
==========================================================
طبقتان:
1) قواعد تحليل ثابتة تشتغل على كل البيانات كل ما تنفتح اللوحة (بدون أي خدمة خارجية):
   السيولة والتحصيل · الربحية · شذوذ التكاليف · الموردين · انضباط الفواتير · مخاطر التشغيل · المبيعات · الجرد · السعة.
2) ملخص مكتوب بالذكاء الاصطناعي (اختياري): إذا ضُبط ANTHROPIC_API_KEY في Railway يكتب Claude «الزبدة» بجمل قصيرة
   من نتائج القواعد والأرقام، ويتحدّث كل 6 ساعات (أو بزر التحديث).
"""
import json, os, statistics, datetime, urllib.request

VAT = 1.15
LEVEL_ORDER = {'red': 0, 'amber': 1, 'info': 2, 'green': 3}


def _today():
    return (datetime.datetime.utcnow() + datetime.timedelta(hours=3)).date()


def _d(s):
    try:
        return datetime.date.fromisoformat(str(s)[:10])
    except Exception:
        return None


def _f(x):
    try:
        return float(x or 0)
    except Exception:
        return 0.0


def _m(n):
    return f"{n:,.0f}"


def build(conn, base):
    """base = ناتج today_routes.compute"""
    T = _today()
    out = []

    def add(level, area, title, detail='', link='', score=0):
        out.append({'level': level, 'area': area, 'title': title, 'detail': detail, 'link': link, 'score': score})

    k = base['kpis']
    # ── 1) السيولة والتحصيل ──
    month = T.strftime('%Y-%m')
    prev = (T.replace(day=1) - datetime.timedelta(days=1)).strftime('%Y-%m')
    col = {r[0]: r[1] for r in conn.execute("""SELECT substr(COALESCE(payment_date, recorded_at),1,7) m, SUM(amount) FROM gen_payments
                                              WHERE substr(COALESCE(payment_date, recorded_at),1,7) IN (?,?) GROUP BY m""", (month, prev))}
    cm, pm = _f(col.get(month)), _f(col.get(prev))
    day_frac = T.day / 30.0
    if pm and day_frac > 0.3:
        pace = cm / day_frac
        if pace < pm * 0.7:
            add('amber', 'السيولة', f'التحصيل هذا الشهر أبطأ من الشهر الماضي',
                f'محصّل {_m(cm)} حتى الآن؛ بنفس الوتيرة ينتهي الشهر عند ~{_m(pace)} مقابل {_m(pm)} الشهر الماضي', '/today', 60)
        elif pace > pm * 1.2:
            add('green', 'السيولة', 'التحصيل أسرع من الشهر الماضي', f'{_m(cm)} حتى الآن (الماضي {_m(pm)})', '/today', 10)
    od = base['overdue']
    if od:
        tot = sum(x['remaining'] for x in od)
        old = [x for x in od if _d(x['date']) and (T - _d(x['date'])).days > 30]
        top = '، '.join(f"{x['client']} ({_m(x['remaining'])})" for x in od[:3])
        add('red' if tot > 20000 or old else 'amber', 'التحصيل', f'{len(od)} عميل خلصت مناسبته وعليه متبقي {_m(tot)} ريال',
            f"الأكبر: {top}" + (f" · {len(old)} منها متأخرة أكثر من 30 يوم" if old else ''), '/today', 90 + len(old))
    # ── 2) الربحية ──
    pnl = [p for p in base['pnl'] if p['rev'] > 0 and (p['cost'] > 0)]
    if pnl:
        neg = [p for p in pnl if p['profit'] < 0]
        low = [p for p in pnl if p['margin'] is not None and 0 <= p['margin'] < 20]
        if neg:
            add('red', 'الربحية', f'{len(neg)} مناسبة خسرانة آخر 90 يوم',
                '، '.join(f"{p['o']} {p['client']} ({_m(p['profit'])})" for p in neg[:4]), '/today', 95)
        if low:
            add('amber', 'الربحية', f'{len(low)} مناسبة هامشها أقل من 20%',
                '، '.join(f"{p['o']} ({p['margin']}%)" for p in low[:5]), '/today', 55)
        margins = [p['margin'] for p in pnl if p['margin'] is not None]
        if len(margins) >= 3:
            add('info', 'الربحية', f'متوسط هامش الربح آخر 90 يوم {statistics.mean(margins):.0f}%',
                f'على {len(margins)} مناسبة فيها مصاريف مسجلة · الوسيط {statistics.median(margins):.0f}%', '/today', 20)
    no_cost = [p for p in base['pnl'] if p['rev'] > 0 and not p['cost']]
    if no_cost:
        add('amber', 'انضباط البيانات', f'{len(no_cost)} مناسبة انتهت بدون أي مصاريف مسجلة',
            'الربحية لها غير حقيقية حتى تُسجّل مصاريفها: ' + '، '.join(p['o'] for p in no_cost[:6]), '/expenses', 50)
    # ── 3) شذوذ التكاليف (ضيافة/إشراف/تنفيذ لكل مناسبة مقارنة بالوسيط) ──
    for key, lbl in (('hos', 'الضيافة'), ('sup', 'الإشراف'), ('exe', 'التنفيذ')):
        vals = [p[key] for p in base['pnl'] if p.get(key)]
        if len(vals) >= 5:
            med = statistics.median(vals)
            hi = [p for p in base['pnl'] if p.get(key) and p[key] > med * 1.8 and p[key] - med > 1500]
            if hi:
                add('amber', 'التكاليف', f'مصاريف {lbl} مرتفعة بشكل غير معتاد في {len(hi)} مناسبة',
                    f'الوسيط {_m(med)} ريال للمناسبة؛ ' + '، '.join(f"{p['o']} ({_m(p[key])})" for p in hi[:4]), '/expenses', 45)
    # ── 4) الموردين ──
    rows = conn.execute("""SELECT sup_key, substr(COALESCE(invoice_date, entered_at),1,7) m, SUM(net) FROM exp_invoices
                           WHERE status<>'deleted' AND COALESCE(is_test,0)=0 AND COALESCE(sup_key,'')<>'' GROUP BY sup_key, m""").fetchall()
    by = {}
    for s, m, v in rows:
        by.setdefault(s, {})[m] = _f(v)
    months3 = [(T.replace(day=1) - datetime.timedelta(days=30 * i)).strftime('%Y-%m') for i in (1, 2, 3)]
    spikes = []
    for s, mm in by.items():
        cur = mm.get(month, 0)
        avg = sum(mm.get(x, 0) for x in months3) / 3
        if avg > 2000 and cur > avg * 1.5 and day_frac > 0.3:
            spikes.append((s, cur, avg))
    if spikes:
        spikes.sort(key=lambda x: -(x[1] - x[2]))
        add('amber', 'الموردين', f'صرف أعلى من المعتاد عند {len(spikes)} مورد هذا الشهر',
            '، '.join(f"{s}: {_m(c)} (المعتاد {_m(a)})" for s, c, a in spikes[:4]), '/expenses', 40)
    tot_m = sum(mm.get(month, 0) for mm in by.values())
    if tot_m > 10000:
        s, mm = max(by.items(), key=lambda kv: kv[1].get(month, 0))
        share = mm.get(month, 0) / tot_m * 100
        if share > 35:
            add('info', 'الموردين', f'{s} يمثّل {share:.0f}% من مصاريف الشهر', f'{_m(mm.get(month, 0))} من {_m(tot_m)}', '/expenses', 25)
    aged = conn.execute("""SELECT sup_key, SUM(remaining), MIN(COALESCE(invoice_date, entered_at)) FROM exp_invoices
                           WHERE status<>'deleted' AND COALESCE(is_test,0)=0 AND remaining>0.009 GROUP BY sup_key""").fetchall()
    old_dues = [(s, _f(r), o) for s, r, o in aged if _d(o) and (T - _d(o)).days > 30 and _f(r) > 500]
    if old_dues:
        old_dues.sort(key=lambda x: -x[1])
        add('amber', 'الموردين', f'مستحقات موردين متأخرة أكثر من 30 يوم: {_m(sum(x[1] for x in old_dues))} ريال',
            '، '.join(f"{s} ({_m(r)})" for s, r, _ in old_dues[:4]), '/expenses', 50)
    # ── 5) انضباط الفواتير ──
    miss = conn.execute("""SELECT person, COUNT(*) FROM exp_invoices WHERE status<>'deleted' AND COALESCE(is_test,0)=0
                           AND COALESCE(invoice_date, entered_at) >= ? AND (COALESCE(invoice_number,'')='' OR COALESCE(attachment,'')='')
                           GROUP BY person ORDER BY 2 DESC""", ((T - datetime.timedelta(days=30)).isoformat(),)).fetchall()
    mt = sum(n for _, n in miss)
    if mt >= 3:
        add('amber', 'انضباط البيانات', f'{mt} فاتورة آخر 30 يوم بدون رقم فاتورة أو صورة',
            'حسب المسؤول: ' + '، '.join(f"{p or 'غير محدد'} ({n})" for p, n in miss[:5]), '/expenses', 35)
    # ── 6) مخاطر التشغيل ──
    up = base['upcoming']
    unconf = [u for u in up if not u['confirmed'] and _d(u['date']) and (_d(u['date']) - T).days <= 7]
    if unconf:
        add('red', 'التشغيل', f'{len(unconf)} مناسبة خلال أسبوع بدون تأكيد موعد', '، '.join(f"{u['o']} {u['client']}" for u in unconf[:5]), '/operations', 85)
    noplan = []
    for u in up:
        q = conn.execute("""SELECT p.approved_version FROM opn_orders o LEFT JOIN wpg_plans p ON p.quote_code=o.Q WHERE o.O=?""", (u['o'],)).fetchone()
        if not q or not q[0]:
            if _d(u['date']) and (_d(u['date']) - T).days <= 21:
                noplan.append(u)
    if noplan:
        add('red' if any((_d(u['date']) - T).days <= 10 for u in noplan) else 'amber', 'التشغيل',
            f'{len(noplan)} مناسبة خلال 3 أسابيع بدون خطة عمل معتمدة', '، '.join(f"{u['o']} ({u['date']})" for u in noplan[:5]), '/workplans', 80)
    try:
        import ops_native
        late = {}
        orders, byQ = ops_native.load(conn)
        now = ops_native.now_r()
        for o in orders:
            if ops_native.t_(o.get('closed')) == 'نعم' or ops_native.t_(o.get('is_test')) == '1':
                continue
            c = ops_native.compute_order(conn, o, byQ.get(o['Q'], []), now)
            for x in c['_T']:
                if x['late']:
                    late[x['t']['dept']] = late.get(x['t']['dept'], 0) + 1
        if late:
            worst = sorted(late.items(), key=lambda kv: -kv[1])
            add('red' if worst[0][1] >= 5 else 'amber', 'التشغيل', f'{sum(late.values())} مهمة متأخرة — أكثر قسم: {worst[0][0]} ({worst[0][1]})',
                '، '.join(f"{d} {n}" for d, n in worst), '/operations', 70)
    except Exception:
        pass
    # ── 7) المبيعات ──
    qs = base['quotes']
    stale = [q for q in qs if _d(q.get('created_at')) and (T - _d(q['created_at'])).days > 14]
    if stale:
        add('amber', 'المبيعات', f'{len(stale)} عرض سعر مفتوح أكثر من أسبوعين بدون تحويل',
            f"قيمتها {_m(sum(_f(q.get('total_with_vat')) for q in stale))} · " + '، '.join(q['client_name'] or q['quote_code'] for q in stale[:5]), '/dashboard/', 40)
    r = conn.execute("""SELECT COUNT(*), SUM(CASE WHEN COALESCE(contract_code,'')<>'' THEN 1 ELSE 0 END) FROM quotes
                        WHERE COALESCE(is_test,0)=0 AND created_at >= ?""", ((T - datetime.timedelta(days=60)).isoformat(),)).fetchone()
    if r and r[0] and r[0] >= 5:
        add('info', 'المبيعات', f'نسبة تحويل العروض لعقود آخر 60 يوم: {(r[1] or 0) / r[0] * 100:.0f}%', f'{r[1] or 0} عقد من {r[0]} عرض', '/dashboard/', 15)
    nc = k.get('newContracts') or 0
    if nc:
        add('green', 'المبيعات', f'{nc} عقد جديد هذا الشهر بقيمة {_m(k.get("newContractsValue") or 0)}', '', '/dashboard/', 5)
    # ── 8) الجرد ──
    try:
        rep = 0
        for (cj,) in conn.execute("SELECT counts_json FROM jrd_items WHERE section='asset' AND deleted=0"):
            d = json.loads(cj or '{}')
            rep += d.get('يحتاج صيانة', 0) + d.get('تالف', 0)
        if rep:
            add('info', 'الجرد', f'{rep} قطعة تحتاج صيانة أو تالفة', 'راجعها قبل ما تدخل في خطط العمل الجاية', '/jard', 20)
    except Exception:
        pass
    # ── 9) السعة ──
    try:
        cap = int((conn.execute("SELECT value FROM settings WHERE key='ops_capacity'").fetchone() or ['2'])[0] or 2)
        days = {}
        for u in up:
            days[u['date']] = days.get(u['date'], 0) + 1
        busy = [(d, n) for d, n in days.items() if n > cap]
        if busy:
            add('amber', 'السعة', f'{len(busy)} يوم فيه مناسبات أكثر من السعة ({cap})', '، '.join(f"{d}: {n}" for d, n in busy[:5]), '/operations', 60)
    except Exception:
        pass
    out.sort(key=lambda x: (LEVEL_ORDER[x['level']], -x['score']))
    return out


# ───────────────────────── ملخص الذكاء الاصطناعي ─────────────────────────
def _setting(conn, k):
    r = conn.execute("SELECT value FROM settings WHERE key=?", (k,)).fetchone()
    return r[0] if r else None


def ai_brief(conn, base, items, force=False):
    key = os.environ.get('ANTHROPIC_API_KEY')
    if not key:
        return {'enabled': False}
    cached = _setting(conn, 'ai_brief_cache')
    if cached and not force:
        try:
            c = json.loads(cached)
            if (datetime.datetime.utcnow() - datetime.datetime.fromisoformat(c['at'])).total_seconds() < 6 * 3600:
                return dict(c, enabled=True)
        except Exception:
            pass
    facts = {'kpis': base['kpis'], 'monthly': base['monthly'][-4:], 'insights': items[:20],
             'upcoming': base['upcoming'][:12], 'overdue_top': base['overdue'][:8], 'suppliers_top': base['suppliers'][:8]}
    prompt = ("أنت محلل أعمال لشركة أبيلا للأفراح والمناسبات في الرياض. هذه أرقام الشركة ونتائج التحليل الآلي (JSON). "
              "اكتب «الزبدة» لصاحب الشركة منصور والأستاذة نوف: 5 إلى 7 نقاط قصيرة جداً باللهجة السعودية البسيطة، "
              "كل نقطة سطر واحد يبدأ بالأهم: وش الوضع، وش الخطر، ووش المطلوب منهم بالضبط (قرار أو متابعة مع شخص). "
              "لا تخترع أرقاماً غير موجودة، ولا تكرر نفس المعلومة، وبدون مقدمات أو خاتمة. "
              "أرجع JSON فقط بالشكل: {\"headline\": \"جملة واحدة عن حال الشركة\", \"points\": [\"...\"]}\n\n"
              + json.dumps(facts, ensure_ascii=False, default=str))
    body = json.dumps({'model': os.environ.get('ABELLA_AI_MODEL', 'claude-sonnet-5-5'), 'max_tokens': 1200,
                       'messages': [{'role': 'user', 'content': prompt}]}).encode()
    req = urllib.request.Request('https://api.anthropic.com/v1/messages', data=body, method='POST',
                                 headers={'x-api-key': key, 'anthropic-version': '2023-06-01', 'content-type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            txt = ''.join(b.get('text', '') for b in json.loads(r.read())['content'])
        s, e = txt.find('{'), txt.rfind('}')
        data = json.loads(txt[s:e + 1])
        res = {'at': datetime.datetime.utcnow().isoformat(timespec='seconds'), 'headline': data.get('headline', ''), 'points': data.get('points', [])[:8]}
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('ai_brief_cache', ?)", (json.dumps(res, ensure_ascii=False),))
        conn.commit()
        return dict(res, enabled=True)
    except Exception as ex:
        if cached:
            try:
                return dict(json.loads(cached), enabled=True, stale=True)
            except Exception:
                pass
        return {'enabled': True, 'error': str(ex)[:200]}
