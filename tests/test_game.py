import json, math, sys, time, random
from playwright.sync_api import sync_playwright
import pathlib
URL=(pathlib.Path(__file__).resolve().parent.parent/'index.html').as_uri()
OUT='/tmp/sannoir-shots'
import os; os.makedirs(OUT,exist_ok=True)
errors=[]; fails=[]
def check(cond,msg):
    if not cond: fails.append(msg); print('FAIL:',msg)
    else: print('ok:',msg)
def S(p): return p.evaluate('JSON.parse(JSON.stringify(SN.S))')
def adv(p,m): p.evaluate(f'SN.advance({m})')
def inv(p,where):
    s=S(p)
    bad=[]
    def walk(o,path=''):
        if isinstance(o,float) and (math.isnan(o) or math.isinf(o)): bad.append(path)
        elif isinstance(o,dict): [walk(v,path+'.'+k) for k,v in o.items()]
        elif isinstance(o,list): [walk(v,path+f'[{i}]') for i,v in enumerate(o)]
    walk(s)
    g=[c for c in s['cars'] if c['loc']=='garage']; st=[c for c in s['cars'] if c['loc']=='stock']
    ok = not bad and len(g)<=5 and len(st)<=30 and s['holds']>=-0.01 and s['bal']-s['holds']>=-0.5 and s['safe']>=0
    if not ok: fails.append(f'invariant @{where}: nan={bad[:3]} g={len(g)} st={len(st)} holds={s["holds"]} bal={s["bal"]} safe={s["safe"]}')
    return s
def click(p,sel,timeout=3000):
    p.locator(sel).first.click(timeout=timeout)
def run():
    with sync_playwright() as pw:
        b=pw.chromium.launch(**({'executable_path':'/usr/bin/google-chrome'} if os.path.exists('/usr/bin/google-chrome') else {}),args=['--no-sandbox'])
        ctx=b.new_context(viewport={'width':390,'height':844},device_scale_factor=2)
        ctx.route('**/telegram.org/**',lambda r:r.abort()); ctx.route('**/fonts.googleapis.com/**',lambda r:r.abort()); ctx.route('**/fonts.gstatic.com/**',lambda r:r.abort())
        p=ctx.new_page()
        p.on('pageerror',lambda e:errors.append('pageerror: '+str(e)))
        p.on('console',lambda m:errors.append('console: '+m.text) if m.type=='error' and 'fonts' not in m.text and 'ERR_FAILED' not in m.text else None)
        p.goto(URL,wait_until='domcontentloaded'); p.wait_for_timeout(500)
        p.evaluate('localStorage.clear()'); p.reload(wait_until='domcontentloaded'); p.wait_for_timeout(500)
        p.screenshot(path=f'{OUT}/01_city.png',full_page=True)
        s=inv(p,'start'); check(s['bal']==1500 and len(s['cars'])==2,'старт: 1500 Н и 2 машины')
        t0=S(p)['t']; p.wait_for_timeout(3200); check(S(p)['t']-t0>=3,'реальное время идёт: 1 сек = 1 игровая минута')
        p.reload(wait_until='domcontentloaded'); p.wait_for_timeout(400); check(S(p)['t']>=t0+3,'прогресс сохраняется после перезагрузки')
        click(p,'#devbtn'); click(p,'[data-dev="60"]'); check(S(p)['t']>=t0+63,'кнопка перемотки +1 час'); click(p,'#devbtn')
        # collect
        adv(p,60); click(p,'[data-act=collect]'); s=inv(p,'collect')
        check(s['bal']>1500,'сбор сейфа увеличил баланс'); check(s['cnt'].get('collect')==1,'счётчик сбора')
        # tasks: claim t1
        click(p,'[data-act=tasks]'); p.wait_for_timeout(200); p.screenshot(path=f'{OUT}/02_tasks.png',full_page=True)
        b0=S(p)['bal']; click(p,'[data-tut=t1]'); check(S(p)['bal']==b0+200,'награда за первое задание +200')
        click(p,'#sheet [data-close]')
        # garage: open port
        click(p,'[data-tab=garage]'); p.screenshot(path=f'{OUT}/03_garage.png',full_page=True)
        n0=len(S(p)['cars']); click(p,'[data-act=openPort]'); p.wait_for_timeout(1700)
        p.screenshot(path=f'{OUT}/04_reveal.png'); s=inv(p,'openPort')
        check(len(s['cars'])==n0+1,'контейнер дал машину'); check(p.locator('#modal.on').count()==1,'окно с машиной открыто')
        click(p,'#sheet [data-close]')
        # car modal: move & back
        click(p,'[data-car]'); p.wait_for_timeout(150); p.screenshot(path=f'{OUT}/05_car.png',full_page=True)
        u=int(p.locator('[data-move]').first.get_attribute('data-move'))
        click(p,'[data-move]'); s=S(p); c=[x for x in s['cars'] if x['u']==u][0]; check(c['loc']=='stock','машина ушла на склад')
        p.locator(f'[data-car="{u}"]').click(); click(p,'[data-move]'); s=S(p); c=[x for x in s['cars'] if x['u']==u][0]; check(c['loc']=='garage','машина вернулась в гараж')
        # fill garage to test 5 limit + stock
        p.evaluate("for(let i=0;i<8;i++){placeCar(pick(TIER.C).id)} render()")
        s=inv(p,'fill'); g=[c for c in s['cars'] if c['loc']=='garage']; check(len(g)==5,'в гараже ровно 5 машин')
        # sell to city
        st=[c for c in s['cars'] if c['loc']=='stock'][0]; b0=s['bal']; p.locator(f'[data-car="{st["u"]}"]').click(); click(p,'[data-sellcity]')
        s=inv(p,'sellCity'); check(s['bal']>b0 and not any(c['u']==st['u'] for c in s['cars']),'продажа городу')
        # market auction
        click(p,'[data-tab=market]')
        for _ in range(20):
            s=S(p); act=[l for l in s['lots'] if not l['res'] and l['start']<=s['t']<l['end'] and l['k']=='E']
            if act: break
            adv(p,5)
        p.evaluate('SN.S.bal+=20000'); p.evaluate('SN.render()')
        s=S(p); act=[l for l in s['lots'] if not l['res'] and l['start']<=s['t']<l['end'] and l['k']=='E']
        check(bool(act),'есть активный лот «Экспорт»')
        if act:
            lid=act[0]['id']; p.fill(f'#bid{lid}','9000'); click(p,f'[data-bid="{lid}"]'); s=inv(p,'bid')
            check(s['holds']>=9000,'ставка заморозила деньги'); p.screenshot(path=f'{OUT}/06_auction.png',full_page=True)
            n0=len(s['cars']); adv(p,40); s=inv(p,'lotEnd')
            l=[x for x in s['lots'] if x['id']==lid]
            check(s['holds']==0,'после торгов заморозка снята')
            if l: check(l[0]['res'] is not None,'лот завершён'); 
            check(s['wins']['E']==1 and len(s['cars'])==n0+1,'максимум 9000 выигрывает «Экспорт» (стоимость ≤7500)')
            p.evaluate('ui.modal=null;SN.render()')
            # second bid same day blocked
            for _ in range(20):
                s=S(p); act=[l for l in s['lots'] if not l['res'] and l['start']<=s['t']<l['end'] and l['k']=='E']
                if act: break
                adv(p,5)
            if act and S(p)['wins']['E']==1 and S(p)['wins']['day']==(S(p)['t']//1440+1):
                check(p.locator(f'#bid{act[0]["id"]}').count()==0,'второй выигрыш «Экспорта» за день заблокирован')
        # trade offers
        p.evaluate("market();market();market();market();market();market();SN.render()")
        click(p,'[data-sub="market:trade"]'); p.screenshot(path=f'{OUT}/07_trade.png',full_page=True)
        s=S(p)
        if s['offers']:
            t0=s['stats']['trades']; click(p,'[data-offer]'); s=inv(p,'offer'); check(s['stats']['trades']==t0+1,'принятие предложения обмена/продажи')
        else: print('no offers generated (random)')
        # listing
        s=S(p); c=[x for x in s['cars'] if not x['lock'] and x['id']!='noire'][0]
        p.evaluate(f"ui.tab='garage';SN.render()"); p.locator(f'[data-car="{c["u"]}"]').click()
        p.fill('#lp','1'); click(p,f'[data-list="{c["u"]}"]'); check(len(S(p)['listings'])==0,'цена ниже коридора отклонена')
        mp=p.evaluate(f"marketPrice('{c['id']}')"); p.fill('#lp',str(mp)); click(p,f'[data-list="{c["u"]}"]'); check(len(S(p)['listings'])==1,'объявление в коридоре принято')
        # friends + gift
        p.evaluate("ui.tab='city';SN.render()"); click(p,'[data-act=friends]'); click(p,'[data-act=invite]'); click(p,'[data-act=invite]')
        p.screenshot(path=f'{OUT}/08_friends.png',full_page=True); click(p,'#sheet [data-close]')
        s=S(p); check(len(s['friends'])==2,'два друга'); c=[x for x in s['cars'] if not x['lock'] and x['id']!='noire'][-1]
        p.evaluate("ui.tab='garage';SN.render()"); p.locator(f'[data-car="{c["u"]}"]').click(); click(p,f'[data-giftopen="{c["u"]}"]'); click(p,'[data-gift]')
        s=inv(p,'gift'); check(len(s['gifts'])==1 and not any(x['u']==c['u'] for x in s['cars']),'подарок другу')
        # stocks
        click(p,'[data-tab=stocks]'); p.screenshot(path=f'{OUT}/09_stocks.png',full_page=True)
        pr=p.evaluate("SN.S.stocks.find(x=>x.id==='chrom').p")
        p.fill('#q_chrom','1000'); p.wait_for_timeout(50); hint=p.locator('#h_chrom').inner_text(); check('акц.' in hint,f'подсказка суммы: {hint}')
        b0=S(p)['bal']; click(p,'[data-buy=chrom]'); s=S(p); q1=s['port']['chrom']['q']; check(q1==int(1000//pr) and b0-s['bal']<=1000,f'покупка на сумму 1000 Н → {q1} акц.')
        click(p,'[data-qmode=qty]'); check(p.evaluate("ui.qmode")=='qty','переключатель на штуки')
        p.fill('#q_chrom','4'); click(p,'[data-sell=chrom]'); s=S(p); check(s['port']['chrom']['q']==q1-4,'продажа 4 акций поштучно'); check(s['stats']['trades']>=1,'статистика сделок')
        click(p,'[data-qfill="chrom:.5"]'); v=p.locator('#q_chrom').input_value(); check(int(v)==max(1,(q1-4)//2),f'кнопка 50% в штуках → {v}')
        click(p,'[data-qmode=sum]'); click(p,'[data-qfill="chrom:.25"]'); v=int(p.locator('#q_chrom').input_value()); check(abs(v-int(p.evaluate('avail()')*.25))<=1,f'кнопка 25% от свободных → {v}')
        check(p.locator('.pl').count()>=2,'плашки прибыли/убытка есть (позиция + портфель)')
        txt=p.locator('#app').inner_text(); check('Закрытые сделки' in txt and '%' in txt,'портфель в процентах')
        p.screenshot(path=f'{OUT}/09b_stocks_new.png',full_page=True)
        click(p,'[data-buy=cerb]'); click(p,'[data-sellall=cerb]'); s=S(p); check(s['port']['cerb']['q']==0,'продать все акции')
        p.evaluate("ui.qmode='qty';SN.render()"); p.fill('#q_chrom','10'); click(p,'[data-buy=chrom]'); p.evaluate("ui.qmode='sum';SN.render()")
        click(p,'[data-act=rumorStock]'); s=S(p); check(s['rumors']['stock'] is not None,'слух по акциям куплен')
        click(p,'[data-act=verifyStock]'); s=S(p); check(s['rumors']['stock']['checked'],'слух проверен Шипом')
        # expo
        p.evaluate("ui.modal=null;ui.tab='expo';SN.render()")
        if (S(p)['t']%1440)>=19*60: adv(p,(24*60-(S(p)['t']%1440))+9*60)
        p.evaluate("ui.modal=null;ui.tab='expo';SN.render()")
        boxes=p.locator('[data-expo]'); k=min(3,boxes.count())
        for i in range(k): p.locator('[data-expo]').nth(i).check(); p.wait_for_timeout(50)
        s=S(p); check(len(s['expo']['entries'])==k and k>0,f'записано {k} машин на выставку')
        click(p,'[data-guard="2"]'); check(S(p)['expo']['guard']==2,'усиленная охрана')
        p.select_option('#gangSize','3'); click(p,'[data-act=gang]'); check(S(p)['expo']['gang']['size']==3,'банда из 3 готова')
        p.screenshot(path=f'{OUT}/10_expo.png',full_page=True)
        m=(20*60-(S(p)['t']%1440))+1; adv(p,m); s=inv(p,'expo')
        check(s['expo']['done'] and s['expo']['res'] is not None,'выставка подведена в 20:00')
        check(all(c['lock']!='expo' for c in s['cars']),'машины с выставки разблокированы')
        p.evaluate("document.getElementById('toast').innerHTML='';SN.render()"); p.screenshot(path=f'{OUT}/11_expo_res.png',full_page=True)
        # bug Давида: перемотка через выставку и полночь
        p.evaluate("ui.modal=null;SN.render()")
        p.evaluate("dev('to1855')"); p.evaluate("ui.modal=null;ui.tab='expo';SN.render()")
        boxes=p.locator('[data-expo]')
        if boxes.count(): boxes.first.check()
        p.evaluate("dev(360)")
        s=S(p); check(s['lastExpo'] is not None and s['lastExpo']['day']==(s['t']//1440),'итоги вчерашней выставки сохранены после полуночи')
        mk=p.evaluate("ui.modal&&ui.modal.k"); body=p.locator('#sheet').inner_text() if mk else ''
        check(mk!='expoRes' or 'Итоги выставки' in body,f'окно итогов не пустое (modal={mk})')
        p.evaluate("ui.modal=null;ui.tab='expo';SN.render()"); txt=p.locator('#app').inner_text(); check('Итоги прошлой выставки' in txt,'карточка итогов прошлой выставки')
        click(p,'[data-act=expoRes]'); check('Итоги выставки' in p.locator('#sheet').inner_text(),'подробные итоги открываются')
        p.screenshot(path=f'{OUT}/11b_expo_last.png',full_page=True); p.evaluate("ui.modal=null;SN.render()")
        # не участвовал
        p.evaluate("dev('to1855')"); p.evaluate("SN.S.expo.entries.forEach(u=>{const c=SN.S.cars.find(x=>x.u===u);if(c)c.lock=null});SN.S.expo.entries=[]"); p.evaluate("dev(70)")
        s=S(p); check(s['lastExpo']['took']==False,f"итоги видны и без участия {s['lastExpo'].get('took')} gang={s['expo'].get('gang')} t={s['t']%1440}")
        p.evaluate("ui.modal=null;ui.tab='expo';SN.render()"); click(p,'[data-act=expoRes]'); check('не участвовали' in p.locator('#sheet').inner_text(),'текст «не участвовали»'); p.evaluate("ui.modal=null;SN.render()")
        p.evaluate('ui.modal=null;SN.render()')
        # buyout: go to day 5, rumor, verify, day 6 sell
        s=S(p); d=s['t']//1440+1
        if d<5: adv(p,(5-d)*1440)
        p.evaluate("SN.S.jail=0;ui.tab='market';ui.sub.market='boss';ui.modal=null;SN.render()")
        p.screenshot(path=f'{OUT}/12_boss.png',full_page=True)
        if S(p)['t']//1440+1==5:
            click(p,'[data-act=rumorBuy]'); check('6' in S(p)['rumors']['buy'],'слух о выкупе куплен')
            click(p,'[data-act=verifyBuy]'); check(S(p)['rumors']['buy']['6']['checked'],'слух о выкупе проверен')
            cty=S(p)['buyouts']['6']['cty']
            p.evaluate(f"(()=>{{const c=CARS.find(x=>x.cty==='{cty}'&&x.r!=='D');SN.S.cars.push(mkCar(SN.S,c.id,'stock'))}})()")
            adv(p,(5*1440)-S(p)['t']+60); p.evaluate("ui.modal=null;ui.tab='market';ui.sub.market='boss';SN.render()")
            b0=S(p)['bal']; click(p,'[data-boss]'); s=inv(p,'boss'); check(s['bal']>b0 and s['buyouts']['6']['sold']==1,'продажа Боссу в день выкупа')
        # loans
        p.evaluate("ui.modal=null;ui.tab='city';SN.render()"); click(p,'[data-act=loans]'); click(p,'[data-loan]')
        s=inv(p,'loan'); check(s['loan'] and s['loan']['debt']==2000,'взят малый долг')
        bal=s['bal']; p.evaluate(f"SN.S.bal={s['holds']+2500};SN.render()")
        p.evaluate("ui.tab='garage';ui.modal=null;SN.render()"); check(p.locator('[data-act=openPort]').is_disabled(),'контейнер на заёмные деньги заблокирован')
        p.evaluate(f"SN.S.bal={bal};SN.render()")
        adv(p,4*1440+60); s=inv(p,'overdue'); check(s['loan'] and s['loan']['workoff'],'просрочка малого долга → отработка')
        p.evaluate('ui.modal=null;SN.render()')
        # claim a daily → goes to debt
        p.evaluate("SN.S.cnt={};SN.S.cday=Math.floor(SN.S.t/1440)+1;SN.S.daily.ids.forEach(i=>{const t=DAILY.find(x=>x.id===i);SN.S.cnt[t.k]=t.need});SN.S.jail=0;ui.tab='city';ui.modal=null;SN.render()")
        d0=S(p)['loan']['debt']; click(p,'[data-act=tasks]'); click(p,'[data-daily]'); s=S(p)
        check((s['loan'] is None) or s['loan']['debt']<d0,'награда за задание пошла в счёт долга')
        click(p,'#sheet [data-close]')
        p.evaluate("if(SN.S.loan){SN.S.bal+=SN.S.loan.debt+10;repay()}SN.render()"); check(S(p)['loan'] is None,'долг закрыт')
        # big loan & collateral
        p.evaluate("(()=>{const c=CARS.find(x=>x.r==='E');SN.S.cars.push(mkCar(SN.S,c.id,'stock'))})();ui.tab='city';ui.modal=null;SN.render()")
        click(p,'[data-act=loans]'); click(p,'[data-loanbig]'); s=S(p); check(s['loan'] and s['loan']['kind']=='big','крупный долг под залог')
        adv(p,6*1440+30); p.evaluate('SN.render()'); check(p.locator('[data-coll]').count()==2,'выбор: отдать залог или отработать')
        p.screenshot(path=f'{OUT}/13_collateral.png')
        click(p,'[data-coll=give]'); s=inv(p,'coll'); check(s['loan'] is None,'залог отдан, долг закрыт')
        # season scouting & finale
        p.evaluate("SN.S.jail=0;SN.S.bal+=20000;ui.modal=null;SN.render()")
        click(p,'[data-act=season]'); p.screenshot(path=f'{OUT}/14_season.png',full_page=True); click(p,'#sheet [data-act=tasks]')
        for sid in ['place','time','guard','route']:
            for _ in range(6):
                if S(p)['clues'][sid]>=1: break
                p.evaluate(f"SN.S.scoutCd['{sid}']=0;SN.render()"); click(p,f'[data-scout="{sid}"]')
        s=S(p); check(all(s['clues'][k]>=1 for k in s['clues']),'все 4 типа зацепок собраны')
        p.evaluate("ui.modal=null;SN.render()")
        # кружка для Кракса: видно репутацию и подтверждение покупки (отзыв Давида)
        p.evaluate("SN.S.mugDay=0;SN.S.jail=0;document.getElementById('toast').innerHTML='';ui.modal={k:'tasks'};SN.render()")
        r0=S(p)['rep']; click(p,'#sheet [data-act=mug]'); s=S(p)
        check(s['rep']==r0+25,'кружка даёт +25 репутации')
        check('+25 реп.' in p.locator('#toast').inner_text(),'после покупки кружки показан тост с репутацией')
        sh=p.locator('#sheet').inner_text(); rt=p.evaluate("'репутация '+fmt(SN.S.rep)"); check(rt.upper() in sh.upper(),'в заданиях видна текущая репутация')
        check('Уже куплена' in sh and p.locator('#sheet [data-act=mug]').is_disabled(),'кнопка кружки: «Уже куплена»')
        p.evaluate("ui.modal=null;SN.render()")
        p.evaluate("dev('toFinal')"); adv(p,10); s=inv(p,'finale'); check(s['finale'] is not None,'финал сезона прошёл')
        p.evaluate("document.getElementById('toast').innerHTML='';SN.render()"); p.screenshot(path=f'{OUT}/15_finale.png')
        p.evaluate('ui.modal=null'); adv(p,3*1440+200); s=S(p); check(s['inkShown'],'Чернильная ночь показана')
        p.evaluate("document.getElementById('toast').innerHTML='';SN.render()"); p.screenshot(path=f'{OUT}/16_ink.png'); click(p,'[data-act=newSeason]'); s=inv(p,'newSeason')
        check(s['season']==2 and s['bal']==1500,'новый сезон с общего старта')
        # monkey test
        random.seed(1)
        for i in range(250):
            btns=p.locator('main button:not([disabled]), #sheet button:not([disabled]), nav button')
            n=btns.count()
            if n==0: continue
            try:
                btns.nth(random.randrange(n)).click(timeout=600)
            except Exception as e: pass
            if i%20==0: adv(p,random.choice([30,120,600]))
            if i%50==0: inv(p,f'monkey{i}')
        inv(p,'monkey-end')
        for tab in ['city','garage','market','expo','stocks']:
            p.evaluate(f"ui.modal=null;ui.tab='{tab}';SN.render()"); p.screenshot(path=f'{OUT}/z_{tab}.png',full_page=True)
        b.close()
run()
print('\n==== ERRORS ====');print('\n'.join(errors) or 'none')
print('==== FAILS ====');print('\n'.join(fails) or 'none')
sys.exit(1 if errors or fails else 0)
