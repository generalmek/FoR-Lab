"""Bounded, deterministic interpretation of observed language, not style imitation."""
import re

QUESTIONS={'что ты понял','что ты понял из видео','перескажи своими словами',
           'перескажи фрагмент','как это подано','какая манера подачи'}
FOLLOW={'а почему','почему','почему ты так понял','на чем основано','почему он поправился'}
BASIS='Язык · пробный разбор фрагмента, не проверка фактов'
CORRECTION=re.compile(r'(?i)\b(?:нет[,!:] ?|простите|поправка|точнее|вернее|поправлюсь|я ошибся)\b')
NUMBER=re.compile(r'(?<![\d:])\d{2,5}(?![\d:])')


def analyze(rows):
    rows=list(rows)[-18:]
    for i in range(len(rows)-1,-1,-1):
        stamp,text=rows[i]
        if not CORRECTION.search(text) or re.search(r'[«»"“”]|\b(?:якобы|шучу|шутка)\b',text,re.I):
            continue
        nums=NUMBER.findall(text)
        # A fronted apology before two counts is not a correction.
        atoms=list(NUMBER.finditer(text))
        marker=CORRECTION.search(text)
        if (len(nums)==2 and nums[0]!=nums[1] and marker.start()>atoms[0].end()
                and not re.search(r'(?i)\b(?:и|или|плюс)\b',text[atoms[0].end():atoms[1].start()])
                and (marker.start()<atoms[1].start() or
                     not re.search(r'[а-яёa-z]',text[atoms[1].end():marker.start()],re.I))):
            return ('поправка', nums[0],nums[1],(stamp,))
        if len(nums)==1 and i:
            earlier,value=rows[i-1]
            a=NUMBER.findall(value)
            if (len(a)==1 and a[0]!=nums[0]
                    and re.match(r'(?i)^\s*(?:нет|поправка|точнее|вернее|поправлюсь|я ошибся)\b',text)):
                return ('поправка',a[0],nums[0],(earlier,stamp))
    return None


def route(runtime,q):
    if q not in QUESTIONS and q not in FOLLOW:
        runtime.discourse151=None
        return None
    lesson=getattr(runtime,'screen_lesson145',None)
    old=getattr(runtime,'discourse151',None)
    if q in FOLLOW:
        if old and lesson and lesson.target and old[0]==lesson.key:
            return old[1],BASIS
        return None
    runtime.discourse151=None
    rows=lesson.discourse_rows() if lesson and lesson.target else []
    if not rows:
        return 'Пока нет прочитанного фрагмента для разбора. Включи субтитры и «Глаз».',BASIS
    if q in {'как это подано','какая манера подачи'}:
        text=' '.join(s for _,s in rows)
        markers=[]
        if re.search(r'\b(?:наверное|похоже|возможно|по-моему|кажется)\b',text,re.I):
            markers.append('есть слова, которыми говорящий обозначает неуверенность')
        if re.search(r'\b(?:шучу|шутка|мы шутим)\b',text,re.I):
            markers.append('говорящий прямо обозначает шутку')
        if analyze(rows):
            markers.append('говорящий поправляется')
        answer=('В этом фрагменте '+', '.join(markers)+'.' if markers else
                'Не нашёл явных признаков, по которым могу уверенно назвать манеру этого фрагмента.')
        return answer+' По одному фрагменту не сужу о манере автора в целом.',BASIS
    result=analyze(rows)
    if result:
        _,a,b,stamps=result
        where=', '.join(stamps)
        runtime.discourse151=(lesson.key, f'Я опирался на {where}: там есть явный маркер поправки. Почему говорящий поменял число, из текста не ясно.')
        return f'Похоже, говорящий сначала назвал {a}, а затем поправился на {b}. Основание — {where}. Я не проверял, какое число верно.',BASIS
    candidates=runtime.reading146.recent('ocr',lesson.key)
    # A candidate from earlier in the session is not evidence for this fragment.
    visible={stamp for stamp,_ in rows}
    candidates=[row for row in candidates if (row[6].split(' · ',1)[0] in visible
                or row[6].removeprefix('субтитры · ') in visible)]
    if candidates:
        row=candidates[0]
        a,b=row[2:4]
        where=row[6]
        answer=(f'Автор связывает «{a}» и «{b}» как причину и следствие.' if row[1]=='causal_claim'
                else f'Автор относит «{a}» к категории «{b}».')
        runtime.discourse151=(lesson.key,f'Я опирался на утверждение источника ({where}). Независимой проверки у меня нет.')
        return answer+f' Основание — {where}. Сам это не проверял.',BASIS
    return f'Взял для разбора {len(rows)} фрагментов, но пока не смог уверенно связать их в одну мысль. Это не значит, что чтение не работало.',BASIS
