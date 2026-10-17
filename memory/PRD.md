# PRD — ERP Service Auto România

## Original problem statement
PROMPT ERP SERVICE AUTO ROMÂNIA — platformă ERP enterprise completă (SaaS + On-Premise) pentru administrarea unui service auto din România, comparabilă cu Autosoft / WinMentor Service / Tekmetric etc. Module: Dashboard Executiv, CRM Clienți (PF cu CNP / PJ cu CUI, Reg. Com.), Parc auto (VIN, marcă, model, an, motorizare, putere, euro, combustibil, km, istoric), Recepție (notă recepție, fișă intrare, PV predare-primire, fișă constatare, poze obligatorii față/spate/laterale/interior, semnătură electronică), Comandă de lucru (flux Recepție→Deviz→Aprobare→Lucrări→CC→Facturare→Livrare, statusuri Nouă…Închisă), Devize (email/SMS/WhatsApp, aprobare digitală, versiuni), Manoperă (norme RAR/Autodata/HaynesPro, tarife pe categorii, pontaj automat), Mecanici (productivitate = ore facturate/ore prezente, eficiență = ore normate/ore efective), Magazie (NIR, cod OE/aftermarket, raft, FIFO/LIFO, loturi), Achiziții (LKQ, Autonet, InterCars, Unix, ATP, AD), Facturare ANAF/e-Factura, Încasări (numerar/POS/transfer/online, chitanță, registru casă), integrare e-Factura, RAR, RAR PASS, Control calitate, Planificare, Garanții, Notificări, ITP/RCA/CASCO/Rovinietă/Leasing, Flotă, BI, AI (Service Advisor, Diagnostic OBD, Stock Forecast, Retention), RBAC 14 roluri, Portal client, aplicație mobilă mecanic, 300+ rapoarte, cerințe enterprise (multi-company, multi-currency, audit, GDPR, ISO). Stack cerut inițial: .NET 9/PostgreSQL/Next.js/Flutter — implementat pe stack-ul disponibil React + FastAPI + MongoDB.

User choices: prima livrare = nucleul de service (Dashboard, CRM, Parc auto, Recepție, Comenzi de lucru, Devize, Mecanici, Magazie, Facturare + Încasări); JWT email/parolă cu conturi create de admin și roluri; AI = Gemini (Emergent key); e-Factura XML + exporturi reale, transmitere ANAF/RAR + notificări SIMULATE; UI RO + EN.
Follow-up request (2026-10-17): decodare automată VIN la crearea vehiculului, marcă = selectare din listă, model = selectare din listă.

## Architecture
- Backend FastAPI (/app/backend): core.py (DB, JWT, RBAC MODULE_ROLES, calc_totals), routes_auth (auth, users, settings, audit), routes_crm (clients, vehicles, expirations, vehicle-catalog, VIN decode), routes_service (mechanics, work orders, quotes, QC, timers, elevators, public quote), routes_stock (products, suppliers, NIR, FIFO), routes_finance (invoices, e-Factura UBL CIUS-RO, payments, cash register), routes_dashboard, routes_ai (Gemini streaming), efactura.py, vehicle_catalog.py (makes/models catalog, WMI, NHTSA vPIC), seed.py (demo data).
- Frontend React (/app/frontend/src): Layout cu sidebar filtrat pe permisiuni, RO/EN + dark/light, pagini Dashboard, Clients, ClientDetail, Vehicles, Reception (wizard), WorkOrders (kanban DnD + listă), WorkOrderDetail (linii, devize, CC, pontaj, recepție, istoric), Mechanics, Stock, Invoices, InvoiceDetail, Cash, AiAssistant, Users, Settings, PublicQuote (/approve/:token), PrintDoc (/print/:kind/:id).

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

## MOCKED
- ANAF SPV upload/status, trimitere devize pe email/SMS/WhatsApp

## Backlog
- P0: date reale firmă în Setări (acum placeholder), certificat/OAuth ANAF real
- P1: Planificare calendar (elevatoare/mecanici DnD), Garanții & reclamații, Notificări reale (ITP/RCA), Portal client complet, Achiziții furnizori + comparare prețuri, RAR / RAR PASS export XML, Rapoarte (TVA, producție, marjă), Flotă cu aprobări multiple
- P2: Multi-company/warehouse/currency complet, AI stock forecast & retention, aplicație mobilă mecanic, backup, LIFO, storno facturi

## Next tasks
- Planificare calendar + Garanții; rapoarte de bază
