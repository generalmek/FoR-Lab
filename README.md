# FoR-Lab — Foundations of Reason / Основы Разума

**Experimental laboratory · Экспериментальная лаборатория**  
Research snapshot / Срез исследований: **23 October 2026 / 23 октября 2026**

[English](#english) · [Русский](#русский)

## English

### What this project investigates

Can an agent detect that its decision rests on insufficient grounds, choose a useful check, revise its model or measurement method, and update the decisions that depend on it?

FoR-Lab translates selected mechanisms from **Foundations of Reason** into executable symbolic prototypes. The laboratory contains code, tests, protocols, traces, earlier versions and negative cases. It makes the proposed mechanisms inspectable and exposes where they fail.

### Authorship and use of AI

**Mihail Tkalic** — author of Foundations of Reason and initiator of the research project.

The laboratory was developed **with AI assistance** for programming, local execution, analysis of results, protocol refinement and preparation of documentation. AI-assisted review is not independent scientific validation.

The verdict below is an **internal synthesis of the recorded laboratory results**, not an external peer-review decision. No independent replication is claimed.
### Verdict of this stage

> **Selected mechanisms have executable implementations and work in the tested, restricted environments. Some causal roles are supported by disabling and restoring components. Scientific superiority of FoR over the comparison algorithms is not established; the full architecture of Reason is not validated.**

This stage provides working prototypes, reproducible records and concrete limits. It neither confirms nor refutes the entire theory. The development series was open and iterative; it is not a completed preregistered confirmatory study.

### What the results show

| Mechanism or question | Observed result | Scope of the conclusion |
|---|---|---|
| Updating decisions after a model correction | Disabling the update leaves a stale plan with error 3; restoring it gives error 0 | Supports the role of the update in this implementation. B2 also achieves error 0 |
| Repairing a measurement method | The old scaling case has total dependent-plan error 6; revised calibration reduces it to 0 | A specific engineering defect was corrected; successful measurement now costs 4 readings rather than 2 |
| Detecting an inadequate measurement model | A quadratic distortion is rejected; absent references and insufficient budget leave the question open | Works under the declared reference, noise and model-class assumptions |
| Transferring a saved method | A saved procedure is reloaded and recalibrated for new parameters | Demonstrates reuse of an implemented procedure, not acquired general learning |
| Correction and rollback | A false observation causes error 1.5; supplied counterevidence and rollback restore error 0 | The system does not independently detect every false observation; this is limited recovery |
| Consequences and action constraints | A local risk check and explicit prohibition affect the selected action | A constrained decision pilot, not a derivation or validation of the full Compass or universal ethics |

**Important negative results:**

- B2, the comparison controller, is equal or cheaper in the final pilots. Overall architectural advantage is not demonstrated.
- The nonlinear mapping `y = 2x + x(x−1)(x−3)` agrees with the calibration model at all three reference points, yet both implementations err by 1 at `x = 2`.
- An integration scenario reaches its goal with an incorrect model. That task therefore does not establish that correct identification is necessary for success.
- A permitted but false observation can corrupt a correction. Wider robustness to deception, noise and unknown risk is unresolved.

The latest measurement suite records **8/8 software tests passing**, including the expected counterexample. Passing tests do not turn that negative scientific result into a success. The eight control classes are only partially covered; they are not eight completed validations of the theory. Autonomous formation of Reason, the full Core and Compass, general semantic understanding and cumulative development in an Incubator remain unestablished.

### Download and run

The complete source tree is currently distributed as **[FoR-Lab.zip](FoR-Lab.zip)**. Download and extract it into an empty folder. **Do not run from inside the ZIP.** The repository-level files describe the package; the source code is inside it.

Python **3.11+**. From the extracted folder on Windows:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -B -m unittest discover -s . -p "test_*.py" -v
.\.venv\Scripts\python.exe -B research/measurement-fix-2026-10-23/run.py
```

NumPy is used by the earlier numerical prototype; later research pilots use the standard library. Tkinter is needed only for the legacy GUI. On Linux/macOS use `python3 -m venv .venv` and `.venv/bin/python`.

Root test discovery does **not** cover every research suite. Use the relevant `Start_FoR_*.bat` launcher or the entry point shown in it. New pilot runs write timestamped results under their own `runs/` directory.

### Reading the evidence

Inside the archive:

| Location | Contents |
|---|---|
| `research/audit-0.3a-2026-10-23/` | Procedure audit, corrected contracts, research journal and earlier failures |
| `research/integrated-2026-10-23/` | Integration pilot and the successful-action/wrong-model case |
| `research/eight-controls-2026-10-23/COVERAGE_8_RU.md` | What each control class covers and leaves unresolved |
| `research/cycles-9-11-2026-10-23/RESULTS_RU.md` | Consequences, rollback and dependent-plan updates |
| `research/final-12-14-2026-10-23/RESULTS_RU.md` | Initiative, saved methods, comparison results and limits |
| `research/measurement-fix-2026-10-23/RESULTS_AND_AMENDMENT_RU.md` | Calibration repair, remaining counterexample and proposed engineering clarification |
| Each suite's `runs/` | Source snapshots, test output, traces, manifests and summaries |

Detailed reports are currently in Russian; this README gives a bilingual overview. Historical runs are versions of related pilots, not independent statistical replications. Read protocols and negative cases together with the test counts.

### Package integrity

Original laboratory files were not modified. Virtual environments, caches and raw chat/browser captures are excluded; personal user-directory components and email addresses are redacted. `RELEASE_MANIFEST.json` records the original and publication hashes for copied research files and the exclusions. Historical hashes can refer to the unsanitized originals. `SHA256SUMS.txt` verifies the archive when downloaded from the repository.

Publication preparation checked the file inventory, common credential patterns and Python syntax. No new experiments were run for publication or this README revision. These checks are not an independent replication or an exhaustive security audit.

---

## Русский

### Что исследует проект

Может ли агент обнаружить, что основания его решения недостаточны, выбрать полезную проверку, исправить модель или способ измерения и пересмотреть зависящие от них решения?

FoR-Lab переводит отдельные механизмы **«Основ Разума»** в исполняемые символические прототипы. Здесь сохранены код, тесты, протоколы, трассы, предыдущие версии и отрицательные случаи. Это позволяет проверять предложенные механизмы и видеть, где они перестают работать.

### Авторство и применение ИИ

**Михаил Ткалич** — автор «Основ Разума» и инициатор исследовательского проекта.

Лаборатория разработана **с применением ИИ** для программирования, локальных запусков, анализа результатов, уточнения протоколов и подготовки документации. Проверка с помощью ИИ не является независимой научной экспертизой.

Приведённый ниже вердикт — **внутренний итог по сохранённым результатам лаборатории**, а не решение внешней научной экспертизы. Независимое воспроизведение не заявляется.
### Вердикт этого этапа

> **Отдельные механизмы реализованы и работают в проверенных ограниченных средах. Для некоторых связей показана причинная роль через отключение и восстановление компонентов. Научное преимущество FoR над алгоритмами сравнения не установлено; полная архитектура Разума не подтверждена.**

Результат этапа — работающие прототипы, воспроизводимые записи и конкретные границы применимости. Это не подтверждение и не опровержение всей теории. Разработка была открытой и итерационной; завершённой предварительно зарегистрированной подтверждающей серии здесь нет.

### Что показали проверки

| Механизм или вопрос | Наблюдаемый результат | Что из этого следует |
|---|---|---|
| Обновление решений после исправления модели | Без обновления сохраняется устаревший план с ошибкой 3; после восстановления ошибка 0 | Показана роль обновления в этой реализации. B2 также получает ошибку 0 |
| Исправление измерительного метода | В прежнем случае масштабного искажения суммарная ошибка зависимых планов 6; после новой калибровки — 0 | Исправлен конкретный инженерный дефект; успешный метод требует 4 измерения вместо 2 |
| Обнаружение непригодной измерительной модели | Квадратичное искажение отклоняется; отсутствие эталонов или бюджета оставляет вопрос открытым | Результат действует при заявленных предпосылках об эталонах, шуме и классе моделей |
| Перенос сохранённого метода | Процедура загружается и повторно калибруется при новых параметрах | Показано повторное применение реализованной процедуры, а не приобретённое общее обучение |
| Исправление и откат | Ложное свидетельство даёт ошибку 1,5; предоставленное опровержение и откат возвращают 0 | Система не распознаёт любое ложное свидетельство самостоятельно; восстановление ограничено |
| Последствия и ограничения действий | Локальная проверка риска и явный запрет меняют выбор действия | Пилот ограниченного выбора, а не вывод или подтверждение полного Компаса и универсальной этики |

**Существенные отрицательные результаты:**

- Алгоритм сравнения B2 в завершающих пилотах равен или дешевле. Преимущество архитектуры в целом не показано.
- Нелинейное преобразование `y = 2x + x(x−1)(x−3)` совпадает с калибровочной моделью на всех трёх эталонах, но обе реализации ошибаются на 1 при `x = 2`.
- В интеграционном сценарии цель достигается даже с неверной моделью. Такая задача не доказывает необходимость правильной идентификации для успеха.
- Допустимое по формату, но ложное свидетельство способно испортить исправление. Общая устойчивость к обману, шуму и неизвестному риску остаётся открытым вопросом.

В последнем измерительном наборе прошли **8 из 8 программных тестов**, включая ожидаемый контрпример. Зелёные тесты не превращают этот отрицательный научный результат в успех. Восемь классов контролей покрыты частично: это не восемь завершённых проверок всей теории. Самостоятельное формирование Разума, полные Ядро и Компас, общее семантическое понимание и накопительное развитие в Инкубаторе ещё не установлены.

### Скачать и запустить

Полное дерево исходников пока распространяется архивом **[FoR-Lab.zip](FoR-Lab.zip)**. Скачайте и распакуйте его в пустую папку. **Не запускайте файлы внутри ZIP.** Файлы на главной странице описывают пакет; код находится в архиве.

Нужен Python **3.11+**. Из распакованной папки в Windows:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -B -m unittest discover -s . -p "test_*.py" -v
.\.venv\Scripts\python.exe -B research/measurement-fix-2026-10-23/run.py
```

NumPy нужен раннему численному прототипу; поздние исследовательские пилоты используют стандартную библиотеку. Tkinter требуется только старому графическому интерфейсу. В Linux/macOS используйте `python3 -m venv .venv` и `.venv/bin/python`.

Поиск тестов из корня **не охватывает все наборы**. Для каждого этапа используйте соответствующий `Start_FoR_*.bat` либо указанный в нём исполняемый файл. Новые запуски сохраняют результаты в отдельные каталоги с датой и временем внутри `runs/` своего набора.

### Где смотреть основания вердикта

Внутри архива:

| Путь | Содержание |
|---|---|
| `research/audit-0.3a-2026-10-23/` | Аудит процедуры, исправленный контракт, исследовательский журнал и ранние неудачи |
| `research/integrated-2026-10-23/` | Интеграционный пилот и случай успеха с неверной моделью |
| `research/eight-controls-2026-10-23/COVERAGE_8_RU.md` | Покрытие и ограничения восьми классов контролей |
| `research/cycles-9-11-2026-10-23/RESULTS_RU.md` | Последствия, откат и обновление зависимых планов |
| `research/final-12-14-2026-10-23/RESULTS_RU.md` | Инициатива, сохранённые методы, сравнение и ограничения |
| `research/measurement-fix-2026-10-23/RESULTS_AND_AMENDMENT_RU.md` | Исправление калибровки, оставшийся контрпример и предложение инженерной поправки |
| `runs/` каждого набора | Снимки исходников, вывод тестов, трассы, манифесты и сводки |

Подробные отчёты пока на русском; README даёт обзор на двух языках. Исторические запуски — версии связанных пилотов, а не независимые статистические повторения. Число тестов следует читать вместе с протоколом и отрицательными случаями.

### Целостность пакета

Исходная лаборатория не изменена. Исключены виртуальные окружения, кэши и необработанные выгрузки чатов/браузера; личные имена каталогов пользователя и адреса электронной почты обезличены. `RELEASE_MANIFEST.json` содержит исходные и публикационные хэши скопированных исследовательских файлов и список исключений. Хэши в исторических журналах могут относиться к исходным необезличенным версиям. `SHA256SUMS.txt` позволяет проверить скачанный из репозитория архив.

При подготовке проверены состав файлов, типовые признаки секретов и синтаксис Python. Новых экспериментов ради публикации или этой правки README не проводилось. Эти проверки не являются независимым воспроизведением или исчерпывающим аудитом безопасности.

