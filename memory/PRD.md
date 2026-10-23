# PRD — ERP Service Auto România

## Original problem statement
PROMPT ERP SERVICE AUTO ROMÂNIA — platformă ERP enterprise completă (SaaS + On-Premise) pentru administrarea unui service auto din România, comparabilă cu Autosoft / WinMentor Service / Tekmetric etc. Module: Dashboard Executiv, CRM Clienți (PF cu CNP / PJ cu CUI, Reg. Com.), Parc auto (VIN, marcă, model, an, motorizare, putere, euro, combustibil, km, istoric), Recepție (notă recepție, fișă intrare, PV predare-primire, fișă constatare, poze obligatorii față/spate/laterale/interior, semnătură electronică), Comandă de lucru (flux Recepție→Deviz→Aprobare→Lucrări→CC→Facturare→Livrare, statusuri Nouă…Închisă), Devize (email/SMS/WhatsApp, aprobare digitală, versiuni), Manoperă (norme RAR/Autodata/HaynesPro, tarife pe categorii, pontaj automat), Mecanici (productivitate = ore facturate/ore prezente, eficiență = ore normate/ore efective), Magazie (NIR, cod OE/aftermarket, raft, FIFO/LIFO, loturi), Achiziții (LKQ, Autonet, InterCars, Unix, ATP, AD), Facturare ANAF/e-Factura, Încasări (numerar/POS/transfer/online, chitanță, registru casă), integrare e-Factura, RAR, RAR PASS, Control calitate, Planificare, Garanții, Notificări, ITP/RCA/CASCO/Rovinietă/Leasing, Flotă, BI, AI (Service Advisor, Diagnostic OBD, Stock Forecast, Retention), RBAC 14 roluri, Portal client, aplicație mobilă mecanic, 300+ rapoarte, cerințe enterprise (multi-company, multi-currency, audit, GDPR, ISO). Stack cerut inițial: .NET 9/PostgreSQL/Next.js/Flutter — implementat pe stack-ul disponibil React + FastAPI + MongoDB.

User choices: prima livrare = nucleul de service (Dashboard, CRM, Parc auto, Recepție, Comenzi de lucru, Devize, Mecanici, Magazie, Facturare + Încasări); JWT email/parolă cu conturi create de admin și roluri; AI = Gemini (Emergent key); e-Factura XML + exporturi reale, transmitere ANAF/RAR + notificări SIMULATE; UI RO + EN.
Follow-up request (2026-10-17): decodare automată VIN la crearea vehiculului, marcă = selectare din listă, model = selectare din listă.

## Architecture
- Backend FastAPI (/app/backend): core.py (DB, JWT, RBAC MODULE_ROLES, calc_totals), routes_auth (auth, users, settings, audit), routes_crm (clients, vehicles, expirations, vehicle-catalog, VIN decode), routes_service (mechanics, work orders, quotes, QC, timers, elevators, public quote), routes_stock (products, suppliers, NIR, FIFO), routes_finance (invoices, e-Factura UBL CIUS-RO, payments, cash register), routes_planning, routes_reports, routes_dashboard, routes_ai, efactura.py, anexa5.py, vehicle_catalog.py, seed.py.
- Frontend React (/app/frontend/src): Layout cu sidebar filtrat pe permisiuni, RO/EN + dark/light, pagini Dashboard, Clients, ClientDetail, Vehicles, Reception (wizard), WorkOrders (kanban DnD + listă), WorkOrderDetail (linii, devize, CC, pontaj, recepție, istoric), PlanningCalendar, FinalInspectionReport, Mechanics, Stock, Invoices, InvoiceDetail, Cash, AiAssistant, Users, Settings, PublicQuote (/approve/:token), PrintDoc (/print/:kind/:id).

## User personas
Administrator, Director, Șef service, Consilier service, Recepționer, Magazioner, Mecanic/Electrician/Tinichigiu/Vopsitor, Contabil, Casier, Manager flotă, Client (aprobare deviz public).

## Implemented (2026-10-17)
- JWT auth (cookie + Bearer), brute-force lockout (X-Forwarded-For), RBAC pe module, admin + 7 demo users
- Dashboard KPI timp real + grafice venit/profit/încasări, statusuri, productivitate mecanici, expirări ITP/RCA
- CRM PF/PJ cu validare CNP, CUI obligatoriu, flotă/limită buget, GDPR; istoric reparații/facturi
- Parc auto + istoric; VIN auto-decode (NHTSA vPIC + WMI local + coduri model VAG), marcă/model din listă (35 mărci) cu opțiune „Altul”
- Recepție wizard: 5 poze opționale (modificat 2026-10-17 la cererea clientului), semnătură canvas obligatorie, accesorii, daune, elevator → CL-YYYY-NNNNN
- Comenzi de lucru: kanban drag&drop, reguli status (Finalizată doar după CC, Facturată automat, Închisă după facturare), piese și manoperă separate (tab-uri distincte, formulare dedicate, bară totaluri; 2026-10-17), mecanici alocați
- Devize versionate, trimitere email/SMS/WhatsApp (SIMULAT), aprobare semnată în service sau link public
- Control calitate (7 puncte + semnătură mecanic + șef service), pontaj automat pe lucrare, pontaj prezență
- Magazie: produse OE/aftermarket/raft, NIR cu loturi, cost mediu, consum FIFO la facturare, mișcări stoc
- Facturi fiscale/proforme, XML e-Factura UBL CIUS-RO, transmitere SPV + recipisă (SIMULATE), încasări cu documente (chitanță etc.), registru de casă
- Documente tipăribile: notă recepție/PV, deviz, factură, chitanță, NIR, registru casă
- AI Gemini (gemini-3.1-pro-preview) Service Advisor + Diagnostic OBD cu context istoric vehicul, streaming, markdown
- Utilizatori & audit log, setări companie (date firmă placeholder, tarife, serii, elevatoare)

## Financiar, stoc și documente (2026-10-18)
- Stornare fiscală totală/parțială pe linii și cantități, prin note de credit UBL `CreditNote`
- Legătură bidirecțională factură originală ↔ notă de credit, cu status și valori stornate
- Reintroducere opțională în stoc a pieselor stornate, la costul de ieșire
- Retururi către furnizor, cu scădere stoc FIFO și legare opțională de NIR-ul de origine
- PDF local pentru facturile e-Factura primite, generat din XML și disponibil lângă NIR
- UBL pentru facturi și note de credit cu `TaxSubtotal` separat pentru fiecare cotă TVA

## RAR AutoPass (2026-10-18)
- Administrare › RAR AutoPass: un punct de lucru implicit, cod autorizație RAR, CUI,
  mediu Test/Producție și token stocat criptat pe server
- La emiterea facturii fiscale și la închiderea comenzii se creează/actualizează idempotent
  o intrare outbox cu VIN, număr de înmatriculare, kilometraj, timestamp recepție,
  referință foto opțională, factură și rezumat operațiuni
- Transmiterea externă este intenționat inactivă până la primirea contractului API RAR,
  endpointurilor oficiale de test/producție și a tokenului de acces
- Teste RAR/stornare/retur/TVA mixt: 30 teste funcționale trecute, cu 2 skip-uri RBAC

## Calendar și Anexa 5 RAR (2026-10-18)
- Planificare calendar completă cu vizualizări zi, săptămână, lună și rampe/elevatoare,
  alocare de client, vehicul, rampă, consilier și mecanici, mutare/redimensionare DnD
- Validare de disponibilitate pentru rampă și mecanic, capacitate calculată pe durata reală,
  statusuri operaționale și conversie idempotentă în comandă de lucru la „În lucru"
- Confirmarea programării și reminder-ul de 24h sunt jurnalizate local; cronul rulează la 15 minute
- Controlul calității finale folosește cele 7 categorii Anexa 5 și codurile C/N/NA;
  o inspecție neconformă sau nevalidată blochează finalizarea/facturarea fiscală
- Rapoarte › Registru Inspecții Finale: filtre perioadă/inspector, tabel cu 13 coloane,
  export PDF A4 landscape, CSV și Excel; PDF-ul include font Unicode pentru diacritice
- Teste de regresie: 54 teste trecute, cu 2 skip-uri RBAC; build frontend reușit

## Garanții piese și manoperă (2026-10-18)
- Factura fiscală generează automat, o singură dată, certificatul PDF de garanție;
  piesele folosesc perioada produsului (implicit 24 luni), iar manopera are 3 luni
- Certificatul include factura, client, vehicul, CUI emitent, cod/articol, cantitate,
  perioadă și dată de valabilitate; se descarcă din factură sau din Garanții
- Dosarul de reclamație validează acoperirea și cantitatea cumulată, apoi creează o comandă
  GW distinctă cu preț zero pentru client; rezultatul tehnic, returul furnizor și soluția sunt trasabile
- Stornarea reduce acoperirea liniilor creditate; comenzile GW nu pot fi facturate fiscal
- Alertele de acoperire activă sunt afișate pe comanda vehiculului; certificatele au index unic pe factură
- Teste garanții + regresii: 85 teste trecute, cu 2 skip-uri RBAC; PDF-ul a fost verificat vizual

## Reguli deviz pentru închidere (2026-10-18)
- Orice comandă nefacturată poate fi închisă direct, indiferent de deviz sau QC; statusul anterior
  este păstrat pentru redeschidere. O comandă cu `invoice_id` nu poate fi închisă/redeschisă.
- Administrare › Verificare închideri nefacturate listează exclusiv comenzile nefacturate închise;
  administratorul poate aplica Aprobare sau Redeschidere comandă, iar rândul dispare din listă.
- Factura fiscală necesită obligatoriu un deviz emis cu status `approved`, control calitate promovat
  și status `finalizata`; factura emisă păstrează statusul terminal `facturata`.
- Retestare completă: 43/43 teste backend și 100% fluxuri UI; datele TEST au fost curățate.

## Multi-tenant pool model (2026-10-19)
- Izolare logică strictă pentru datele operaționale prin `tenant_id` și `branch_id`; contextul este
  extras din JWT și orice acces fără context eșuează controlat.
- Tenantul demo `demo-tenant-001` și sucursala `demo-branch-001` au fost păstrate și toate datele
  operaționale existente au fost migrate idempotent către acest context.
- Rolul proprietarului este `SUPERADMIN`; panoul Platformă permite administrarea tenanturilor,
  planurilor, cotelor de sucursale, sucursalelor și Tenant Admin-ilor.
- Doar Superadmin poate crea sucursale. Tenant Admin poate administra exclusiv utilizatorii din
  contextul său. Cota implicită este o sucursală per tenant.
- Selectorul global de sucursală este disponibil în interfață, iar schimbarea ramurii reemite
  contextul de lucru fără a expune date din alte sucursale.
- Setările, seriile, configurările RAR/e-Factura, contoarele, OAuth-ul și cronurile sunt izolate
  per tenant și sucursală; tenanturile suspendate/expirate și sucursalele inactive sunt blocate.
- Hardening final: upsert-urile fără context tenant/sucursală răspund `503`, fără scrieri de date.
- Verificare: 57 teste multi-tenant trecute; curățarea a confirmat 0 date temporare rămase.
  Livrare testată de agent, în așteptarea confirmării de acceptanță a utilizatorului.

## Corecție header mobil (2026-10-19)
- Acțiunile principale din header sunt vizibile din nou pe ecrane mobile: deschidere meniu,
  recepție nouă, schimbare limbă, schimbare temă și deconectare.
- Acțiunea „Recepție nouă” se afișează ca icon compact pe mobil și cu etichetă pe ecrane mai mari;
  selectorul de sucursală rămâne restrâns pentru a preveni overflow-ul.
- Verificare la 390px: toate acțiunile au fost vizibile și funcționale, fără erori în consolă.

## Ciclul de viață tenant Superadmin (2026-10-19)
- Superadmin creează tenanturi fără ID introdus manual: ID-ul tenantului și ID-ul sediului principal
  se generează automat. Formularul cere Nume companie SRL, CUI, email administrator, parolă
  inițială și planul `BASIC` sau `FULL`.
- `BASIC` oferă o singură sucursală, iar `FULL` oferă până la cinci. La creare se generează un
  Tenant Admin, asociat exclusiv sediului principal, cu parolă bcrypt și obligație de schimbare
  a parolei la prima conectare.
- Utilizatorii cu parolă inițială nu pot accesa date operaționale până nu o schimbă. Pagina
  dedicată validează parola curentă, lungimea, confirmarea și interzice reutilizarea parolei.
- Tenantul poate fi șters doar de Superadmin, cu confirmare prin numele exact al companiei;
  ștergerea elimină utilizatori, sucursale, date operaționale și contoare. Tenantul activ al
  Superadminului nu poate fi șters.
- Securitate: CUI și email administrator sunt validate și unice, ID-urile nu sunt acceptate din
  payload-ul public, iar ștergerea contoarelor folosește escaping pentru expresii regulate.
- Verificare: 67 teste de regresie multi-tenant și 10 teste de ciclu tenant au trecut; curățarea
  a confirmat 0 tenanturi, sucursale, utilizatori sau date temporare rămase.

## Migrare Superadmin și resetare Tenant Admin (2026-10-19)
- Tenantul demo istoric a fost migrat idempotent la un ID generat automat `tenant-e93a5f22c8ba4a11`,
  afișat ca `SUPERADMIN`; sediul principal și cele 9 conturi asociate au primit contextul nou.
- Migrarea a mutat datele operaționale, setările, jurnalele, configurațiile e-Factura/RAR și seriile,
  apoi a eliminat referințele rămase către ID-urile demo vechi. Tenanturile comerciale existente au
  rămas neatinse.
- Lista Superadmin afișează emailul administratorului principal al fiecărui tenant, fără hash-uri sau
  alte date sensibile. Asocierea administratorului principal este robustă și are fallback controlat.
- Superadmin poate genera o parolă temporară pentru Tenant Admin al unui alt tenant; parola apare o
  singură dată, este stocată exclusiv bcrypt, șterge blocajele de login și impune schimbarea parolei
  înainte de acces operațional. Tenantul propriu Superadmin nu poate fi resetat din această acțiune.
- UI: dialogul de resetare previne generarea dublă, permite copierea sigură cu tratarea erorilor și
  funcționează fără overflow pe mobil.
- Verificare: 79 teste backend au trecut, build frontend reușit și curățarea a confirmat 0 date
  temporare rămase; fluxurile de migrare, resetare și schimbare obligatorie au fost testate și în UI.

## Administrare plan și date tenant (2026-10-19)
- Tenantul `SUPERADMIN` are planul `FULL` și capacitate pentru locații multiple.
- Superadmin poate edita numele companiei, CUI-ul, planul BASIC/FULL, statusul și emailul
  administratorului principal din lista de tenanturi.
- Mesajele Superadmin comunică acum regula curentă: BASIC include o sucursală, iar FULL permite
  locații multiple, fără a menționa vechea limită de cinci.
- Selectorul de plan din creare afișează doar valorile BASIC și FULL; regulile de capacitate rămân
  explicate separat în mesajul informativ.
- Mesajul de creare menționează exclusiv generarea automată a ID-ului de tenant; configurarea
  sediului principal rămâne responsabilitatea tenantului în propriul cont.
- Actualizarea validează unicitatea CUI/email, recalculează automat cota de sucursale la 1 pentru
  BASIC și 999 pentru FULL și păstrează jurnalul de audit.
- Verificare: API-ul confirmă `SUPERADMIN` ca FULL, build frontend reușit și dialogul de editare
  a fost verificat în interfață.

## Matrice planuri actualizată (2026-10-19)
- BASIC: 1 locație, 500 MB storage documente și maximum 500 comenzi de lucru pe lună.
- FULL: 5 locații, 10 GB storage documente și maximum 5.000 comenzi de lucru pe lună.
- ENTERPRISE: locații multiple, 50 GB storage documente și comenzi de lucru nelimitate.
- Cotele sunt centralizate în backend, aplicate la creare/editare tenant și comenzi de lucru, apoi
  afișate în Setări. FULL și ENTERPRISE au aceleași drepturi premium de branding/module.

## Stabilizare setări și logo Base64 (2026-10-19)
- Salvarea Setărilor funcționează și pentru tenanturi fără `labor_rates` sau elevatoare, fără eroarea
  „Cannot convert undefined or null to object”. Setările noi primesc implicit TVA 21% și termen 30 zile.
- Endpointul de setări acceptă doar câmpuri validate, ignoră scope/plan/câmpuri derivate/logo din
  payload și normalizează subdomeniul nul; logo-ul se actualizează exclusiv prin endpointul dedicat.
- Tenanturile FULL/ENTERPRISE pot elimina ulterior logo-ul personalizat; BASIC rămâne blocat.
- Verificare: testing agent a confirmat fluxul UI/Backend de salvare sparse și logo; suita specifică
  a trecut 17/17, iar curățarea a confirmat 0 date temporare.

## Navigare laterală compactă (2026-10-19)
- Bara laterală desktop afișează doar iconițele modulelor pentru a elibera spațiu de lucru.
- La hover, fiecare iconiță afișează un tooltip cu denumirea modulului; accesibilitatea este păstrată
  prin etichete ARIA.
- Pe mobil, meniul lateral rămâne extins, cu denumiri complete pentru navigare clară.
- Verificare: tooltip desktop și meniul mobil au fost testate vizual; build frontend reușit.
- Toggle-ul de extindere/restrângere este poziționat în header, înaintea datei, fără duplicat în
  bara laterală. Lățimea sidebarului se schimbă fluid între 64px și 240px.
- Logo-ul și textul Performa Auto trimit la Dashboard; subtitlul `ERP · RO` a fost eliminat.
- Meniul mobil are titlu accesibil pentru dialog, iar categoria tooltip-urilor are contrast ierarhic.
- Scrollbar-ul sidebarului are 4px, fără butoane/săgeți native în Chromium/WebKit; Firefox primește
  fallback thin și transparent. Retestarea a confirmat derularea în ambele stări fără overflow.
- Stilul vizual al toggle-ului de sidebar a fost păstrat în varianta ghost anterioară, la cererea
  utilizatorului; poziționarea și comportamentul de extindere/restrângere rămân neschimbate.

## Programări: comandă, ștergere și modal responsiv (2026-10-19)
- Programările pot fi șterse și după crearea unei comenzi de lucru; se elimină doar programarea și
  notificările sale, iar comanda rămâne intactă.
- Formularul de programare nu mai expune statusul sau Consilierul service; consilierul este setat
  automat din utilizatorul autentificat, iar mecanicul se selectează din dropdown.
- Footer-ul modalului afișează Creare comandă în stânga, apoi Comandă după conversie, alături de
  Șterge și Salvează. Pe mobil, Șterge/Salvează sunt icon-only, accesibile și aliniate la 40px.
- Dialogurile și calendarul folosesc scrollbar-ul discret de 4px; dialogurile rămân încadrate în
  viewport cu scroll intern.
- Verificare: testing agent a trecut 11/11 teste backend și 100% UI pentru conversie, ștergere,
  păstrarea comenzii, dropdown mecanic și acțiuni mobile; build frontend reușit.

## Identitate vizuală Performa (2026-10-19)
- Logo-ul Performa furnizat a fost decupat și pregătit cu fundal transparent în
  `frontend/public/performa-logo.png`.
- Varianta inițială a fost înlocuită cu semnul compact bleumarin-portocaliu, pătrat, furnizat
  ulterior de utilizator; dimensiunile din interfață au fost adaptate pentru noul format.
- Ambele teme folosesc acum aceeași variantă portocalie transparentă, fără halo sau margini deschise,
  pentru o identitate Performa uniformă pe fundaluri light și dark.
- Favicon-ul `performa-favicon.png` este generat din semnul Performa și este declarat atât în
  documentul HTML, cât și la rularea aplicației, pentru încărcare fiabilă în previzualizare.
- Logo-ul înlocuiește monogramele anterioare în autentificare, bara laterală desktop și meniul
  lateral mobil, păstrând proporțiile și contrastul în temele aplicației.
- Verificare: logo vizibil în cele trei zone, fără erori de consolă; build frontend reușit.

## Corecții code review P0: sesiuni și stabilitate UI (2026-10-23)
- Clientul web folosește exclusiv cookie-uri HttpOnly pentru sesiune. `erp_token` și headerul
  Bearer au fost eliminate din `localStorage`, Axios și fluxul AI; preferințele vizuale locale
  (limbă, temă și sidebar) sunt păstrate separat.
- Login, refresh, schimbarea parolei inițiale și schimbarea sucursalei nu mai expun JWT-ul în
  răspunsurile JSON. Refresh-ul este protejat împotriva apelurilor paralele, iar eșecul lui
  marchează sesiunea interfeței ca neautentificată.
- JWT-urile includ o versiune de sesiune. Logout-ul, schimbarea parolei și schimbarea sucursalei
  invalidează tokenurile anterioare server-side; tokenurile replay după logout sunt respinse.
- Testele RAR și e-Factura folosesc credențiale de test citite din documentația de test și tokenuri
  temporare, fără parole sau secrete hardcodate. Importurile dinamice de `ObjectId` au fost
  înlocuite cu importuri statice.
- Dependențele Hooks au fost corectate pentru API, VIN, OAuth e-Factura și semnătură. Rândurile
  editabile NIR/retur folosesc identificatori locali stabili, iar cheile bazate exclusiv pe index
  au fost eliminate din zonele revizuite.
- Verificare: build frontend curat; 10/10 teste P0 cookie/auth/stoc trecute; login UI, refresh,
  logout, revocare token replay, AI cu cookie, NIR, retur, VIN și e-Factura au fost testate.
  Datele temporare create de test au fost curățate. Livrare testată de agent, în așteptarea
  confirmării de acceptanță a utilizatorului.
- Test debt cunoscut, preexistent: patru suite legacy de fixture-uri nu sunt compatibile cu
  izolarea multi-tenant și trebuie mutate într-un tenant TEST dedicat înainte de reactivare.

## P1: paginare server-side și filtre Facturi (2026-10-23)
- Listele Facturi, Comenzi, Clienți, Vehicule, Produse, NIR, Retururi, Încasări, Certificate și
  Dosare de garanție încarcă maximum 20 de rânduri prin API, cu total și navigare între pagini.
  Endpointurile fără parametrii de paginare păstrează răspunsurile vechi pentru dropdownuri și
  integrări existente.
- Filtrele Facturi (tip, status, text, client, CUI, vehicul/VIN și interval) rulează pe server;
  totalul financiar și numărul documentelor reflectă exact filtrul activ. Selectorul de dată este
  un calendar accesibil, iar tabelul rămâne lizibil pe mobil prin derulare orizontală.
- Căutarea în Facturi, Comenzi, Clienți, Vehicule și Stoc are întârziere controlată de 300 ms.
  Răspunsurile vechi sunt ignorate, iar schimbarea filtrului mută imediat la pagina 1 fără curse de
  rețea. Paginarea Mongo include `_id` drept criteriu secundar pentru rezultate complete și stabile.
- Verificare: 40/40 teste API trecute; contractele paginate, filtrele, ordinea NIR, validarea zilei
  pentru încasări, compatibilitatea endpointurilor vechi și resetarea filtrelor în browser au fost
  validate. Datele temporare identificate în liste au fost curățate. Livrare testată de agent,
  în așteptarea confirmării de acceptanță a utilizatorului.

## P1: condiții comerciale client și Fișă de cont (2026-10-23)
- Persoanele juridice au termen preferențial opțional în zile și limită de credit implicită de
  0 RON. Fără termen setat, condiția este CASH. Persoanele fizice sunt protejate server-side de
  termen sau limită de credit.
- Emiterea unei facturi fiscale peste plafon afișează avertisment, dar nu blochează operațiunea.
  Fișa de client afișează condiția de plată, plafonul și expunerea curentă.
- Pagina clientului are taburile paginate (20 rânduri): Istoric Comenzi, Facturi și Fișa Cont.
  Fișa cont include interval, sold inițial/final, facturi, încasări, stornări și export PDF.
  Vehiculele din pagina clientului deschid acum pagina de detaliu vehicul.
- Verificare: API PJ/PF, valoare implicită 0 RON, Fișă cont și PDF verificate; documentul PDF a
  fost randat și verificat vizual. Livrare testată, în așteptarea acceptanței utilizatorului.

## P1: încasări, numerar și registru de casă (2026-10-23)
- Încasări & registru de casă are taburi pentru Registru de casă, Încasări numerar și POS / OP.
  Înregistrarea selectează clientul și factura restantă sau aplică automat FIFO după scadență.
- Pentru numerar se emit chitanță sau, doar la persoane fizice, bon fiscal înregistrat ca document
  emis la casa de marcat existentă. POS, OP și online sunt separate de numerar.
- Registrul calculează numai intrările de numerar și depunerile bancare; depunerile parțiale sau
  totale nu pot depăși soldul disponibil. Plățile FIFO apar corect pe fiecare factură și o singură
  dată în Fișa de cont.
- După înregistrarea unei chitanțe sau a unui bon fiscal, documentul se deschide automat în pagina
  de tipărire. Operatorul poate astfel tipări imediat documentul emis.
- Verificare: 18/18 teste de regresie financiară trecute după corecția atomică a alocării FIFO,
  controlului bonului fiscal PJ/PF, filtrelor, listelor și depunerilor. Build frontend reușit.

## MOCKED
- Trimiterea devizelor pe email/SMS/WhatsApp
- e-Factura în mediul „Simulare” (implicit) – Test/Producție sunt integrări reale ANAF (necesită Client ID/Secret + autorizare SPV cu certificat)
- RAR AutoPass: outbox-ul și validarea precondițiilor sunt active, însă transportul către RAR
  este blocat până la contractul API oficial și tokenul furnizate de client
- Programări: confirmările și reminder-ele de 24h sunt jurnalizate cu status `simulated`;
  nu se expediază SMS sau email până la configurarea unui furnizor

## RO e-Factura (2026-10-17)
- Administrare › eFactura / Setări API: OAuth 2.0 ANAF (Client ID/Secret criptat Fernet, Redirect URI, state CSRF), comutare Simulare/Test/Producție (api.anaf.ro/test|prod), status conexiune, jurnal, auto-trimitere
- Facturi: validare internă CIUS-RO (CIF, UN/ECE, TVA, totaluri, IBAN) + validare publică ANAF, upload, index_incarcare, stareMesaj, recipisă ZIP, erori ANAF; TaxSubtotal per cotă TVA
- Stocuri › Facturi e-Factura primite: sincronizare SPV (listaMesajeFactura + descarcare), import XML, parsare UBL, mapare articole (memorată), NIR din XML, detectare duplicat + Overwrite/Link fără mișcări duplicate
- CRON (.emergent/crons.yml): refresh token zilnic, polling stare la 15 min, inbox orar
- Documentație: /app/docs/EFACTURA.md

## Backlog
- P0: date reale firmă în Setări (acum placeholder), certificat/OAuth ANAF real; confirmare de
  acceptanță pentru migrarea multi-tenant.
- P1: retestare end-to-end invalidare deviz după editarea liniilor; regresie UBL TVA mixt; izolare
  suite legacy într-un tenant TEST dedicat; contract API RAR AutoPass, endpointuri oficiale, token
  și validare Sandbox; notificări reale (ITP/RCA), portal client complet, achiziții furnizori +
  comparare prețuri, rapoarte executive (TVA, producție, marjă, retenție), flotă cu aprobări
  multiple.
- P2: warehouse/currency complet, AI stock forecast & retention, aplicație mobilă mecanic, backup,
  LIFO.

## Next tasks
- Confirmați în interfață comportamentul tenantului demo, al panoului Superadmin și al selectorului
  de sucursală.
- Confirmați fluxul de creare tenant, prima conectare cu schimbarea parolei și ștergerea cu
  confirmare în panoul Superadmin.
- Confirmați în UI lista Superadmin actualizată, emailul Tenant Admin și resetarea parolei temporare
  pentru tenanturile comerciale.
- Retestați end-to-end invalidarea devizului după editarea pieselor sau manoperei aprobate.
- Planificați izolarea fixture-urilor legacy RAR/e-Factura/storno/multi-tenant într-un tenant TEST.
- Obțineți documentația contractuală RAR, endpointurile Test/Producție și tokenul de acces.
- Validați un payload într-un mediu RAR Sandbox înainte de activarea transportului extern.
- Implementați rapoarte executive de eficiență, marjă, timp de staționare și retenție/flotă.
